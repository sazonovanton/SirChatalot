'''
The single OpenAI-compatible LLM engine.

One LLMEngine per configured model (see ModelSpec in config.py). Anthropic, Yandex,
local models etc. are used through their OpenAI-compatible endpoints or OpenRouter.
'''

import hashlib
from dataclasses import dataclass, field

import tiktoken
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from sirchatalot.config import ModelSpec
from sirchatalot.logging_setup import get_logger

logger = get_logger('engine')

# errors worth retrying on another model in the fallback chain
RETRIABLE_ERRORS = (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError)


class EngineError(Exception):
    '''A completion failed in a way that should not be retried on another model.'''


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __iadd__(self, other: 'Usage') -> 'Usage':
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        return self

    def cost(self, spec: ModelSpec) -> float:
        return (self.prompt_tokens * spec.prompt_price
                + self.completion_tokens * spec.completion_price) / 1_000_000


@dataclass
class ChatResult:
    message: dict            # normalized assistant message: content + optional tool_calls
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = 'stop'


def hashed_user(user_id) -> str:
    return hashlib.sha1(str(user_id).encode('utf-8')).hexdigest()


def openai_http_client(proxy: str | None):
    '''httpx client for AsyncOpenAI-based engines; None uses the SDK default.'''
    if not proxy:
        return None
    import httpx
    return httpx.AsyncClient(proxy=proxy)


class LLMEngine:
    def __init__(self, spec: ModelSpec, default_proxy: str | None = None):
        self.spec = spec
        self.proxy = spec.proxy or default_proxy
        self.client = AsyncOpenAI(
            api_key=spec.api_key,
            base_url=spec.base_url,
            timeout=spec.timeout_seconds,
            max_retries=1,
            http_client=openai_http_client(self.proxy),
        )
        try:
            self.encoding = tiktoken.encoding_for_model(spec.model.split('/')[-1])
        except KeyError:
            self.encoding = tiktoken.get_encoding('cl100k_base')

    async def complete(self, messages: list, tools: list | None = None,
                       tool_choice: str | None = None, end_user: str | None = None,
                       max_tokens: int | None = None) -> ChatResult:
        '''
        One chat completion. Raises RETRIABLE_ERRORS unchanged (for the fallback chain)
        and EngineError for everything else.
        '''
        kwargs = {}
        if tools:
            kwargs['tools'] = tools
            kwargs['tool_choice'] = tool_choice or 'auto'
        if end_user is not None:
            kwargs['user'] = hashed_user(end_user)
        if max_tokens is not None:
            kwargs['max_tokens'] = max_tokens
        try:
            response = await self.client.chat.completions.create(
                model=self.spec.model,
                temperature=self.spec.temperature,
                messages=messages,
                **kwargs,
            )
        except RETRIABLE_ERRORS:
            raise
        except Exception as e:
            raise EngineError(f'{self.spec.name}: {e}') from e

        choice = response.choices[0]
        message = {'role': 'assistant', 'content': choice.message.content}
        if choice.message.tool_calls:
            message['tool_calls'] = [
                {'id': tc.id, 'type': 'function',
                 'function': {'name': tc.function.name, 'arguments': tc.function.arguments}}
                for tc in choice.message.tool_calls
            ]
        usage = Usage(
            prompt_tokens=int(getattr(response.usage, 'prompt_tokens', 0) or 0),
            completion_tokens=int(getattr(response.usage, 'completion_tokens', 0) or 0),
        )
        return ChatResult(message=message, usage=usage,
                          finish_reason=choice.finish_reason or 'stop')

    async def summary(self, text: str, size: int = 420,
                      instruction: str | None = None) -> tuple[str, Usage]:
        result = await self.complete(
            [{'role': 'system',
              'content': instruction or 'You are very good at summarizing text. '
                         'Answer to the user message with the summary only.'},
             {'role': 'user', 'content': str(text)}],
            max_tokens=size,
        )
        return result.message['content'] or '', result.usage

    async def moderation_flagged(self, text: str, user_id=None) -> list[str] | None:
        '''
        Check text with the OpenAI moderation API.
        Returns a list of flagged categories (empty if clean), or None if the check
        could not be performed (treated as pass by callers).
        '''
        try:
            response = await self.client.moderations.create(
                input=text, model='omni-moderation-latest'
            )
            output = response.results[0]
            if not output.flagged:
                return []
            categories = output.categories.model_dump()
            return sorted(k for k, v in categories.items() if v)
        except Exception as e:
            logger.error(f'Moderation check failed ({self.spec.name}): {e}')
            return None

    # rough per-image budget so histories with photos still get trimmed
    IMAGE_TOKENS = 1000

    def count_tokens(self, messages: list) -> int:
        tokens = 0
        for message in messages:
            text = f"{message.get('role', '')}: {message_text(message)}"
            tokens += len(self.encoding.encode(text))
            content = message.get('content')
            if isinstance(content, list):
                tokens += self.IMAGE_TOKENS * sum(
                    1 for p in content if p.get('type') == 'image_url')
        return tokens


def message_text(message: dict) -> str:
    '''Text representation of a message content (multimodal parts flattened, images skipped).'''
    content = message.get('content')
    if content is None:
        parts = []
    elif isinstance(content, str):
        parts = [content]
    else:
        parts = [p.get('text', '') for p in content if p.get('type') == 'text']
    if message.get('tool_calls'):
        for tc in message['tool_calls']:
            parts.append(f"[tool call: {tc['function']['name']}({tc['function']['arguments']})]")
    return ' '.join(p for p in parts if p)


def sanitize_for(messages: list, spec: ModelSpec) -> list:
    '''
    Adapt a history to the capabilities of a model:
    - no vision: image parts replaced with a text placeholder
    - no tools: assistant tool_calls flattened to text, tool results become user messages
    History in the DB stays untouched; this only shapes what is sent to the API.
    '''
    sanitized = []
    for message in messages:
        msg = dict(message)
        if not spec.vision and isinstance(msg.get('content'), list):
            texts = [p.get('text', '') for p in msg['content'] if p.get('type') == 'text']
            if any(p.get('type') == 'image_url' for p in msg['content']):
                texts.append('<the user sent an image, but the current model cannot see it>')
            msg['content'] = '\n'.join(t for t in texts if t)
        if not spec.tools:
            if msg.get('tool_calls'):
                msg = {'role': 'assistant', 'content': message_text(msg)}
            if msg.get('role') == 'tool':
                msg = {'role': 'user', 'content': f"[tool result] {msg.get('content', '')}"}
        sanitized.append(msg)
    return sanitized
