'''
Tool registry for the agent loop.

Each tool module registers its OpenAI "function" schema together with its async
handler; MCP servers register their tools at startup. ChatManager builds a
ToolContext with the configured services and the per-user disabled set, and the
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
    memory: Any = None            # memory.MemoryStore
    summary: Callable[[str], Awaitable[str]] | None = None
    url_summarize: bool = False
    rag_results: int = 4
    disabled: set[str] = field(default_factory=set)  # per-user disabled group keys


Handler = Callable[..., Awaitable[ToolResult]]


@dataclass
class ToolEntry:
    schema: dict
    handler: Handler
    requires: str | None    # ToolContext attribute that must be set, or None
    group: str              # /tools toggle key: tool name, or MCP server name
    pass_raw_args: bool = False  # MCP tools take arguments as one dict


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}

    def register(self, schema: dict, requires: str | None = None,
                 group: str | None = None):
        '''
        Decorator. `schema` is the OpenAI tool dict; `requires` names the ToolContext
        attribute that must be set for the tool to be offered to the model; `group`
        is the /tools toggle key (defaults to the tool name).
        '''
        name = schema['function']['name']

        def decorator(handler: Handler) -> Handler:
            self._tools[name] = ToolEntry(schema, handler, requires, group or name)
            return handler
        return decorator

    def register_mcp_tool(self, server: str, schema: dict, handler: Handler) -> None:
        name = schema['function']['name']
        self._tools[name] = ToolEntry(schema, handler, requires=None,
                                      group=server, pass_raw_args=True)

    def unregister_group(self, group: str) -> None:
        self._tools = {n: e for n, e in self._tools.items() if e.group != group}

    def groups(self, ctx: ToolContext) -> list[str]:
        '''Toggle keys of the tools available in this deployment (ignoring `disabled`).'''
        seen = []
        for entry in self._tools.values():
            if entry.requires is not None and getattr(ctx, entry.requires, None) is None:
                continue
            if entry.group not in seen:
                seen.append(entry.group)
        return seen

    def _available(self, ctx: ToolContext, entry: ToolEntry) -> bool:
        if entry.group in ctx.disabled:
            return False
        return entry.requires is None or getattr(ctx, entry.requires, None) is not None

    def enabled_schemas(self, ctx: ToolContext) -> list[dict]:
        return [e.schema for e in self._tools.values() if self._available(ctx, e)]

    async def dispatch(self, ctx: ToolContext, name: str, arguments_json: str) -> ToolResult:
        entry = self._tools.get(name)
        if entry is None:
            logger.warning(f'Model called unknown tool: {name}')
            return ToolResult(for_model=f'Unknown tool: {name}')
        if not self._available(ctx, entry):
            return ToolResult(for_model=f'Tool {name} is not available')
        try:
            args = json.loads(arguments_json) if arguments_json else {}
            if not isinstance(args, dict):
                raise ValueError('arguments must be an object')
        except (json.JSONDecodeError, ValueError) as e:
            return ToolResult(for_model=f'Invalid tool arguments: {e}')
        try:
            if entry.pass_raw_args:
                return await entry.handler(ctx, args)
            # drop hallucinated arguments instead of crashing the handler
            accepted = inspect.signature(entry.handler).parameters
            args = {k: v for k, v in args.items() if k in accepted}
            return await entry.handler(ctx, **args)
        except Exception as e:
            logger.exception(f'Tool {name} failed')
            return ToolResult(for_model=f'Tool {name} failed: {e}')


registry = ToolRegistry()

# importing the modules registers their tools
from sirchatalot.tools import image_gen, memory_tool, rag_search, web  # noqa: E402,F401
