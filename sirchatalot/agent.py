'''
The agent loop: lets the model call tools across multiple bounded iterations
using the modern OpenAI tools protocol (assistant message with tool_calls,
role:"tool" results, parallel calls supported).
'''

import asyncio
import json
from dataclasses import dataclass, field

from sirchatalot.config import ModelSpec
from sirchatalot.engine import Usage
from sirchatalot.logging_setup import get_logger
from sirchatalot.model_registry import ModelRegistry
from sirchatalot.tools import ToolContext, ToolRegistry, ToolResult

logger = get_logger('agent')


def _status_for(call: dict) -> str:
    '''Human-readable one-liner about a tool call for the live status message.'''
    name = call['function']['name']
    try:
        args = json.loads(call['function']['arguments'] or '{}')
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        args = {}
    if name == 'web_search':
        return f'🔍 Searching the web: {str(args.get("query", ""))[:80]}'
    if name == 'url_opener':
        return f'📄 Opening {str(args.get("url", ""))[:80]}'
    if name == 'semantic_search':
        return f'🗂 Searching documents: {str(args.get("text", ""))[:60]}'
    if name == 'read_file':
        return f'📖 Reading {str(args.get("filename", ""))[:60]}'
    if name == 'generate_image':
        return '🎨 Generating an image…'
    if name == 'save_memory':
        return '📝 Saving a memory…'
    if name.startswith('mcp__'):
        parts = name.split('__', 2)
        if len(parts) == 3:
            return f'🔧 {parts[1]}: {parts[2]}…'
    return f'🔧 {name}…'


def describe_calls(calls: list[dict]) -> str:
    return '\n'.join(_status_for(c) for c in calls)


@dataclass
class AgentOutcome:
    text: str
    messages: list
    spec: ModelSpec
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0    # priced per call with the model actually used
    media: list[bytes] = field(default_factory=list)
    images_generated: int = 0


async def run_turn(user_id: int, messages: list, registry: ModelRegistry,
                   tools: ToolRegistry, ctx: ToolContext, max_iterations: int = 5,
                   end_user: str | None = None, primary=None,
                   on_status=None, max_turn_tokens: int | None = None) -> AgentOutcome:
    '''
    Run one conversation turn. `messages` is mutated in place (assistant/tool
    messages are appended) and returned inside the outcome for persistence.
    `on_status` (async callable) receives human-readable tool activity updates.
    '''
    total_usage = Usage()
    cost_usd = 0.0
    media: list[bytes] = []
    schemas = tools.enabled_schemas(ctx)
    # identical calls within one turn are dispatched once
    call_cache: dict[tuple[str, str], ToolResult] = {}

    for iteration in range(max_iterations):
        result, spec = await registry.complete(
            user_id, messages, tools=schemas or None, end_user=end_user, primary=primary
        )
        total_usage += result.usage
        cost_usd += result.usage.cost(spec)
        assistant = result.message

        if not assistant.get('tool_calls'):
            messages.append({'role': 'assistant', 'content': assistant.get('content') or ''})
            return AgentOutcome(text=assistant.get('content') or '', messages=messages,
                                spec=spec, usage=total_usage, cost_usd=cost_usd,
                                media=media, images_generated=len(media))

        messages.append(assistant)
        calls = assistant['tool_calls']
        logger.debug(f'Iteration {iteration}: model called '
                     f'{[c["function"]["name"] for c in calls]} (user {user_id})')
        if on_status is not None:
            try:
                await on_status(describe_calls(calls))
            except Exception:
                logger.debug('Status callback failed', exc_info=True)

        # dispatch only calls not seen before in this turn
        fresh: dict[tuple[str, str], asyncio.Task] = {}
        for call in calls:
            key = (call['function']['name'], call['function']['arguments'] or '')
            if key not in call_cache and key not in fresh:
                fresh[key] = asyncio.ensure_future(
                    tools.dispatch(ctx, call['function']['name'],
                                   call['function']['arguments']))
        if fresh:
            for key, tool_result in zip(fresh, await asyncio.gather(*fresh.values())):
                call_cache[key] = tool_result
        media_taken: set[tuple[str, str]] = set()
        for call in calls:
            key = (call['function']['name'], call['function']['arguments'] or '')
            tool_result = call_cache[key]
            messages.append({'role': 'tool', 'tool_call_id': call['id'],
                             'content': tool_result.for_model})
            # a repeated call reuses the text but does not resend the media
            if key in fresh and key not in media_taken:
                media.extend(tool_result.images)
                media_taken.add(key)

        if max_turn_tokens is not None and (
                total_usage.prompt_tokens + total_usage.completion_tokens) >= max_turn_tokens:
            logger.warning(f'Agent hit the token budget ({max_turn_tokens}) '
                           f'for user {user_id}')
            break

    # iteration/token budget exhausted: force a final text answer
    logger.warning(f'Agent forcing a final answer for user {user_id}')
    result, spec = await registry.complete(user_id, messages, tools=None,
                                           end_user=end_user, primary=primary)
    total_usage += result.usage
    cost_usd += result.usage.cost(spec)
    text = result.message.get('content') or ''
    messages.append({'role': 'assistant', 'content': text})
    return AgentOutcome(text=text, messages=messages, spec=spec, usage=total_usage,
                        cost_usd=cost_usd, media=media, images_generated=len(media))
