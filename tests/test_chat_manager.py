from sirchatalot.chat_manager import ChatManager
from sirchatalot.model_registry import ModelRegistry
from tests.conftest import make_config
from tests.test_agent import FakeEngine, text_result, tool_call_result


def make_manager(db, primary_script, cfg=None, **kwargs):
    cfg = cfg or make_config()
    registry = ModelRegistry(cfg, db)
    registry.engines['primary'] = FakeEngine(cfg.model_spec('primary'), primary_script)
    registry.engines['backup'] = FakeEngine(cfg.model_spec('backup'), [])
    return ChatManager(cfg, db, registry, **kwargs), registry


async def test_process_text_full_turn(db):
    manager, registry = make_manager(db, [text_result('greetings!')])
    outcome = await manager.process_text(1, 'hello')
    assert outcome.text == 'greetings!'
    # history persisted with the system message first
    history = await db.get_history(1)
    assert history[0]['role'] == 'system'
    assert history[-1] == {'role': 'assistant', 'content': 'greetings!'}
    # stats recorded with cost from spec prices (10 prompt * $1/M + 5 completion * $2/M)
    stats = await db.get_stats(1)
    assert stats['messages_sent'] == 1
    assert abs(stats['cost_usd'] - (10 * 1.0 + 5 * 2.0) / 1_000_000) < 1e-12


async def test_style_changes_system_message(db):
    cfg = make_config(styles={'Pirate': {
        'description': 'arr', 'system_message': 'You are a pirate.'}})
    manager, _ = make_manager(db, [text_result('arr'), text_result('arr again')], cfg=cfg)
    assert await manager.set_style(1, 'Pirate')
    await manager.process_text(1, 'hi')
    history = await db.get_history(1)
    assert history[0]['content'].startswith('You are a pirate.')
    assert not await manager.set_style(1, 'Ghost')


async def test_delete_chat(db):
    manager, _ = make_manager(db, [text_result('x')])
    await manager.process_text(1, 'hi')
    assert await manager.delete_chat(1) is True
    assert await db.get_history(1) is None
    assert await manager.delete_chat(1) is False


async def test_second_turn_keeps_history(db):
    manager, registry = make_manager(db, [text_result('one'), text_result('two')])
    await manager.process_text(1, 'first')
    await manager.process_text(1, 'second')
    history = await db.get_history(1)
    roles = [m['role'] for m in history]
    assert roles == ['system', 'user', 'assistant', 'user', 'assistant']
    # the engine saw the persisted first exchange on the second call
    second_call = registry.engines['primary'].calls[1]['messages']
    assert any(m.get('content') == 'first' for m in second_call)
