'''Tests for smart history compaction, user memory and per-user tool toggles.'''

from sirchatalot.chat_manager import SUMMARY_MARKER
from sirchatalot.config import MemoryConfig
from sirchatalot.memory import MemoryStore
from sirchatalot.tools import ToolContext, ToolRegistry, ToolResult, registry as global_registry
from tests.conftest import make_config
from tests.test_agent import text_result
from tests.test_chat_manager import make_manager


# ---- smart compaction ----

def long_history(turns: int) -> list:
    messages = [{'role': 'system', 'content': 'sys'}]
    for i in range(turns):
        messages.append({'role': 'user', 'content': f'question number {i} ' + 'blah ' * 30})
        messages.append({'role': 'assistant', 'content': f'answer number {i} ' + 'blah ' * 30})
    return messages


async def test_compact_creates_rolling_summary(db):
    cfg = make_config(chat={'keep_recent_messages': 4})
    manager, registry = make_manager(db, [text_result('rolled-up summary')], cfg=cfg)
    messages = long_history(10)
    compacted, usage = await manager._compact(messages)
    assert manager._is_summary(compacted[1])
    assert 'rolled-up summary' in compacted[1]['content']
    # system + summary + recent tail
    assert len(compacted) == 2 + 4
    assert compacted[-1] == messages[-1]
    assert usage.prompt_tokens > 0


async def test_compact_is_incremental(db):
    cfg = make_config(chat={'keep_recent_messages': 2})
    manager, registry = make_manager(
        db, [text_result('first summary'), text_result('updated summary')], cfg=cfg)
    compacted, _ = await manager._compact(long_history(6))
    # grow the tail and compact again: the previous summary must be fed to the LLM
    compacted += [{'role': 'user', 'content': 'newer question'},
                  {'role': 'assistant', 'content': 'newer answer'}]
    again, _ = await manager._compact(compacted)
    assert 'updated summary' in again[1]['content']
    sent = registry.engines['primary'].calls[1]['messages'][-1]['content']
    assert 'first summary' in sent  # old summary included for incremental update
    assert sum(1 for m in again if manager._is_summary(m)) == 1


async def test_trim_preserves_rolling_summary(db):
    cfg = make_config(chat={'keep_recent_messages': 2})
    manager, _ = make_manager(db, [], cfg=cfg)
    messages = [{'role': 'system', 'content': 'sys'},
                {'role': 'assistant', 'content': f'{SUMMARY_MARKER}: old facts'},
                {'role': 'user', 'content': 'a'},
                {'role': 'assistant', 'content': 'b'},
                {'role': 'user', 'content': 'c'}]
    trimmed = manager._trim_one(messages)
    assert manager._is_summary(trimmed[1])
    assert trimmed[2] == {'role': 'assistant', 'content': 'b'}


# ---- memory ----

async def test_memory_store_roundtrip(db):
    store = MemoryStore(MemoryConfig(max_items=3), db)
    await store.save(1, 'likes cats')
    await store.save(1, 'lives in Prague')
    memories = await store.list(1)
    assert [m['content'] for m in memories] == ['likes cats', 'lives in Prague']
    block = await store.prompt_block(1)
    assert 'likes cats' in block and 'remember about this user' in block
    assert await store.delete(1, memories[0]['id']) is True
    assert await store.clear(1) == 1
    assert await store.prompt_block(1) == ''


async def test_memory_max_items(db):
    store = MemoryStore(MemoryConfig(max_items=2), db)
    for fact in ('one', 'two', 'three'):
        await store.save(1, fact)
    assert [m['content'] for m in await store.list(1)] == ['two', 'three']


async def test_save_memory_tool_and_prompt_injection(db):
    store = MemoryStore(MemoryConfig(max_items=10), db)
    ctx = ToolContext(user_id=1, memory=store)
    result = await global_registry.dispatch(ctx, 'save_memory', '{"content": "is a vegan"}')
    assert result.for_model == 'Memory saved.'
    cfg = make_config()
    manager, _ = make_manager(db, [text_result('hi')], cfg=cfg, memory=store)
    await manager.process_text(1, 'hello')
    history = await db.get_history(1)
    assert 'is a vegan' in history[0]['content']


# ---- per-user tool toggles ----

def sample_registry() -> ToolRegistry:
    reg = ToolRegistry()
    schema = {'type': 'function', 'function': {
        'name': 'alpha', 'description': 'x',
        'parameters': {'type': 'object', 'properties': {}}}}

    @reg.register(schema)
    async def alpha(ctx):
        return ToolResult(for_model='alpha ran')

    reg.register_mcp_tool('srv', {'type': 'function', 'function': {
        'name': 'mcp__srv__beta', 'description': 'y',
        'parameters': {'type': 'object', 'properties': {}}}},
        _mcp_beta)
    return reg


async def _mcp_beta(ctx, args):
    return ToolResult(for_model='beta ran')


async def test_disabled_group_hides_and_blocks():
    reg = sample_registry()
    ctx = ToolContext(user_id=1)
    assert {s['function']['name'] for s in reg.enabled_schemas(ctx)} == \
        {'alpha', 'mcp__srv__beta'}
    assert reg.groups(ctx) == ['alpha', 'srv']

    ctx_off = ToolContext(user_id=1, disabled={'srv'})
    assert {s['function']['name'] for s in reg.enabled_schemas(ctx_off)} == {'alpha'}
    result = await reg.dispatch(ctx_off, 'mcp__srv__beta', '{}')
    assert 'not available' in result.for_model
    assert (await reg.dispatch(ctx_off, 'alpha', '{}')).for_model == 'alpha ran'


async def test_disabled_tools_persisted(db):
    await db.set_disabled_tools(1, {'web_search', 'srv'})
    assert await db.get_disabled_tools(1) == {'web_search', 'srv'}
    await db.set_disabled_tools(1, set())
    assert await db.get_disabled_tools(1) == set()


def test_unregister_group():
    reg = sample_registry()
    reg.unregister_group('srv')
    ctx = ToolContext(user_id=1)
    assert reg.groups(ctx) == ['alpha']


async def test_memory_dedup(db):
    store = MemoryStore(MemoryConfig(max_items=10), db)
    assert await store.save(1, 'likes cats') is True
    assert await store.save(1, 'likes cats') is False        # exact duplicate
    assert await store.save(1, '  Likes Cats  ') is False    # case/space-insensitive
    assert await store.save(1, 'likes dogs') is True
    assert [m['content'] for m in await store.list(1)] == ['likes cats', 'likes dogs']
