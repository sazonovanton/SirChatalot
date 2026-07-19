'''
Tool registry for the agent loop.

Each tool module registers its OpenAI "function" schema together with its async
handler; ChatManager builds a ToolContext with the configured services and the
agent dispatches calls through the registry.
'''

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sirchatalot.logging_setup import get_logger

logger = get_logger('tools')


@dataclass
class ToolResult:
    for_model: str                          # appended as the role:"tool" message content
    images: list[bytes] = field(default_factory=list)  # media to send to the user


@dataclass
class ToolContext:
    user_id: int
    user_message: str = ''
    image_engine: Any = None      # media.images.ImageEngine
    web_search: Any = None        # tools.web.GoogleSearch
    url_opener: Any = None        # tools.web.UrlOpener
    files_rag: Any = None         # files.rag.FilesRAG
    summary: Callable[[str], Awaitable[str]] | None = None
    url_summarize: bool = False
    rag_results: int = 4


Handler = Callable[..., Awaitable[ToolResult]]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, tuple[dict, Handler, str]] = {}

    def register(self, schema: dict, requires: str | None = None):
        '''
        Decorator. `schema` is the OpenAI tool dict; `requires` names the ToolContext
        attribute that must be set for the tool to be offered to the model.
        '''
        name = schema['function']['name']

        def decorator(handler: Handler) -> Handler:
            self._tools[name] = (schema, handler, requires)
            return handler
        return decorator

    def enabled_schemas(self, ctx: ToolContext) -> list[dict]:
        return [schema for schema, _, requires in self._tools.values()
                if requires is None or getattr(ctx, requires, None) is not None]

    async def dispatch(self, ctx: ToolContext, name: str, arguments_json: str) -> ToolResult:
        if name not in self._tools:
            logger.warning(f'Model called unknown tool: {name}')
            return ToolResult(for_model=f'Unknown tool: {name}')
        _, handler, requires = self._tools[name]
        if requires is not None and getattr(ctx, requires, None) is None:
            return ToolResult(for_model=f'Tool {name} is not available')
        try:
            args = json.loads(arguments_json) if arguments_json else {}
            if not isinstance(args, dict):
                raise ValueError('arguments must be an object')
        except (json.JSONDecodeError, ValueError) as e:
            return ToolResult(for_model=f'Invalid tool arguments: {e}')
        # drop hallucinated arguments instead of crashing the handler
        accepted = inspect.signature(handler).parameters
        args = {k: v for k, v in args.items() if k in accepted}
        try:
            return await handler(ctx, **args)
        except Exception as e:
            logger.exception(f'Tool {name} failed')
            return ToolResult(for_model=f'Tool {name} failed: {e}')


registry = ToolRegistry()

# importing the modules registers their tools
from sirchatalot.tools import image_gen, rag_search, web  # noqa: E402,F401
