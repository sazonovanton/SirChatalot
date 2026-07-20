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


READ_SCHEMA = {
    'type': 'function',
    'function': {
        'name': 'read_file',
        'description': 'Read an uploaded document page by page (reassembled from its '
                       'chunks). Use it when semantic search is not enough — e.g. to '
                       'summarize a whole document or read it sequentially.',
        'parameters': {
            'type': 'object',
            'properties': {
                'filename': {
                    'type': 'string',
                    'description': 'Exact name of the file (see the available files list)',
                },
                'part': {
                    'type': 'integer',
                    'description': 'Page number to read, starting from 1',
                    'default': 1,
                },
            },
            'required': ['filename'],
        },
    },
}


@registry.register(READ_SCHEMA, requires='files_rag')
async def read_file(ctx: ToolContext, filename: str, part: int | None = None) -> ToolResult:
    result = await ctx.files_rag.read_file(filename=filename, user_id=ctx.user_id,
                                           part=part or 1)
    if result is None:
        return ToolResult(for_model=f'File not found: {filename}')
    text, current, total = result
    return ToolResult(for_model=f'[{filename} — part {current} of {total}]\n{text}')


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
