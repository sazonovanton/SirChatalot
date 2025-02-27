# Description: Embeddings Engines for SirChatalot

import configparser
config = configparser.ConfigParser()
config.read('./data/.config', encoding='utf-8')
LogLevel = config.get("Logging", "LogLevel") if config.has_option("Logging", "LogLevel") else "WARNING"

# logging
import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-EmbEngines")
LogLevel = getattr(logging, LogLevel.upper())
logger.setLevel(LogLevel)
handler = TimedRotatingFileHandler('./logs/sirchatalot.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7,
                                       encoding='utf-8')
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

######## OpenAI Embeddings Engine ########

class OpenAIEmbEngine:
    def __init__(self, api_key, base_url=None, proxy=None, model="text-embedding-3-small"):
        from openai import AsyncOpenAI
        if proxy is not None:
            import httpx
            http_client = httpx.AsyncClient(proxy=proxy)
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client if proxy is not None else None
        )
        self.model = model
        logger.info("OpenAI Emb Engine Initialized")
        logger.debug(f"OpenAI Emb Engine Initialized with API Key: ***{api_key[-4:]}, base_url: {base_url}, proxy: {proxy.split('@')[1] if proxy is not None else None}")

    async def get_embeddings(self, text):
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text
            )
            prompt_tokens = response.usage.prompt_tokens
            embs = []
            for el in response.data:
                embs.append(el.embedding)
            if type(text) == str:
                embs = embs[0]
            logger.debug(f"OpenAI Emb Engine: Got embeddings for text (Tokens: {prompt_tokens})")
            return embs, prompt_tokens
        except KeyboardInterrupt:
            raise KeyboardInterrupt
        except Exception as e:
            logger.error(f"OpenAI Emb Engine Error: {e}")
            return None, None
        

def get_embeddings_engine():
        api_key = config.get("Embeddings", "SecretKey")
        engine = config.get("Embeddings", "Engine", fallback="OpenAI")
        proxy = config.get("Embeddings", "Proxy", fallback=None)
        base_url = config.get("Embeddings", "BaseURL", fallback=None)
        model = config.get("Embeddings", "Model", fallback="text-embedding-3-small")
        if engine == "OpenAI":
            emb_engine = OpenAIEmbEngine(api_key, base_url=base_url, proxy=proxy, model=model)
        else:
            emb_engine = None
        return emb_engine

if __name__ == "__main__":
    # test
    import asyncio
    api_key = config.get("Embeddings", "SecretKey")
    engine = config.get("Embeddings", "Engine", fallback="OpenAI")
    proxy = config.get("Embeddings", "Proxy", fallback=None)
    base_url = config.get("Embeddings", "BaseURL", fallback=None)
    model = config.get("Embeddings", "Model", fallback="text-embedding-3-small")
    if engine == "OpenAI":
        emb_engine = OpenAIEmbEngine(api_key, base_url=base_url, proxy=proxy, model=model)
    
    texts = ["Pineapple is a fruit", "A car, or an automobile, is a motor vehicle with wheels.", "Paris is the capital and largest city of France. "]

    async def test():
        embs, tokens = await emb_engine.get_embeddings(texts)
        print(f"Total tokens: {tokens}\n---")
        for text, embs in zip(texts, embs):
            print(f"Text: {text}")
            print(f"Embeddings length: {len(embs)}")
        await asyncio.sleep(1)
    asyncio.run(test())