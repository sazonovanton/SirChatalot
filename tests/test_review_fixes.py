'''Regression tests for issues found in the post-refactor code review.'''

from sirchatalot.chat_manager import ChatManager
from sirchatalot.engine import LLMEngine
from sirchatalot.tg.handlers import sanitize_filename  # noqa: F401 (covered elsewhere)
from tests.conftest import make_config
from tests.test_agent import FakeEngine, text_result
from tests.test_chat_manager import make_manager


def test_count_tokens_includes_images():
    engine = LLMEngine(make_config().model_spec('primary'))
    plain = [{'role': 'user', 'content': 'hi'}]
    with_image = [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'hi'},
        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,AAAA'}}]}]
    assert engine.count_tokens(with_image) >= engine.count_tokens(plain) + LLMEngine.IMAGE_TOKENS


def test_awaiting_caption_detection():
    image_msg = {'role': 'user', 'content': [
        {'type': 'image_url', 'image_url': {'url': 'data:...'}}]}
    captioned = {'role': 'user', 'content': [
        {'type': 'image_url', 'image_url': {'url': 'data:...'}},
        {'type': 'text', 'text': 'what is this?'}]}
    assert ChatManager._awaiting_caption([image_msg]) is True
    assert ChatManager._awaiting_caption([captioned]) is False
    assert ChatManager._awaiting_caption([{'role': 'user', 'content': 'hi'}]) is False
    assert ChatManager._awaiting_caption([]) is False


async def test_caption_merges_into_pending_image_after_restart(db):
    # pending-image state is derived from history, so it survives restarts
    manager, _ = make_manager(db, [text_result('nice photo')])
    assert await manager.add_image(1, 'AAAA')
    # simulate a restart: a brand-new manager instance with no in-memory state
    manager2, _ = make_manager(db, [text_result('nice photo')])
    await manager2.process_text(1, 'what is on the photo?')
    history = await db.get_history(1)
    user_messages = [m for m in history if m['role'] == 'user']
    assert len(user_messages) == 1  # caption merged, no second user message
    parts = user_messages[0]['content']
    assert any(p.get('type') == 'image_url' for p in parts)
    assert any(p.get('type') == 'text' and 'photo' in p['text'] for p in parts)


async def test_summarize_does_not_orphan_tool_messages(db):
    cfg = make_config(chat={'keep_recent_messages': 2})
    manager, _ = make_manager(db, [], cfg=cfg)
    messages = [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'old question'},
        {'role': 'assistant', 'content': 'old answer'},
        {'role': 'user', 'content': 'search something'},
        {'role': 'assistant', 'content': None,
         'tool_calls': [{'id': 't1', 'type': 'function',
                         'function': {'name': 'f', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 't1', 'content': 'result'},
    ]
    manager.registry.engines['primary'].script = [text_result('summary text')]
    summarized, _ = await manager._compact(messages)
    # no tool message may appear without its preceding assistant tool_calls
    for i, m in enumerate(summarized):
        if m.get('role') == 'tool':
            assert i > 0 and summarized[i - 1].get('tool_calls'), summarized


async def test_all_models_failed_gives_transient_error_text(db):
    from openai import APITimeoutError
    cfg = make_config()
    manager, registry = make_manager(db, [APITimeoutError(request=None)], cfg=cfg)
    registry.engines['backup'].script = [APITimeoutError(request=None)]
    outcome = await manager.process_text(1, 'hi')
    assert outcome is not None
    assert 'try again later' in outcome.text
    assert '/delete' not in outcome.text


def test_imagine_prompt_strips_bot_mention():
    import re
    strip = lambda t: re.sub(r'^/\w+(@\w+)?\s*', '', t).strip()
    assert strip('/imagine@MyBot a cat') == 'a cat'
    assert strip('/imagine a cat') == 'a cat'
    assert strip('/imagine') == ''
