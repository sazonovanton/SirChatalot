import pytest_asyncio

from sirchatalot.config import AppConfig
from sirchatalot.db import Database

BASE_CONFIG = {
    'telegram': {'token': 'test-token'},
    'models': [
        {'name': 'primary', 'model': 'gpt-test', 'api_key': 'k',
         'vision': True, 'tools': True,
         'prompt_price': 1.0, 'completion_price': 2.0},
        {'name': 'backup', 'model': 'gpt-backup', 'api_key': 'k',
         'vision': False, 'tools': False},
    ],
    'default_model': 'primary',
    'fallback_chain': ['backup'],
}


def make_config(**overrides) -> AppConfig:
    raw = {**BASE_CONFIG, **overrides}
    return AppConfig.model_validate(raw)


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / 'test.sqlite3'))
    await database.connect()
    yield database
    await database.close()
