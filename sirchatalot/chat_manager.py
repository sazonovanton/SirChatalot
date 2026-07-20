'''
ChatManager: orchestrates a conversation turn — history, styles, moderation,
trimming/summarizing, the agent loop and statistics.
'''

import base64

from sirchatalot.agent import AgentOutcome, run_turn
from sirchatalot.config import AppConfig
from sirchatalot.db import Database
from sirchatalot.engine import Usage, message_text
from sirchatalot.logging_setup import get_logger
from sirchatalot.model_registry import AllModelsFailedError, ModelRegistry, summary_engine
from sirchatalot.tools import ToolContext, registry as tool_registry

logger = get_logger('chat')

ERROR_REPLY = ('Sorry, I could not get an answer to your message. '
               'Please try again or /delete your chat history.')

SUMMARY_MARKER = '<Conversation summary>'
COMPACT_INSTRUCTION = (
    'You maintain a running summary of a conversation. The user message contains '
    'the current summary (possibly empty) followed by newer messages. Produce an '
    'updated summary that preserves important facts, decisions, names, numbers and '
    'open questions. Answer with the updated summary only.'
)


class ChatManager:
    def __init__(self, cfg: AppConfig, db: Database, model_registry: ModelRegistry,
                 image_engine=None, audio_engine=None, web_search=None,
                 url_opener=None, files_rag=None, memory=None):
        self.cfg = cfg
        self.db = db
        self.registry = model_registry
        self.image_engine = image_engine
        self.audio_engine = audio_engine
        self.web_search = web_search
        self.url_opener = url_opener
        self.files_rag = files_rag
        self.memory = memory
        if cfg.chat.moderation and self.registry.engines[self.registry.default].spec.base_url:
            logger.warning('Moderation is enabled but the default model does not use '
                           'api.openai.com — moderation calls will likely fail and be '
                           'treated as pass.')

    # ---- system message ----

    async def _base_system_message(self, user_id: int) -> str:
        style_name = await self.db.get_style(user_id)
        if style_name and style_name in self.cfg.styles:
            return self.cfg.styles[style_name].system_message
        return self.cfg.chat.system_message

    async def _context_block(self, user_id: int) -> str:
        from datetime import datetime
        now = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')
        lines = [f'\n# Current date and time: {now}']
        full_name, username = await self.db.get_user_identity(user_id)
        if full_name or username:
            who = full_name or ''
            if username:
                who = f'{who} (@{username})'.strip()
            lines.append(f'# You are talking to: {who}')
        return '\n'.join(lines)

    async def _build_system_message(self, user_id: int, spec) -> str:
        text = await self._base_system_message(user_id)
        text += await self._context_block(user_id)
        if spec.vision:
            text += '\n# You have vision capabilities enabled'
        if spec.tools:
            text += '\n# You have function calling (tools) enabled'
        if self.files_rag is not None:
            files_block = await self._files_block(user_id)
            if files_block:
                text += files_block
        if self.memory is not None:
            text += await self.memory.prompt_block(user_id)
        return text

    async def _files_block(self, user_id: int) -> str:
        user_files = await self.db.list_files(str(user_id))
        common_files = await self.db.list_files('common')
        if not user_files and not common_files:
            return ''
        lines = ['\n# Available files:']
        if user_files:
            lines.append('## User files:')
            lines += [f'- {f["filename"]}: {f["summary"] or ""}' for f in user_files]
        if common_files:
            lines.append('## Common files:')
            lines += [f'- {f["filename"]}: {f["summary"] or ""}' for f in common_files]
        lines.append('---\nUse semantic search to find information in the files '
                     'when you think it can be there.')
        return '\n'.join(lines)

    async def _prepare_history(self, user_id: int, spec=None) -> list:
        if spec is None:
            spec = await self.registry.spec_for_user(user_id)
        messages = await self.db.get_history(user_id) or []
        system = {'role': 'system',
                  'content': await self._build_system_message(user_id, spec)}
        if messages and messages[0].get('role') == 'system':
            messages[0] = system
        else:
            messages.insert(0, system)
        return messages

    @staticmethod
    def _awaiting_caption(messages: list) -> bool:
        '''True when the last message is a user photo without any text yet.'''
        if not messages:
            return False
        last = messages[-1]
        content = last.get('content')
        return (last.get('role') == 'user' and isinstance(content, list)
                and any(p.get('type') == 'image_url' for p in content)
                and not any(p.get('type') == 'text' for p in content))

    # ---- history size management ----

    async def _shrink_if_needed(self, engine, messages: list) -> tuple[list, Usage]:
        usage = Usage()
        limit = engine.spec.max_history_tokens
        if engine.count_tokens(messages) <= int(limit * self.cfg.chat.compact_threshold):
            return messages, usage
        if self.cfg.chat.summarize_too_long:
            messages, usage = await self._compact(messages)
        # safety net: trim if still over budget (huge tail messages, failed summary)
        while engine.count_tokens(messages) > int(limit * 0.8) and len(messages) > 2:
            messages = self._trim_one(messages)
        return messages, usage

    def _trim_one(self, messages: list) -> list:
        '''Drop the oldest non-system, non-summary message with its tool-result tail.'''
        keep = 1
        if len(messages) > 1 and self._is_summary(messages[1]):
            keep = 2
        head, rest = messages[:keep], messages[keep:]
        drop = 1
        while drop < len(rest) and rest[drop].get('role') == 'tool':
            drop += 1
        return head + rest[drop:]

    @staticmethod
    def _is_summary(message: dict) -> bool:
        content = message.get('content')
        return (message.get('role') == 'assistant' and isinstance(content, str)
                and content.startswith(SUMMARY_MARKER))

    @staticmethod
    def _split_tail(body: list, keep: int) -> tuple[list, list]:
        '''
        Split into (middle, tail) keeping the last `keep` messages, then move
        orphaned tool plumbing from the tail into the middle: a role:"tool"
        message must follow its assistant tool_calls message.
        '''
        middle, tail = body[:-keep] if keep < len(body) else [], body[-keep:]
        while tail and (
            tail[0].get('role') == 'tool'
            or (tail[0].get('tool_calls')
                and sum(1 for m in tail[1:] if m.get('role') == 'tool')
                < len(tail[0]['tool_calls']))
        ):
            middle.append(tail.pop(0))
        return middle, tail

    async def _compact(self, messages: list) -> tuple[list, Usage]:
        '''
        Fold older messages into a rolling summary kept right after the system
        message; the last chat.keep_recent_messages stay verbatim.
        '''
        head = messages[0]
        body = messages[1:]
        old_summary = ''
        if body and self._is_summary(body[0]):
            old_summary = body[0]['content'].removeprefix(SUMMARY_MARKER).strip(': ')
            body = body[1:]
        middle, tail = self._split_tail(body, self.cfg.chat.keep_recent_messages)
        if not middle or not tail:
            return messages, Usage()
        transcript = '\n'.join(f"{m.get('role')}: {message_text(m)}" for m in middle)
        text = (f'Current summary:\n{old_summary or "(empty)"}\n\n'
                f'Newer messages:\n{transcript}')
        try:
            summary, usage = await summary_engine(self.registry).summary(
                text, instruction=COMPACT_INSTRUCTION)
        except Exception:
            logger.exception('Could not compact history, falling back to trimming')
            return messages, Usage()
        logger.debug(f'Compacted {len(middle)} messages into the rolling summary')
        return ([head, {'role': 'assistant', 'content': f'{SUMMARY_MARKER}: {summary}'}]
                + tail), usage

    # ---- moderation ----

    async def _moderation_blocked(self, user_id: int, text: str) -> bool:
        if not self.cfg.chat.moderation or not text:
            return False
        flagged = await summary_engine(self.registry).moderation_flagged(text, user_id)
        if flagged:
            logger.info(f'Message from user {user_id} was flagged: {flagged}')
            try:
                with open('./data/moderation.txt', 'a', encoding='utf-8') as f:
                    f.write(f'{user_id}\t{flagged}\n')
            except OSError:
                logger.exception('Could not write moderation log')
            return True
        return False

    # ---- main entry points ----

    async def process_text(self, user_id: int, text: str,
                           on_status=None) -> AgentOutcome | None:
        '''One conversation turn. Returns the outcome, or None on failure.'''
        try:
            if await self._moderation_blocked(user_id, text):
                return AgentOutcome(
                    text='Your message was flagged by moderation and was not sent. '
                         'Please try again.',
                    messages=[], spec=await self.registry.spec_for_user(user_id))

            engine = await self.registry.engine_for_user(user_id)
            messages = await self._prepare_history(user_id, engine.spec)
            if self._awaiting_caption(messages):
                messages[-1]['content'].append({'type': 'text', 'text': text})
            else:
                messages.append({'role': 'user', 'content': text})
            return await self._execute_turn(user_id, engine, messages, text,
                                            on_status=on_status)
        except AllModelsFailedError as e:
            logger.error(f'All models failed for user {user_id}: {e}')
            return AgentOutcome(
                text='The AI service is currently unavailable or rate limited. '
                     'Please try again later.',
                messages=[], spec=await self.registry.spec_for_user(user_id))
        except Exception:
            logger.exception(f'Could not process message from user {user_id}')
            return None

    async def _execute_turn(self, user_id: int, engine, messages: list,
                            text: str, on_status=None) -> AgentOutcome:
        messages, extra_usage = await self._shrink_if_needed(engine, messages)
        turn_start = len(messages)
        ctx = ToolContext(
            user_id=user_id, user_message=text,
            image_engine=self.image_engine, web_search=self.web_search,
            url_opener=self.url_opener, files_rag=self.files_rag,
            memory=self.memory,
            summary=self.summarize_text,
            url_summarize=bool(self.cfg.web and self.cfg.web.url_open
                               and self.cfg.web.url_open.summarize),
            rag_results=self.cfg.files.search_results if self.cfg.files else 4,
            disabled=await self.db.get_disabled_tools(user_id),
        )
        outcome = await run_turn(
            user_id, messages, self.registry, tool_registry, ctx,
            max_iterations=self.cfg.agent.max_iterations,
            end_user=str(user_id) if self.cfg.chat.end_user_id else None,
            primary=engine,
            on_status=on_status,
            max_turn_tokens=self.cfg.agent.max_turn_tokens,
        )
        outcome.usage += extra_usage
        outcome.cost_usd += extra_usage.cost(engine.spec)
        outcome.text = self._session_length_note(outcome)
        self._truncate_old_tool_results(outcome.messages, turn_start)
        await self.db.save_history(user_id, outcome.messages)
        await self.db.add_stats(
            user_id, messages_sent=1,
            prompt_tokens=outcome.usage.prompt_tokens,
            completion_tokens=outcome.usage.completion_tokens,
            images_generated=outcome.images_generated,
            cost_usd=outcome.cost_usd
            + outcome.images_generated * self._image_price(),
        )
        return outcome

    def _truncate_old_tool_results(self, messages: list, turn_start: int) -> None:
        '''Tool results from previous turns are kept only as short stubs: the model
        already used them, and re-sending full dumps every turn wastes tokens.
        The current turn's results (index >= turn_start) stay full.'''
        keep = self.cfg.agent.tool_result_keep_chars
        if not keep:
            return
        for message in messages[:turn_start]:
            content = message.get('content')
            if (message.get('role') == 'tool' and isinstance(content, str)
                    and len(content) > keep):
                message['content'] = content[:keep] + '… [truncated]'

    async def undo(self, user_id: int) -> bool:
        '''Remove the last exchange (the last user message and everything after it).'''
        messages = await self.db.get_history(user_id)
        if not messages:
            return False
        while messages and messages[-1].get('role') != 'user':
            messages.pop()
        if not messages:
            return False
        messages.pop()
        await self.db.save_history(user_id, messages)
        return True

    async def retry(self, user_id: int, on_status=None) -> AgentOutcome | None:
        '''Regenerate the answer to the last user message. None = nothing to retry.'''
        try:
            history = await self.db.get_history(user_id)
            if not history or not any(m.get('role') == 'user' for m in history):
                return None
            engine = await self.registry.engine_for_user(user_id)
            messages = await self._prepare_history(user_id, engine.spec)
            while messages and messages[-1].get('role') != 'user':
                messages.pop()
            if not messages or messages[-1].get('role') != 'user':
                return None
            text = message_text(messages[-1])
            return await self._execute_turn(user_id, engine, messages, text,
                                            on_status=on_status)
        except AllModelsFailedError as e:
            logger.error(f'All models failed for user {user_id}: {e}')
            return AgentOutcome(
                text='The AI service is currently unavailable or rate limited. '
                     'Please try again later.',
                messages=[], spec=await self.registry.spec_for_user(user_id))
        except Exception:
            logger.exception(f'Could not retry for user {user_id}')
            return None

    def _session_length_note(self, outcome: AgentOutcome) -> str:
        text = outcome.text
        limit = self.cfg.chat.max_session_length
        if limit is not None:
            used = len([m for m in outcome.messages if m.get('role') == 'user'])
            if limit - used <= 3:
                text += (f'\n*System*: You are close to the session limit. '
                         f'Messages left: {max(limit - used, 0)}. '
                         f'Use /delete to start a new session.')
        return text

    def _image_price(self) -> float:
        return self.cfg.image_generation.base_price if self.cfg.image_generation else 0.0

    async def summarize_text(self, text: str) -> str | None:
        try:
            summary, _ = await summary_engine(self.registry).summary(text)
            return summary
        except Exception:
            logger.exception('Summary failed')
            return None

    async def process_audio(self, user_id: int, file_path: str,
                            on_status=None) -> str | AgentOutcome | None:
        '''Voice/video message: transcribe, then answer (or transcript only).'''
        if self.audio_engine is None:
            return 'Sorry, speech-to-text is not available.'
        try:
            duration = await self.audio_engine.duration_seconds(file_path)
        except Exception:
            logger.exception('Could not read audio duration')
            duration = 0
        transcript = await self.audio_engine.transcribe(file_path)
        if transcript is None:
            return 'Sorry, I could not convert your audio/video to text.'
        await self.db.add_stats(
            user_id, voice_messages_sent=1, speech2text_seconds=round(duration),
            cost_usd=duration / 60 * self.audio_engine.cfg.price_per_minute,
        )
        if self.audio_engine.cfg.transcribe_only:
            return f'Transcription: {transcript}'
        return await self.process_text(user_id, transcript, on_status=on_status)

    async def add_image(self, user_id: int, image_b64: str) -> bool:
        '''Store an incoming photo in history; the caption may follow separately.'''
        try:
            messages = await self._prepare_history(user_id)
            messages.append({
                'role': 'user',
                'content': [{'type': 'image_url',
                             'image_url': {'url': f'data:image/jpeg;base64,{image_b64}'}}],
            })
            await self.db.save_history(user_id, messages)
            return True
        except Exception:
            logger.exception(f'Could not add image for user {user_id}')
            return False

    async def imagine(self, user_id: int, prompt: str) -> tuple[bytes | None, str | None]:
        '''/imagine command. Returns (image_bytes, caption/error text).'''
        if self.image_engine is None:
            return None, 'Sorry, image generation is not available.'
        b64_image, text = await self.image_engine.imagine(prompt, user_id=user_id)
        if b64_image is None:
            return None, text or 'Sorry, I could not generate an image from your prompt.'
        await self.db.add_stats(user_id, images_generated=1, cost_usd=self._image_price())
        try:
            messages = await self._prepare_history(user_id)
            messages.append({'role': 'assistant',
                             'content': f'<system: an image was generated from the prompt: {prompt}>'})
            await self.db.save_history(user_id, messages)
        except Exception:
            logger.exception('Could not record generated image in history')
        return base64.b64decode(b64_image), text

    async def delete_chat(self, user_id: int) -> bool:
        if self.cfg.logging.log_chats:
            await self._dump_chat(user_id)
        return await self.db.delete_history(user_id)

    async def _dump_chat(self, user_id: int) -> None:
        from datetime import datetime
        messages = await self.db.get_history(user_id)
        if not messages:
            return
        try:
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            with open(f'./data/chats/{user_id}_{stamp}.txt', 'w', encoding='utf-8') as f:
                for m in messages:
                    f.write(f"{m.get('role')}: {message_text(m)}\n")
        except OSError:
            logger.exception(f'Could not dump chat for user {user_id}')

    async def set_style(self, user_id: int, style_name: str | None) -> bool:
        if style_name is not None and style_name not in self.cfg.styles:
            return False
        await self.db.set_style(user_id, style_name)
        await self.delete_chat(user_id)
        return True

    async def stats_text(self, user_id: int) -> str | None:
        stats = await self.db.get_stats(user_id)
        if stats is None:
            return None
        lines = [f"Messages sent: {stats['messages_sent']}"]
        if self.audio_engine is not None:
            lines.append(f"Voice messages sent: {stats['voice_messages_sent']}")
            lines.append(f"Speech to text seconds: {round(stats['speech2text_seconds'])}")
        lines.append(f"Prompt tokens used: {stats['prompt_tokens']}")
        lines.append(f"Completion tokens used: {stats['completion_tokens']}")
        if self.image_engine is not None:
            lines.append(f"Images generated: {stats['images_generated']}")
        lines.append(f"\nApproximate cost of usage is ${round(stats['cost_usd'], 4)}")
        return '\n'.join(lines)
