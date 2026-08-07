'''
Liveness heartbeat shared by the bot and the container healthcheck.

The bot rewrites the heartbeat file on every watchdog tick; healthcheck.py reads
it. Two things have to be true for a healthy bot: the tick itself is running
(the event loop is alive) and the Bot API was reachable recently.
'''

import json
import os
import time

HEARTBEAT_PATH = './data/heartbeat'


def write_heartbeat(path: str, *, ok: bool, last_ok: float,
                    now: float | None = None) -> None:
    '''Atomically record the latest tick. Never raises: a failed heartbeat write
    must not take the bot down (the healthcheck notices the stale file anyway).'''
    payload = {'ts': now if now is not None else time.time(),
               'last_ok': last_ok, 'ok': ok}
    tmp = f'{path}.tmp'
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
        os.replace(tmp, path)
    except OSError:
        pass


def check_heartbeat(path: str, max_age: float,
                    now: float | None = None) -> tuple[int, str]:
    '''Return (exit code, message) for the container healthcheck.'''
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        ts = float(data['ts'])
        last_ok = float(data['last_ok'])
    except (OSError, ValueError, KeyError, TypeError) as e:
        return 1, f'no usable heartbeat at {path}: {type(e).__name__}: {e}'

    now = now if now is not None else time.time()
    age = now - ts
    if age > max_age:
        return 1, f'heartbeat is stale: {age:.0f}s old (limit {max_age:.0f}s)'
    down_for = now - last_ok
    if down_for > max_age:
        return 1, f'Telegram API unreachable for {down_for:.0f}s (limit {max_age:.0f}s)'
    return 0, f'ok: heartbeat {age:.0f}s old, API reachable {down_for:.0f}s ago'
