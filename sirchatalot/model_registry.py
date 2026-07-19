'''
Model registry: per-user model selection and the fallback chain.
'''

from sirchatalot.config import AppConfig
from sirchatalot.db import Database
from sirchatalot.engine import RETRIABLE_ERRORS, ChatResult, LLMEngine, sanitize_for
from sirchatalot.logging_setup import get_logger

logger = get_logger('registry')


class AllModelsFailedError(Exception):
    def __init__(self, chain: list[str], last_error: Exception | None):
        super().__init__(f'All models failed ({" -> ".join(chain)}): {last_error}')
        self.chain = chain
        self.last_error = last_error


class ModelRegistry:
    def __init__(self, cfg: AppConfig, db: Database):
        self.engines = {spec.name: LLMEngine(spec, default_proxy=cfg.proxies.llm)
                        for spec in cfg.models}
        self.default = cfg.default_model
        self.fallback_chain = cfg.fallback_chain
        self.db = db

    def engine(self, name: str) -> LLMEngine:
        # a model removed from the config silently reverts the user to the default
        return self.engines.get(name) or self.engines[self.default]

    async def engine_for_user(self, user_id: int) -> LLMEngine:
        name = await self.db.get_selected_model(user_id)
        return self.engine(name) if name else self.engines[self.default]

    async def spec_for_user(self, user_id: int):
        return (await self.engine_for_user(user_id)).spec

    async def select(self, user_id: int, name: str) -> bool:
        if name not in self.engines:
            return False
        await self.db.set_selected_model(user_id, name)
        return True

    async def complete(self, user_id: int, messages: list, tools: list | None = None,
                       tool_choice: str | None = None, end_user: str | None = None,
                       primary: LLMEngine | None = None):
        '''
        Complete with the user's model, falling back along fallback_chain on
        retriable API errors. Returns (ChatResult, spec actually used).
        Pass `primary` when the caller already resolved the user's engine
        (avoids a DB read per call in the agent loop).
        '''
        if primary is None:
            primary = await self.engine_for_user(user_id)
        chain = [primary.spec.name] + [n for n in self.fallback_chain if n != primary.spec.name]
        last_error = None
        for name in chain:
            eng = self.engines[name]
            msgs = sanitize_for(messages, eng.spec)
            t = tools if (tools and eng.spec.tools) else None
            try:
                result = await eng.complete(msgs, tools=t, tool_choice=tool_choice if t else None,
                                            end_user=end_user)
                if name != chain[0]:
                    logger.warning(f'Fell back from {chain[0]} to {name} for user {user_id}')
                return result, eng.spec
            except RETRIABLE_ERRORS as e:
                last_error = e
                logger.warning(f'Model {name} failed for user {user_id}, trying next: {e}')
        raise AllModelsFailedError(chain, last_error)


def summary_engine(registry: ModelRegistry) -> LLMEngine:
    '''Engine used for auxiliary calls (summaries, moderation): the default model.'''
    return registry.engines[registry.default]
