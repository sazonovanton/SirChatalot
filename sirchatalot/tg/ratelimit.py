'''Per-user message rate limiting backed by the rate_events table.'''

from sirchatalot.config import AppConfig
from sirchatalot.db import Database


def user_limit(cfg: AppConfig, user_id: int) -> int | None:
    '''Effective limit for a user; None means unlimited.'''
    if cfg.rate_limit is None:
        return None
    override = cfg.rate_limit.user_overrides.get(user_id)
    if override is not None:
        return None if override == 0 else override
    return cfg.rate_limit.general_limit


async def check(cfg: AppConfig, db: Database, user_id: int, record: bool = True):
    '''
    Returns (allowed, used, limit). limit is None when the user is unlimited
    (allowed is then always True and used is 0).
    '''
    limit = user_limit(cfg, user_id)
    if limit is None:
        return True, 0, None
    allowed, used = await db.rate_check_and_record(
        user_id, cfg.rate_limit.window_seconds, limit, record=record
    )
    return allowed, used, limit
