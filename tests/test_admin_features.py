'''Tests for local embeddings, per-file deletion and the error notifier.'''

import pytest

from sirchatalot.app import ErrorNotifier
from sirchatalot.config import EmbeddingsConfig
from sirchatalot.files.embeddings import EmbeddingsEngine, LocalEmbeddings, make_embeddings_engine
from sirchatalot.tg.handlers import _file_key


def test_embeddings_provider_validation():
    assert EmbeddingsConfig().provider == 'openai'
    assert EmbeddingsConfig(provider='local').provider == 'local'
    with pytest.raises(Exception, match='openai.*local'):
        EmbeddingsConfig(provider='ollama')


def test_embeddings_factory_dispatch(monkeypatch):
    assert isinstance(make_embeddings_engine(EmbeddingsConfig()), EmbeddingsEngine)
    # avoid downloading the ONNX model in tests
    monkeypatch.setattr(LocalEmbeddings, '__init__', lambda self: None)
    assert isinstance(make_embeddings_engine(EmbeddingsConfig(provider='local')),
                      LocalEmbeddings)


async def test_rag_remove_single_file(tmp_path):
    from sirchatalot.files.rag import FilesRAG
    from tests.test_rag import FakeEmbeddings, files_config
    rag = FilesRAG(files_config(), FakeEmbeddings(), chromadb_path=str(tmp_path / 'c'))
    await rag.process_text('apple text', 'u1', 'a.txt')
    await rag.process_text('banana text', 'u1', 'b.txt')
    assert await rag.remove_file('u1', 'a.txt')
    assert await rag.user_files('u1') == ['b.txt']


async def test_db_delete_single_file(db):
    await db.upsert_file('1', 'a.txt', None, True)
    await db.upsert_file('1', 'b.txt', None, True)
    assert await db.delete_file('1', 'a.txt') is True
    assert await db.delete_file('1', 'a.txt') is False
    assert [f['filename'] for f in await db.list_files('1')] == ['b.txt']


def test_file_key_is_short_and_stable():
    key = _file_key('очень длинное имя файла с юникодом и пробелами.pdf')
    assert key == _file_key('очень длинное имя файла с юникодом и пробелами.pdf')
    assert len(key) == 16
    assert len(f'files:del:{key}'.encode()) <= 64


def test_error_notifier_throttling(monkeypatch):
    notifier = ErrorNotifier(admin_id=1)
    times = iter([100.0, 150.0, 100.0 + ErrorNotifier.THROTTLE_SECONDS + 1])
    import time as time_module
    monkeypatch.setattr(time_module, 'time', lambda: next(times))
    assert notifier._should_notify('err') is True
    assert notifier._should_notify('err') is False       # within throttle window
    assert notifier._should_notify('err') is True        # window passed


def test_error_notifier_distinct_errors():
    notifier = ErrorNotifier(admin_id=1)
    assert notifier._should_notify('error A') is True
    assert notifier._should_notify('error B') is True    # different key not throttled
