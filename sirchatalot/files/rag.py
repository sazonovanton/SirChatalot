'''
RAG over uploaded files: chunking, ChromaDB storage and semantic search.

Fixes over the old implementation: distances are actually requested from Chroma
(so results are really sorted by relevance), nested query results are flattened
once, each hit keeps its own filename, max_distance is applied, and blocking
Chroma calls run off the event loop.
'''

import asyncio
import re
import uuid
from dataclasses import dataclass

import chromadb

from sirchatalot.config import FilesConfig
from sirchatalot.files.embeddings import EmbeddingsEngine
from sirchatalot.logging_setup import get_logger

logger = get_logger('rag')

COMMON_USER = 'common'


@dataclass
class Hit:
    document: str
    filename: str
    distance: float


class FilesRAG:
    def __init__(self, cfg: FilesConfig, embeddings: EmbeddingsEngine,
                 chromadb_path: str = './data/files/chromadb'):
        self.cfg = cfg
        self.embeddings = embeddings
        self.client = chromadb.PersistentClient(path=chromadb_path)
        self.collection = self.client.get_or_create_collection(
            name='files', embedding_function=None
        )

    async def process_text(self, text: str, user_id, filename: str) -> bool:
        '''Chunk text and insert it into the collection. Returns success.'''
        try:
            if not text or not text.strip():
                logger.warning(f'Empty text provided for file: {filename}')
                return False
            chunks = chunk_text(text, self.cfg.chunk_size, self.cfg.overlap_percent)
            if not chunks:
                logger.warning(f'No chunks generated from file: {filename}')
                return False
            metadata = [
                {'user_id': str(user_id), 'filename': filename, 'chunk_number': i + 1}
                for i in range(len(chunks))
            ]
            vectors = await self.embeddings.get_embeddings(chunks)
            ids = [str(uuid.uuid4()) for _ in chunks]
            await asyncio.to_thread(
                self.collection.add,
                ids=ids, embeddings=vectors, documents=chunks, metadatas=metadata,
            )
            logger.info(f'Processed {filename} into {len(chunks)} chunks (user {user_id})')
            return True
        except Exception:
            logger.exception(f'Error processing text from {filename}')
            return False

    async def semantic_search(self, text: str, user_id, n_results: int | None = None,
                              max_distance: float | None = None) -> list[Hit] | None:
        '''
        Search the user's and the common documents. Returns the n_results closest
        hits sorted by distance (filtered by max_distance), or None on error.
        '''
        n_results = n_results or self.cfg.search_results
        max_distance = max_distance if max_distance is not None else self.cfg.max_distance
        try:
            vector = await self.embeddings.get_embedding(text)
            owners = {str(user_id), COMMON_USER}
            results = await asyncio.gather(*[
                asyncio.to_thread(
                    self.collection.query,
                    query_embeddings=[vector],
                    n_results=n_results,
                    where={'user_id': owner},
                    include=['documents', 'metadatas', 'distances'],
                ) for owner in owners
            ])
            hits: list[Hit] = []
            for result in results:
                # Chroma returns one sublist per query embedding; we always send one
                documents = (result.get('documents') or [[]])[0]
                metadatas = (result.get('metadatas') or [[]])[0]
                distances = (result.get('distances') or [[]])[0]
                for doc, meta, dist in zip(documents, metadatas, distances):
                    if dist <= max_distance:
                        hits.append(Hit(document=doc,
                                        filename=(meta or {}).get('filename', 'unknown'),
                                        distance=dist))
            hits.sort(key=lambda h: h.distance)
            return hits[:n_results]
        except Exception:
            logger.exception('Error performing semantic search')
            return None

    async def read_file(self, user_id, filename: str, part: int = 1,
                        part_chars: int = 3000) -> tuple[str, int, int] | None:
        '''
        Read a file's text (reassembled from its chunks) page by page.
        Returns (text, part, total_parts) or None when the file is unknown.
        '''
        try:
            result = await asyncio.to_thread(
                self.collection.get,
                where={'$and': [{'filename': filename},
                                {'user_id': {'$in': [str(user_id), COMMON_USER]}}]},
                include=['documents', 'metadatas'],
            )
            documents = result.get('documents') or []
            metadatas = result.get('metadatas') or []
            if not documents:
                return None
            ordered = sorted(zip(metadatas, documents),
                             key=lambda p: (p[0] or {}).get('chunk_number', 0))
            text = '\n'.join(doc for _, doc in ordered)
            parts = [text[i:i + part_chars] for i in range(0, len(text), part_chars)] or ['']
            part = max(1, min(part, len(parts)))
            return parts[part - 1], part, len(parts)
        except Exception:
            logger.exception(f'Error reading {filename} for user {user_id}')
            return None

    async def reset(self) -> None:
        '''Drop all vectors (used when the embeddings model changes).'''
        await asyncio.to_thread(self.client.delete_collection, 'files')
        self.collection = await asyncio.to_thread(
            self.client.get_or_create_collection, name='files', embedding_function=None
        )

    async def count(self) -> int:
        return await asyncio.to_thread(self.collection.count)

    async def remove_file(self, user_id, filename: str) -> bool:
        try:
            await asyncio.to_thread(
                self.collection.delete,
                where={'$and': [{'user_id': str(user_id)}, {'filename': filename}]},
            )
            return True
        except Exception:
            logger.exception(f'Error removing {filename} for user {user_id}')
            return False

    async def remove_user(self, user_id) -> bool:
        try:
            await asyncio.to_thread(self.collection.delete, where={'user_id': str(user_id)})
            return True
        except Exception:
            logger.exception(f'Error removing texts for user {user_id}')
            return False

    async def user_files(self, user_id) -> list[str] | None:
        try:
            results = await asyncio.to_thread(
                self.collection.get, where={'user_id': str(user_id)}, include=['metadatas']
            )
            filenames = {
                meta['filename'] for meta in (results.get('metadatas') or [])
                if meta and 'filename' in meta
            }
            return sorted(filenames)
        except Exception:
            logger.exception(f'Error retrieving files for user {user_id}')
            return None


def chunk_text(text: str, chunk_size: int, overlap_percent: float) -> list[str]:
    '''
    Split text into ~chunk_size character chunks at paragraph/sentence/word
    boundaries with overlap_percent overlap between consecutive chunks.
    '''
    overlap_size = int(chunk_size * overlap_percent)
    if chunk_size - overlap_size <= 0:
        raise ValueError(f'overlap {overlap_size} leaves no room in chunk_size {chunk_size}')

    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    chunks: list[str] = []
    current = ''

    def flush():
        nonlocal current
        if current:
            chunks.append(current)
            current = _overlap_tail(current, overlap_size)

    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > chunk_size:
            flush()
        if len(paragraph) > chunk_size:
            # split an oversized paragraph by words
            if current:
                chunks.append(current)
                current = ''
            for word in paragraph.split():
                if current and len(current) + len(word) + 1 > chunk_size:
                    flush()
                current = f'{current} {word}' if current else word
        else:
            current = f'{current}\n\n{paragraph}' if current else paragraph
    if current:
        chunks.append(current)
    return chunks


def _overlap_tail(chunk: str, overlap_size: int) -> str:
    '''The trailing part of a chunk carried over into the next one, preferring
    sentence, then word boundaries.'''
    if overlap_size <= 0:
        return ''
    tail = chunk[-min(overlap_size, len(chunk)):]
    sentence = re.search(r'[.!?]\s+(?=[A-ZА-ЯЁ])', tail)
    if sentence:
        return tail[sentence.end():]
    word = re.search(r'\s+', tail)
    if word:
        return tail[word.end():]
    return tail
