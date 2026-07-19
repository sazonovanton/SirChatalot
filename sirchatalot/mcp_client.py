'''
MCP (Model Context Protocol) client support.

Servers are declared in config.yaml under mcp_servers (stdio or streamable-http).
At startup each server is connected, its tools are listed and registered in the
ToolRegistry under the name mcp__<server>__<tool>; the whole server can be
toggled per user with /tools (group key = server name).
'''

import asyncio
from contextlib import AsyncExitStack

from sirchatalot.config import McpServerConfig
from sirchatalot.logging_setup import get_logger
from sirchatalot.tools import ToolRegistry, ToolResult

logger = get_logger('mcp')


def _openai_schema(server: str, tool) -> dict:
    return {
        'type': 'function',
        'function': {
            'name': f'mcp__{server}__{tool.name}',
            'description': (tool.description or tool.name)[:1024],
            'parameters': tool.inputSchema or {'type': 'object', 'properties': {}},
        },
    }


class MCPManager:
    def __init__(self, servers: list[McpServerConfig], registry: ToolRegistry):
        self.servers = servers
        self.registry = registry
        self._stack = AsyncExitStack()
        self._sessions: dict[str, object] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.connected: list[str] = []

    async def start(self) -> None:
        '''Connect all configured servers; a failing server is skipped with a log.'''
        for server in self.servers:
            try:
                await self._connect(server)
            except Exception as e:
                logger.error(f'Could not connect MCP server "{server.name}": {e}')

    async def _connect(self, server: McpServerConfig) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamablehttp_client

        if server.command:
            transport = await self._stack.enter_async_context(stdio_client(
                StdioServerParameters(command=server.command, args=server.args,
                                      env=server.env or None)))
            read, write = transport
        else:
            transport = await self._stack.enter_async_context(
                streamablehttp_client(server.url, headers=server.headers or None))
            read, write = transport[0], transport[1]

        session = await self._stack.enter_async_context(ClientSession(read, write))
        async with asyncio.timeout(server.timeout_seconds):
            await session.initialize()
            tools = (await session.list_tools()).tools
        self._sessions[server.name] = session
        self._locks[server.name] = asyncio.Lock()
        for tool in tools:
            self.registry.register_mcp_tool(
                server.name, _openai_schema(server.name, tool),
                self._make_handler(server, tool.name))
        self.connected.append(server.name)
        logger.info(f'MCP server "{server.name}" connected with '
                    f'{len(tools)} tools: {[t.name for t in tools]}')

    def _make_handler(self, server: McpServerConfig, tool_name: str):
        async def handler(ctx, args: dict) -> ToolResult:
            session = self._sessions.get(server.name)
            if session is None:
                return ToolResult(for_model=f'MCP server {server.name} is not connected')
            # MCP sessions are not safe for concurrent requests over one pipe
            async with self._locks[server.name]:
                async with asyncio.timeout(server.timeout_seconds):
                    result = await session.call_tool(tool_name, args or {})
            texts = [c.text for c in result.content if getattr(c, 'text', None)]
            text = '\n'.join(texts) or '(no text content)'
            if getattr(result, 'isError', False):
                return ToolResult(for_model=f'Tool error: {text}')
            return ToolResult(for_model=text[:20000])
        return handler

    async def stop(self) -> None:
        for name in self.connected:
            self.registry.unregister_group(name)
        self._sessions.clear()
        try:
            await self._stack.aclose()
        except Exception as e:
            logger.warning(f'Error closing MCP connections: {e}')
