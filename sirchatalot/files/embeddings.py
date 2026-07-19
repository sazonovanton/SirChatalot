'''OpenAI-compatible embeddings engine.'''

from openai import AsyncOpenAI

from sirchatalot.config import EmbeddingsConfig
from sirchatalot.logging_setup import get_logger

logger = get_logger('embeddings')


class EmbeddingsEngine:
    def __init__(self, cfg: EmbeddingsConfig):
        self.cfg = cfg
        self.client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url)

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        '''Embeddings for a list of texts. Raises on failure.'''
        response = await self.client.embeddings.create(model=self.cfg.model, input=texts)
        return [item.embedding for item in response.data]

    async def get_embedding(self, text: str) -> list[float]:
        return (await self.get_embeddings([text]))[0]
