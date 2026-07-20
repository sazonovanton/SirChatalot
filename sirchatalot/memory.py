'''Persistent memory about the user: stored in the DB, injected into the system
prompt, written by the model via the save_memory tool, managed by the user
with the /memory command.'''

from sirchatalot.config import MemoryConfig
from sirchatalot.db import Database
from sirchatalot.logging_setup import get_logger

logger = get_logger('memory')


class MemoryStore:
    def __init__(self, cfg: MemoryConfig, db: Database):
        self.cfg = cfg
        self.db = db

    async def save(self, user_id: int, content: str) -> bool:
        '''Save a fact unless an identical one already exists. Returns whether it
        was actually saved (models sometimes call save_memory twice).'''
        content = content.strip()
        if not content:
            return False
        existing = {m['content'].strip().casefold() for m in await self.list(user_id)}
        if content[:1000].casefold() in existing:
            logger.debug(f'Duplicate memory ignored for user {user_id}')
            return False
        await self.db.add_memory(user_id, content[:1000], self.cfg.max_items)
        logger.debug(f'Saved memory for user {user_id}')
        return True

    async def list(self, user_id: int) -> list[dict]:
        return await self.db.list_memories(user_id)

    async def delete(self, user_id: int, memory_id: int) -> bool:
        return await self.db.delete_memory(user_id, memory_id)

    async def clear(self, user_id: int) -> int:
        return await self.db.clear_memories(user_id)

    async def prompt_block(self, user_id: int) -> str:
        memories = await self.list(user_id)
        if not memories:
            return ''
        lines = ['\n# What you remember about this user:']
        lines += [f'- {m["content"]}' for m in memories]
        lines.append('Use the save_memory tool to remember new lasting facts about '
                     'the user (preferences, context, important details).')
        return '\n'.join(lines)
