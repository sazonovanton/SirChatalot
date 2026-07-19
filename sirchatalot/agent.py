'''
The agent loop: lets the model call tools across multiple bounded iterations
using the modern OpenAI tools protocol (assistant message with tool_calls,
role:"tool" results, parallel calls supported).
'''

import asyncio
from dataclasses import dataclass, field

from sirchatalot.config import ModelSpec
from sirchatalot.engine import Usage
from sirchatalot.logging_setup import get_logger
from sirchatalot.model_registry import ModelRegistry
from sirchatalot.tools import ToolContext, ToolRegistry

logger = get_logger('agent')


@dataclass
class AgentOutcome:
    text: str
    messages: list
    spec: ModelSpec
    usage: Usage = field(default_factory=Usage)
    media: list[bytes] = field(default_factory=list)
    images_generated: int = 0


async def run_turn(user_id: int, messages: list, registry: ModelRegistry,
                   tools: ToolRegistry, ctx: ToolContext, max_iterations: int = 5,
                   end_user: str | None = None) -> AgentOutcome:
    '''
    Run one conversation turn. `messages` is mutated in place (assistant/tool
    messages are appended) and returned inside the outcome for persistence.
    '''
    total_usage = Usage()
    media: list[bytes] = []
    images_generated = 0
    schemas = tools.enabled_schemas(ctx)

    for iteration in range(max_iterations):
        result, spec = await registry.complete(
            user_id, messages, tools=schemas or None, end_user=end_user
        )
        total_usage += result.usage
        assistant = result.message

        if not assistant.get('tool_calls'):
            messages.append({'role': 'assistant', 'content': assistant.get('content') or ''})
            return AgentOutcome(text=assistant.get('content') or '', messages=messages,
                                spec=spec, usage=total_usage, media=media,
                                images_generated=images_generated)

        messages.append(assistant)
        calls = assistant['tool_calls']
        logger.debug(f'Iteration {iteration}: model called '
                     f'{[c["function"]["name"] for c in calls]} (user {user_id})')
        results = await asyncio.gather(*[
            tools.dispatch(ctx, call['function']['name'], call['function']['arguments'])
            for call in calls
        ])
        for call, tool_result in zip(calls, results):
            messages.append({'role': 'tool', 'tool_call_id': call['id'],
                             'content': tool_result.for_model})
            media.extend(tool_result.images)
            if call['function']['name'] == 'generate_image' and tool_result.images:
                images_generated += len(tool_result.images)

    # iteration budget exhausted: force a final text answer
    logger.warning(f'Agent reached max iterations ({max_iterations}) for user {user_id}')
    result, spec = await registry.complete(user_id, messages, tools=None, end_user=end_user)
    total_usage += result.usage
    text = result.message.get('content') or ''
    messages.append({'role': 'assistant', 'content': text})
    return AgentOutcome(text=text, messages=messages, spec=spec, usage=total_usage,
                        media=media, images_generated=images_generated)
