'''
Access control: banlist, whitelist with access codes, and rate limiting.
whitelist.txt / banlist.txt stay as plain text files in ./data (human-editable).
'''

import asyncio
import os
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from sirchatalot.logging_setup import get_logger
from sirchatalot.tg import ratelimit
from sirchatalot.tg.services import get_services

logger = get_logger('auth')

WHITELIST_PATH = './data/whitelist.txt'
BANLIST_PATH = './data/banlist.txt'

# commands that should not consume the rate limit
NO_RATE_CHECK = {'statistics_command', 'delete_command', 'limit_command'}

_whitelist_lock = asyncio.Lock()


def _read_ids(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}
    except OSError:
        logger.exception(f'Could not read {path}')
        return set()


async def _add_to_whitelist(user_id: int) -> None:
    async with _whitelist_lock:
        ids = _read_ids(WHITELIST_PATH)
        if str(user_id) not in ids:
            with open(WHITELIST_PATH, 'a', encoding='utf-8') as f:
                f.write(f'{user_id}\n')


async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     message: str | None = None, check_rate: bool = True) -> bool | None:
    '''
    True — access granted; False — denied; None — the user was just whitelisted
    via an access code (a welcome message has been sent, stop processing).
    '''
    services = get_services(context)
    cfg = services.cfg
    user = update.effective_user
    reply_target = update.effective_message

    if user is None:
        return False

    # keep the stored identity fresh for the system-prompt context block
    try:
        await services.db.set_user_identity(user.id, user.full_name, user.username)
    except Exception:
        logger.debug('Could not store user identity', exc_info=True)

    if cfg.telegram.banlist_enabled and str(user.id) in _read_ids(BANLIST_PATH):
        logger.warning(f'Restricted access to banned user: {user.id}')
        if reply_target is not None:
            await reply_target.reply_text('You are banned.')
        return False

    if cfg.telegram.access_codes:
        if str(user.id) not in _read_ids(WHITELIST_PATH):
            if message is not None and message.strip() in cfg.telegram.access_codes:
                await _add_to_whitelist(user.id)
                logger.info(f'Granted access to user {user.id} via access code')
                if reply_target is not None:
                    await reply_target.reply_text('You are now able to use this bot. Welcome!')
                    await services.chat.delete_chat(user.id)
                    outcome = await services.chat.process_text(
                        user.id, f"Hi! I'm {user.full_name}!")
                    await reply_target.reply_text(
                        outcome.text if outcome else 'Sorry, something went wrong.')
                return None
            logger.info(f'Restricted access to user: {user.id}')
            if reply_target is not None:
                await reply_target.reply_text(
                    f"Sorry, {user.full_name}, you don't have access to this bot.")
            return False

    if check_rate:
        allowed, _, limit = await ratelimit.check(cfg, services.db, user.id)
        if not allowed:
            logger.info(f'Rate limited user: {user.id} (limit {limit})')
            if reply_target is not None:
                await reply_target.reply_text(
                    'You are rate limited. You can check your limits with /limit')
            return False
    return True


def is_authorized(func):
    '''Handler decorator: run the handler only when access is granted.'''
    check_rate = func.__name__ not in NO_RATE_CHECK

    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        text = update.message.text if update.message is not None else None
        access = await check_user(update, context, text, check_rate=check_rate)
        if access is not True:
            return None
        return await func(update, context, *args, **kwargs)
    return wrapped
