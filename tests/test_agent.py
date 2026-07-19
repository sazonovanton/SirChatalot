import json

import pytest
from openai import APITimeoutError

from sirchatalot.agent import run_turn
from sirchatalot.engine import ChatResult, Usage, sanitize_for
from sirchatalot.model_registry import AllModelsFailedError, ModelRegistry
from sirchatalot.tools import ToolContext, ToolRegistry, ToolResult
from tests.conftest import make_config


class FakeEngine:
    '''Scripted engine: pops the next ChatResult (or raises it) per complete() call.'''

    def __init__(self, spec, script):
        self.spec = spec
        self.script = list(script)
        self.calls = []

    async def complete(self, messages, tools=None, tool_choice=None,
                       end_user=None, max_tokens=None):
        self.calls.append({'messages': [dict(m) for m in messages], 'tools': tools})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def count_tokens(self, messages):
        return sum(len(str(m.get('content', ''))) for m in messages)

    async def summary(self, text, size=420, instruction=None):
        result = await self.complete(
            [{'role': 'system', 'content': instruction or 'summarize'},
             {'role': 'user', 'content': str(text)}])
        return result.message['content'] or '', result.usage


def text_result(text):
    return ChatResult(message={'role': 'assistant', 'content': text},
                      usage=Usage(10, 5))


def tool_call_result(name, args, call_id='c1'):
    return ChatResult(message={
        'role': 'assistant', 'content': None,
        'tool_calls': [{'id': call_id, 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(args)}}],
    }, usage=Usage(10, 5))


def make_registry(db, primary_script, backup_script=()):
    cfg = make_config()
    registry = ModelRegistry(cfg, db)
    registry.engines['primary'] = FakeEngine(cfg.model_spec('primary'), primary_script)
    registry.engines['backup'] = FakeEngine(cfg.model_spec('backup'), backup_script)
    return registry


def make_tools():
    tools = ToolRegistry()
    schema = {'type': 'function', 'function': {
        'name': 'echo', 'description': 'echo',
        'parameters': {'type': 'object', 'properties': {'text': {'type': 'string'}},
                       'required': ['text']}}}

    @tools.register(schema)
    async def echo(ctx, text):
        return ToolResult(for_model=f'echo: {text}')

    return tools


async def test_plain_turn(db):
    registry = make_registry(db, [text_result('hello')])
    outcome = await run_turn(1, [{'role': 'user', 'content': 'hi'}], registry,
                             make_tools(), ToolContext(user_id=1))
    assert outcome.text == 'hello'
    assert outcome.messages[-1] == {'role': 'assistant', 'content': 'hello'}
    assert outcome.usage.prompt_tokens == 10


async def test_tool_call_loop(db):
    registry = make_registry(db, [
        tool_call_result('echo', {'text': 'ping'}),
        text_result('done'),
    ])
    messages = [{'role': 'user', 'content': 'hi'}]
    outcome = await run_turn(1, messages, registry, make_tools(), ToolContext(user_id=1))
    assert outcome.text == 'done'
    roles = [m['role'] for m in outcome.messages]
    assert roles == ['user', 'assistant', 'tool', 'assistant']
    assert outcome.messages[2]['content'] == 'echo: ping'
    assert outcome.messages[2]['tool_call_id'] == 'c1'


async def test_parallel_tool_calls(db):
    result = ChatResult(message={
        'role': 'assistant', 'content': None,
        'tool_calls': [
            {'id': 'a', 'type': 'function',
             'function': {'name': 'echo', 'arguments': '{"text": "1"}'}},
            {'id': 'b', 'type': 'function',
             'function': {'name': 'echo', 'arguments': '{"text": "2"}'}},
        ]}, usage=Usage(1, 1))
    registry = make_registry(db, [result, text_result('done')])
    outcome = await run_turn(1, [{'role': 'user', 'content': 'hi'}], registry,
                             make_tools(), ToolContext(user_id=1))
    tool_messages = [m for m in outcome.messages if m['role'] == 'tool']
    assert [m['tool_call_id'] for m in tool_messages] == ['a', 'b']
    assert [m['content'] for m in tool_messages] == ['echo: 1', 'echo: 2']


async def test_max_iterations_cutoff(db):
    loop_result = tool_call_result('echo', {'text': 'again'})
    registry = make_registry(db, [loop_result, loop_result, text_result('forced final')])
    outcome = await run_turn(1, [{'role': 'user', 'content': 'hi'}], registry,
                             make_tools(), ToolContext(user_id=1), max_iterations=2)
    assert outcome.text == 'forced final'
    # the forced final call must not offer tools
    assert registry.engines['primary'].calls[-1]['tools'] is None


async def test_fallback_on_timeout(db):
    registry = make_registry(
        db,
        [APITimeoutError(request=None)],
        [text_result('from backup')],
    )
    result, spec = await registry.complete(1, [{'role': 'user', 'content': 'hi'}])
    assert result.message['content'] == 'from backup'
    assert spec.name == 'backup'


async def test_all_models_failed(db):
    registry = make_registry(
        db,
        [APITimeoutError(request=None)],
        [APITimeoutError(request=None)],
    )
    with pytest.raises(AllModelsFailedError):
        await registry.complete(1, [{'role': 'user', 'content': 'hi'}])


async def test_user_selected_model_used(db):
    await db.set_selected_model(1, 'backup')
    registry = make_registry(db, [], [text_result('backup answer')])
    result, spec = await registry.complete(1, [{'role': 'user', 'content': 'hi'}])
    assert spec.name == 'backup'
    assert registry.engines['primary'].calls == []


async def test_removed_model_falls_back_to_default(db):
    await db.set_selected_model(1, 'deleted-model')
    registry = make_registry(db, [text_result('default answer')])
    result, spec = await registry.complete(1, [{'role': 'user', 'content': 'hi'}])
    assert spec.name == 'primary'


async def test_unknown_tool_and_bad_args(db):
    tools = make_tools()
    ctx = ToolContext(user_id=1)
    result = await tools.dispatch(ctx, 'ghost', '{}')
    assert 'Unknown tool' in result.for_model
    result = await tools.dispatch(ctx, 'echo', '{broken json')
    assert 'Invalid tool arguments' in result.for_model
    # hallucinated extra args are dropped, not fatal
    result = await tools.dispatch(ctx, 'echo', '{"text": "x", "hallucinated": true}')
    assert result.for_model == 'echo: x'


def test_sanitize_for_strips_vision_and_tools():
    cfg = make_config()
    no_caps = cfg.model_spec('backup')
    messages = [
        {'role': 'user', 'content': [
            {'type': 'text', 'text': 'look'},
            {'type': 'image_url', 'image_url': {'url': 'data:...'}}]},
        {'role': 'assistant', 'content': None,
         'tool_calls': [{'id': 't', 'type': 'function',
                         'function': {'name': 'f', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 't', 'content': 'res'},
    ]
    sanitized = sanitize_for(messages, no_caps)
    assert isinstance(sanitized[0]['content'], str)
    assert 'look' in sanitized[0]['content']
    assert 'cannot see it' in sanitized[0]['content']
    assert 'tool_calls' not in sanitized[1]
    assert sanitized[2]['role'] == 'user'
    # full-capability spec keeps everything intact
    untouched = sanitize_for(messages, cfg.model_spec('primary'))
    assert untouched[0]['content'] == messages[0]['content']
    assert 'tool_calls' in untouched[1]
