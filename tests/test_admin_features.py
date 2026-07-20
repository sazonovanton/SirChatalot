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


async def test_reindex_on_embeddings_change(db, tmp_path):
    from sirchatalot.app import reindex_if_embeddings_changed, embeddings_fingerprint
    from sirchatalot.files.extract import FilesProcessor
    from sirchatalot.files.rag import FilesRAG
    from sirchatalot.tg.services import Services
    from tests.conftest import make_config
    from tests.test_rag import FakeEmbeddings, files_config

    cfg = make_config(files={'embeddings': {'api_key': 'k', 'model': 'model-A'}})
    rag = FilesRAG(files_config(), FakeEmbeddings(), chromadb_path=str(tmp_path / 'c'))
    services = Services(cfg=cfg, db=db, registry=None, chat=None,
                        files_proc=FilesProcessor(), files_rag=rag)
    files_dir = tmp_path / 'files'

    # first start on an empty store: fingerprint recorded, no reindex needed
    await reindex_if_embeddings_changed(services, files_dir=str(files_dir))
    assert await db.get_meta('embeddings_fingerprint') == embeddings_fingerprint(cfg)

    # user uploads a file (simulated)
    (files_dir / '7').mkdir(parents=True)
    (files_dir / '7' / 'doc.txt').write_text('apple pie recipe text', encoding='utf-8')
    await rag.process_text('apple pie recipe text', '7', 'doc.txt')
    await db.upsert_file('7', 'doc.txt', 'summary', True)
    # plus a registered file whose source is gone
    await db.upsert_file('7', 'ghost.txt', None, True)
    assert await rag.count() > 0

    # model changes -> reindex drops old vectors and re-embeds from disk
    cfg2 = make_config(files={'embeddings': {'api_key': 'k', 'model': 'model-B'}})
    services.cfg = cfg2
    await reindex_if_embeddings_changed(services, files_dir=str(files_dir))

    assert await db.get_meta('embeddings_fingerprint') == embeddings_fingerprint(cfg2)
    assert await rag.user_files('7') == ['doc.txt']       # re-embedded
    names = [f['filename'] for f in await db.list_files('7')]
    assert names == ['doc.txt']                            # ghost dropped from registry
    hits = await rag.semantic_search('apple', user_id='7')
    assert hits and hits[0].filename == 'doc.txt'

    # same fingerprint -> no-op (vectors survive)
    await reindex_if_embeddings_changed(services, files_dir=str(files_dir))
    assert await rag.user_files('7') == ['doc.txt']


def test_fingerprint_shape():
    from sirchatalot.app import embeddings_fingerprint
    from tests.conftest import make_config
    a = embeddings_fingerprint(make_config(files={'embeddings': {'model': 'm1'}}))
    b = embeddings_fingerprint(make_config(files={'embeddings': {'model': 'm2'}}))
    c = embeddings_fingerprint(make_config(files={'embeddings': {'provider': 'local'}}))
    assert a != b and a != c and b != c


async def test_context_block_has_time_and_username(db):
    from tests.conftest import make_config
    from tests.test_chat_manager import make_manager
    from tests.test_agent import text_result
    cfg = make_config()
    manager, _ = make_manager(db, [text_result('hi')], cfg=cfg)
    await db.set_user_identity(1, 'John Doe', 'johnd')
    await manager.process_text(1, 'hello')
    system = (await db.get_history(1))[0]['content']
    assert 'Current date and time' in system
    assert 'John Doe' in system and '@johnd' in system


async def test_user_identity_storage(db):
    assert await db.get_user_identity(1) == (None, None)
    await db.set_user_identity(1, 'Alice', 'alice_tg')
    assert await db.get_user_identity(1) == ('Alice', 'alice_tg')
    # updates in place, does not clobber other user columns
    await db.set_selected_model(1, 'backup')
    await db.set_user_identity(1, 'Alice Smith', 'alice_tg')
    assert await db.get_user_identity(1) == ('Alice Smith', 'alice_tg')
    assert await db.get_selected_model(1) == 'backup'


async def test_image_not_found_message():
    from types import SimpleNamespace
    import openai
    from sirchatalot.config import ImageGenConfig
    from sirchatalot.media.images import ImageEngine

    engine = ImageEngine(ImageGenConfig(api_key='k', api='chat', model='text-only-model'))

    async def raise_not_found(*a, **k):
        raise openai.NotFoundError(
            'no modalities', response=SimpleNamespace(status_code=404, request=None,
                                                      headers={}), body=None)
    engine.client.chat.completions.create = raise_not_found
    b64, text = await engine._generate('a cat', '1024x1024', 'vivid', 'standard', None)
    assert b64 is None
    assert 'does not support image generation' in text
