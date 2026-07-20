'''Tests for agent improvements: statuses, dedup, budget, truncation, read_file.'''

import json

from sirchatalot.agent import describe_calls, run_turn
from sirchatalot.engine import ChatResult, Usage
from sirchatalot.tools import ToolContext, ToolRegistry, ToolResult
from tests.conftest import make_config
from tests.test_agent import make_registry, text_result, tool_call_result
from tests.test_chat_manager import make_manager


def counting_tools():
    tools = ToolRegistry()
    calls = []
    schema = {'type': 'function', 'function': {
        'name': 'echo', 'description': 'echo',
        'parameters': {'type': 'object', 'properties': {'text': {'type': 'string'}},
                       'required': ['text']}}}

    @tools.register(schema)
    async def echo(ctx, text):
        calls.append(text)
        return ToolResult(for_model=f'echo: {text}')

    return tools, calls


def parallel_same_calls():
    return ChatResult(message={
        'role': 'assistant', 'content': None,
        'tool_calls': [
            {'id': 'a', 'type': 'function',
             'function': {'name': 'echo', 'arguments': '{"text": "same"}'}},
            {'id': 'b', 'type': 'function',
             'function': {'name': 'echo', 'arguments': '{"text": "same"}'}},
        ]}, usage=Usage(10, 5))


async def test_duplicate_calls_dispatched_once(db):
    tools, calls = counting_tools()
    registry = make_registry(db, [parallel_same_calls(), text_result('done')])
    outcome = await run_turn(1, [{'role': 'user', 'content': 'hi'}], registry,
                             tools, ToolContext(user_id=1))
    assert calls == ['same']                     # dispatched once
    tool_messages = [m for m in outcome.messages if m['role'] == 'tool']
    assert len(tool_messages) == 2               # but both calls got an answer
    assert all(m['content'] == 'echo: same' for m in tool_messages)


async def test_duplicate_across_iterations_cached(db):
    tools, calls = counting_tools()
    same = tool_call_result('echo', {'text': 'x'})
    registry = make_registry(db, [same, same, text_result('done')])
    await run_turn(1, [{'role': 'user', 'content': 'hi'}], registry,
                   tools, ToolContext(user_id=1))
    assert calls == ['x']


async def test_token_budget_forces_final(db):
    tools, calls = counting_tools()
    registry = make_registry(db, [
        tool_call_result('echo', {'text': 'a'}),
        text_result('forced final'),
    ])
    outcome = await run_turn(1, [{'role': 'user', 'content': 'hi'}], registry,
                             tools, ToolContext(user_id=1),
                             max_iterations=5, max_turn_tokens=10)
    # first completion used 15 tokens >= 10, so no second tool round happened
    assert outcome.text == 'forced final'
    assert registry.engines['primary'].calls[-1]['tools'] is None


async def test_status_callback_receives_tool_activity(db):
    tools, _ = counting_tools()
    registry = make_registry(db, [
        tool_call_result('echo', {'text': 'ping'}),
        text_result('done'),
    ])
    statuses = []

    async def on_status(text):
        statuses.append(text)

    await run_turn(1, [{'role': 'user', 'content': 'hi'}], registry, tools,
                   ToolContext(user_id=1), on_status=on_status)
    assert statuses and 'echo' in statuses[0]


def test_describe_calls_labels():
    calls = [
        {'function': {'name': 'web_search', 'arguments': json.dumps({'query': 'cats'})}},
        {'function': {'name': 'url_opener', 'arguments': json.dumps({'url': 'https://x'})}},
        {'function': {'name': 'read_file', 'arguments': json.dumps({'filename': 'a.pdf'})}},
        {'function': {'name': 'mcp__srv__tool', 'arguments': '{}'}},
        {'function': {'name': 'echo', 'arguments': 'broken{'}},
    ]
    text = describe_calls(calls)
    assert 'cats' in text and 'https://x' in text and 'a.pdf' in text
    assert 'srv' in text and 'echo' in text


async def test_old_tool_results_truncated(db):
    from tests.test_agent import FakeEngine
    cfg = make_config(agent={'tool_result_keep_chars': 20})
    manager, registry = make_manager(db, [], cfg=cfg)
    # first turn: a tool call whose result is long (uses the real global registry
    # via chat manager, so seed history manually instead)
    long_result = 'x' * 200
    await db.save_history(1, [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'q1'},
        {'role': 'assistant', 'content': None,
         'tool_calls': [{'id': 't1', 'type': 'function',
                         'function': {'name': 'f', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 't1', 'content': long_result},
        {'role': 'assistant', 'content': 'a1'},
    ])
    registry.engines['primary'].script = [text_result('a2')]
    await manager.process_text(1, 'q2')
    history = await db.get_history(1)
    tool_message = next(m for m in history if m.get('role') == 'tool')
    assert len(tool_message['content']) <= 20 + len('… [truncated]')
    assert tool_message['content'].endswith('[truncated]')


async def test_read_file_tool(tmp_path):
    from sirchatalot.files.rag import FilesRAG
    from tests.test_rag import FakeEmbeddings, files_config
    rag = FilesRAG(files_config(), FakeEmbeddings(), chromadb_path=str(tmp_path / 'c'))
    text = '\n\n'.join(f'paragraph {i} ' + 'words ' * 30 for i in range(20))
    await rag.process_text(text, 'u1', 'long.txt')

    result = await rag.read_file('u1', 'long.txt', part=1, part_chars=500)
    assert result is not None
    page, current, total = result
    assert current == 1 and total > 1 and len(page) <= 500
    # last part reachable, out-of-range clamps
    last = await rag.read_file('u1', 'long.txt', part=999, part_chars=500)
    assert last[1] == last[2]
    # unknown file
    assert await rag.read_file('u1', 'ghost.txt') is None
    # common files readable by any user
    await rag.process_text('shared text here', 'common', 'shared.txt')
    shared = await rag.read_file('u1', 'shared.txt')
    assert shared is not None and 'shared text' in shared[0]
