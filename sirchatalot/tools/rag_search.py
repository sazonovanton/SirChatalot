'''semantic_search tool: search the RAG database of uploaded files.'''

from sirchatalot.tools import ToolContext, ToolResult, registry

SCHEMA = {
    'type': 'function',
    'function': {
        'name': 'semantic_search',
        'description': 'Searches for similar text chunks in the RAG database of uploaded '
                       'documents. Returns the most similar text chunks. Should be used to '
                       'find information in internal documents.',
        'parameters': {
            'type': 'object',
            'properties': {
                'text': {
                    'type': 'string',
                    'description': 'Text to search similar text chunks for',
                },
                'n_results': {
                    'type': 'integer',
                    'description': 'Number of results to return',
                    'default': 3,
                },
            },
            'required': ['text'],
        },
    },
}


@registry.register(SCHEMA, requires='files_rag')
async def semantic_search(ctx: ToolContext, text: str, n_results: int | None = None) -> ToolResult:
    hits = await ctx.files_rag.semantic_search(
        text, user_id=ctx.user_id, n_results=n_results or ctx.rag_results
    )
    if not hits:
        return ToolResult(for_model='No results found in the uploaded documents.')
    lines = []
    for hit in hits:
        lines.append(f'[{hit.filename}] (distance {hit.distance:.3f})\n{hit.document}')
    return ToolResult(for_model='\n\n'.join(lines))
