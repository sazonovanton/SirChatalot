'''Tests for MarkdownV2 rendering, /retry & /undo, and search providers.'''

import pytest

from sirchatalot.config import UrlOpenConfig, WebSearchConfig
from sirchatalot.tg.utils import SOURCE_CHUNK_LENGTH, split_for_telegram
from sirchatalot.tools.web import (
    BraveSearch,
    GoogleSearch,
    SearxngSearch,
    TavilySearch,
    make_search_engine,
)
from tests.conftest import make_config
from tests.test_agent import text_result
from tests.test_chat_manager import make_manager


# ---- markdown ----

def test_markdownify_produces_valid_v2():
    import telegramify_markdown
    out = telegramify_markdown.markdownify(
        '# Title\n**bold** _it_ `code`\n\n```python\nprint("hi")\n```\n\n- a\n- b\n\n'
        'A dot. And (parens) and 1+1=2!')
    # unescaped markdown-v2 specials outside entities would break sending;
    # dots and parens in plain text must come back escaped
    assert '\\.' in out and '\\(' in out
    assert '```python' in out


def test_split_for_telegram_prefers_paragraphs():
    # a paragraph boundary in the second half of the limit is used as the cut
    para = 'y' * (SOURCE_CHUNK_LENGTH - 100)
    text = para + '\n\n' + 'x' * 500 + '\n\npara three'
    parts = split_for_telegram(text)
    assert all(len(p) <= SOURCE_CHUNK_LENGTH for p in parts)
    assert parts[0] == para
    assert ''.join(parts).replace('\n', '') == text.replace('\n', '')


def test_split_for_telegram_short_text():
    assert split_for_telegram('hello') == ['hello']
    assert split_for_telegram('') == []


# ---- retry / undo ----

async def test_undo_removes_last_exchange(db):
    manager, _ = make_manager(db, [text_result('one'), text_result('two')])
    await manager.process_text(1, 'first')
    await manager.process_text(1, 'second')
    assert await manager.undo(1) is True
    history = await db.get_history(1)
    contents = [m['content'] for m in history if m['role'] != 'system']
    assert contents == ['first', 'one']
    assert await manager.undo(1) is True
    assert [m for m in await db.get_history(1) if m['role'] == 'user'] == []
    assert await manager.undo(1) is False


async def test_retry_regenerates_last_answer(db):
    manager, registry = make_manager(
        db, [text_result('first answer'), text_result('better answer')])
    await manager.process_text(1, 'question')
    outcome = await manager.retry(1)
    assert outcome.text == 'better answer'
    history = await db.get_history(1)
    contents = [m['content'] for m in history if m['role'] != 'system']
    # the old answer is replaced, the question is not duplicated
    assert contents == ['question', 'better answer']


async def test_retry_with_empty_history(db):
    manager, _ = make_manager(db, [])
    assert await manager.retry(1) is None


async def test_retry_drops_tool_tail(db):
    from tests.test_agent import tool_call_result
    manager, _ = make_manager(db, [
        tool_call_result('echo', {'text': 'x'}),  # ignored: no echo tool in real registry
        text_result('with tool'),
        text_result('clean retry'),
    ])
    await manager.process_text(1, 'do it')
    outcome = await manager.retry(1)
    assert outcome.text == 'clean retry'
    history = await db.get_history(1)
    assert history[-1]['content'] == 'clean retry'
    assert [m['content'] for m in history if m['role'] == 'user'] == ['do it']


# ---- search providers ----

def test_search_factory_and_validation():
    assert isinstance(make_search_engine(WebSearchConfig(
        provider='google', api_key='k', cse_id='c')), GoogleSearch)
    assert isinstance(make_search_engine(WebSearchConfig(
        provider='searxng', url='http://x')), SearxngSearch)
    assert isinstance(make_search_engine(WebSearchConfig(
        provider='tavily', api_key='k')), TavilySearch)
    assert isinstance(make_search_engine(WebSearchConfig(
        provider='brave', api_key='k')), BraveSearch)
    with pytest.raises(Exception, match='api_key and cse_id'):
        WebSearchConfig(provider='google')
    with pytest.raises(Exception, match='url'):
        WebSearchConfig(provider='searxng')
    with pytest.raises(Exception, match='api_key'):
        WebSearchConfig(provider='brave')
    with pytest.raises(Exception, match='unknown'):
        WebSearchConfig(provider='bing', api_key='k')


def test_search_parsers():
    google = GoogleSearch(WebSearchConfig(provider='google', api_key='k', cse_id='c'))
    assert google._parse({'items': [{'title': 't', 'link': 'l', 'snippet': 's'}]}) == \
        [{'title': 't', 'link': 'l', 'snippet': 's'}]
    searx = SearxngSearch(WebSearchConfig(provider='searxng', url='http://x'))
    assert searx._parse({'results': [{'title': 't', 'url': 'l', 'content': 's'}]}) == \
        [{'title': 't', 'link': 'l', 'snippet': 's'}]
    tavily = TavilySearch(WebSearchConfig(provider='tavily', api_key='k'))
    assert tavily._parse({'results': [{'title': 't', 'url': 'l', 'content': 's'}]}) == \
        [{'title': 't', 'link': 'l', 'snippet': 's'}]
    brave = BraveSearch(WebSearchConfig(provider='brave', api_key='k'))
    assert brave._parse({'web': {'results': [
        {'title': 't', 'url': 'l', 'description': 's'}]}}) == \
        [{'title': 't', 'link': 'l', 'snippet': 's'}]
    assert brave._parse({}) == []


def test_url_open_config_jina_defaults():
    cfg = UrlOpenConfig()
    assert cfg.via_jina is True
    assert cfg.jina_api_key is None


async def test_answer_message_tracking_and_deletion():
    from types import SimpleNamespace
    from sirchatalot.tg.handlers import _track, _delete_tracked

    deleted = []
    app = SimpleNamespace(bot_data={})
    bot = SimpleNamespace()
    async def delete_message(chat_id, message_id):
        deleted.append(message_id)
    bot.delete_message = delete_message
    context = SimpleNamespace(application=app, bot=bot)
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=42))

    _track(context, user_id=7, messages=[SimpleNamespace(message_id=101),
                                         SimpleNamespace(message_id=102)])
    assert app.bot_data['answer_ids'][7] == [101, 102]

    await _delete_tracked(update, context, user_id=7)
    assert deleted == [101, 102]
    # popped: a second call deletes nothing and does not raise
    await _delete_tracked(update, context, user_id=7)
    assert deleted == [101, 102]


async def test_delete_tracked_swallows_errors():
    from types import SimpleNamespace
    from sirchatalot.tg.handlers import _track, _delete_tracked

    app = SimpleNamespace(bot_data={})
    bot = SimpleNamespace()
    async def delete_message(chat_id, message_id):
        raise RuntimeError('message too old to delete')
    bot.delete_message = delete_message
    context = SimpleNamespace(application=app, bot=bot)
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=1))
    _track(context, 7, [SimpleNamespace(message_id=1)])
    await _delete_tracked(update, context, 7)  # must not raise
