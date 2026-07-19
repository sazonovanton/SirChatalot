import hashlib

import pytest

from sirchatalot.config import FilesConfig
from sirchatalot.files.rag import FilesRAG, chunk_text


class FakeEmbeddings:
    '''Deterministic embeddings: similar first-words map to similar vectors.'''

    async def get_embeddings(self, texts):
        return [self._vector(t) for t in texts]

    async def get_embedding(self, text):
        return self._vector(text)

    def _vector(self, text):
        seed = hashlib.md5(text.split()[0].lower().encode()).digest()
        return [b / 255 for b in seed[:8]]


def files_config(**overrides):
    data = {'embeddings': {'api_key': 'k'}, 'search_results': 4, 'max_distance': 10.0}
    data.update(overrides)
    return FilesConfig.model_validate(data)


@pytest.fixture
def rag(tmp_path):
    return FilesRAG(files_config(), FakeEmbeddings(), chromadb_path=str(tmp_path / 'chroma'))


async def test_search_sorted_and_attributed(rag):
    assert await rag.process_text('apple pie recipe', 'u1', 'apples.txt')
    assert await rag.process_text('banana bread recipe', 'u1', 'bananas.txt')
    assert await rag.process_text('apple orchard guide', 'common', 'orchard.txt')

    hits = await rag.semantic_search('apple', user_id='u1', n_results=3)
    assert hits is not None and len(hits) > 0
    # sorted ascending by distance
    distances = [h.distance for h in hits]
    assert distances == sorted(distances)
    # each hit carries its own filename ('apple ...' texts should rank first)
    assert hits[0].filename in ('apples.txt', 'orchard.txt')
    # common files are included alongside user files
    assert {h.filename for h in hits} >= {'apples.txt', 'orchard.txt'}


async def test_max_distance_filter(rag):
    await rag.process_text('apple pie recipe', 'u1', 'apples.txt')
    # 'banana' maps to a different vector -> distance > 0, filtered out
    hits = await rag.semantic_search('banana', user_id='u1', max_distance=1e-9)
    assert hits == []
    # with a permissive threshold the same hit comes back
    hits = await rag.semantic_search('banana', user_id='u1', max_distance=100.0)
    assert len(hits) == 1


async def test_other_users_files_invisible(rag):
    await rag.process_text('secret document text', 'u2', 'secret.txt')
    hits = await rag.semantic_search('secret', user_id='u1')
    assert hits == []


async def test_remove_user(rag):
    await rag.process_text('some text here', 'u1', 'a.txt')
    assert await rag.user_files('u1') == ['a.txt']
    assert await rag.remove_user('u1')
    assert await rag.user_files('u1') == []


def test_chunk_text_sizes_and_overlap():
    paragraph = 'One sentence here. ' * 10
    text = '\n\n'.join([paragraph] * 5)
    chunks = chunk_text(text, chunk_size=200, overlap_percent=0.1)
    assert len(chunks) > 1
    assert all(len(c) <= 250 for c in chunks)  # chunk_size + slack for word boundaries
    assert ''.join(chunks)  # non-empty


def test_chunk_text_oversized_paragraph():
    text = 'word ' * 500  # single huge paragraph
    chunks = chunk_text(text, chunk_size=100, overlap_percent=0.1)
    assert len(chunks) > 4
    assert all(len(c) <= 110 for c in chunks)


def test_chunk_text_empty():
    assert chunk_text('', 100, 0.1) == []
