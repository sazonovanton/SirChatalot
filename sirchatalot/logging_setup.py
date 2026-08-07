'''
Logging setup for SirChatalot. Called exactly once from app.py.
All modules use logging.getLogger(__name__) and inherit this configuration.
'''

import logging
import os
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = './logs'
LOG_FILE = os.path.join(LOG_DIR, 'sirchatalot.log')


def setup_logging(level: str = 'WARNING') -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    handler = TimedRotatingFileHandler(
        LOG_FILE, when='D', interval=1, backupCount=7, encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter(
        '%(name)s - %(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S'
    ))
    root = logging.getLogger('sirchatalot')
    root.setLevel(getattr(logging, level.upper(), logging.WARNING))
    root.addHandler(handler)
    root.propagate = False   # the same handler sits on the root logger below
    # keep third-party noise (httpx, telegram, chromadb) at WARNING in the same file
    lib_root = logging.getLogger()
    if not lib_root.handlers:
        lib_root.addHandler(handler)
        lib_root.setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f'sirchatalot.{name}')
