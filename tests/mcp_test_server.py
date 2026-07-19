'''Tiny stdio MCP server used by test_mcp.py.'''

from mcp.server.fastmcp import FastMCP

mcp = FastMCP('testsrv')


@mcp.tool()
def add(a: int, b: int) -> int:
    '''Add two numbers.'''
    return a + b


@mcp.tool()
def fail() -> str:
    '''Always raises.'''
    raise RuntimeError('boom')


if __name__ == '__main__':
    mcp.run()
