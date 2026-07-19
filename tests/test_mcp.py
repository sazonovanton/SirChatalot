'''End-to-end MCP test against a local stdio server (tests/mcp_test_server.py).'''

import os
import sys

import pytest
import pytest_asyncio

from sirchatalot.config import McpServerConfig
from sirchatalot.mcp_client import MCPManager
from sirchatalot.tools import ToolContext, ToolRegistry

SERVER = os.path.join(os.path.dirname(__file__), 'mcp_test_server.py')


@pytest_asyncio.fixture
async def manager():
    registry = ToolRegistry()
    mgr = MCPManager(
        [McpServerConfig(name='testsrv', command=sys.executable, args=[SERVER])],
        registry,
    )
    await mgr.start()
    yield mgr, registry
    await mgr.stop()


async def test_mcp_tools_registered_and_callable(manager):
    mgr, registry = manager
    assert mgr.connected == ['testsrv']
    ctx = ToolContext(user_id=1)
    names = {s['function']['name'] for s in registry.enabled_schemas(ctx)}
    assert 'mcp__testsrv__add' in names
    assert registry.groups(ctx) == ['testsrv']

    result = await registry.dispatch(ctx, 'mcp__testsrv__add', '{"a": 2, "b": 3}')
    assert '5' in result.for_model

    # per-user disable of the whole server
    ctx_off = ToolContext(user_id=1, disabled={'testsrv'})
    assert registry.enabled_schemas(ctx_off) == []


async def test_mcp_tool_error_reported(manager):
    mgr, registry = manager
    ctx = ToolContext(user_id=1)
    result = await registry.dispatch(ctx, 'mcp__testsrv__fail', '{}')
    assert 'error' in result.for_model.lower() or 'boom' in result.for_model


async def test_mcp_bad_server_skipped():
    registry = ToolRegistry()
    mgr = MCPManager(
        [McpServerConfig(name='broken', command='/nonexistent-binary', args=[])],
        registry,
    )
    await mgr.start()  # must not raise
    assert mgr.connected == []
    await mgr.stop()


def test_mcp_config_validation():
    with pytest.raises(Exception, match='exactly one'):
        McpServerConfig(name='x')
    with pytest.raises(Exception, match='exactly one'):
        McpServerConfig(name='x', command='a', url='http://b')
    with pytest.raises(Exception, match='identifier'):
        McpServerConfig(name='bad name!', command='a')
