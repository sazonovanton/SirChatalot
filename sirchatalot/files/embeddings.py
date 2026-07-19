'''Embeddings engines: OpenAI-compatible API or fully local ONNX (ChromaDB's
bundled MiniLM model — no API calls, model is downloaded on first use).'''

import asyncio

from openai import AsyncOpenAI

from sirchatalot.config import EmbeddingsConfig
from sirchatalot.logging_setup import get_logger

logger = get_logger('embeddings')


class EmbeddingsEngine:
    def __init__(self, cfg: EmbeddingsConfig, proxy: str | None = None):
        self.cfg = cfg
        from sirchatalot.engine import openai_http_client
        self.client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url,
                                  http_client=openai_http_client(proxy))

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        '''Embeddings for a list of texts. Raises on failure.'''
        response = await self.client.embeddings.create(model=self.cfg.model, input=texts)
        return [item.embedding for item in response.data]

    async def get_embedding(self, text: str) -> list[float]:
        return (await self.get_embeddings([text]))[0]


class LocalEmbeddings:
    '''all-MiniLM-L6-v2 via ONNX runtime, bundled with ChromaDB.'''

    def __init__(self):
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
        self._fn = ONNXMiniLM_L6_V2()

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        vectors = await asyncio.to_thread(self._fn, texts)
        return [list(map(float, v)) for v in vectors]

    async def get_embedding(self, text: str) -> list[float]:
        return (await self.get_embeddings([text]))[0]


def make_embeddings_engine(cfg: EmbeddingsConfig, proxy: str | None = None):
    if cfg.provider == 'local':
        logger.info('Using local ONNX embeddings (all-MiniLM-L6-v2)')
        return LocalEmbeddings()
    return EmbeddingsEngine(cfg, proxy=proxy)
