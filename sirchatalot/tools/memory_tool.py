'''save_memory tool: let the model persist lasting facts about the user.'''

from sirchatalot.tools import ToolContext, ToolResult, registry

SCHEMA = {
    'type': 'function',
    'function': {
        'name': 'save_memory',
        'description': 'Save a lasting fact about the user to persistent memory '
                       '(preferences, personal context, important details). Use it when '
                       'the user shares something worth remembering across conversations. '
                       'Keep each memory short and self-contained.',
        'parameters': {
            'type': 'object',
            'properties': {
                'content': {
                    'type': 'string',
                    'description': 'The fact to remember, one short sentence',
                },
            },
            'required': ['content'],
        },
    },
}


@registry.register(SCHEMA, requires='memory')
async def save_memory(ctx: ToolContext, content: str) -> ToolResult:
    saved = await ctx.memory.save(ctx.user_id, content)
    return ToolResult(for_model='Memory saved.' if saved
                      else 'That is already saved in memory.')
