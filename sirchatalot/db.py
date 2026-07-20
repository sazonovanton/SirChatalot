'''
SQLite storage for SirChatalot (aiosqlite).

Replaces the old pickle files (chats/stats/ratelimit), files.json and rates.txt.
One shared connection in WAL mode; opened in Application.post_init, closed on shutdown.
'''

import json
import time

import aiosqlite

from sirchatalot.logging_setup import get_logger

logger = get_logger('db')

DEFAULT_DB_PATH = './data/db.sqlite3'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    selected_model TEXT,
    style_name     TEXT,
    created_at     TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS chat_history (
    user_id       INTEGER PRIMARY KEY,
    messages_json TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stats (
    user_id             INTEGER PRIMARY KEY,
    messages_sent       INTEGER NOT NULL DEFAULT 0,
    voice_messages_sent INTEGER NOT NULL DEFAULT 0,
    speech2text_seconds REAL    NOT NULL DEFAULT 0,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    images_generated    INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL    NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rate_events (
    user_id INTEGER NOT NULL,
    ts      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_events ON rate_events(user_id, ts);
CREATE TABLE IF NOT EXISTS files (
    owner     TEXT NOT NULL,
    filename  TEXT NOT NULL,
    summary   TEXT,
    processed INTEGER NOT NULL DEFAULT 0,
    added_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (owner, filename)
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
'''

# columns added after the initial schema; applied idempotently on connect
MIGRATIONS = (
    'ALTER TABLE users ADD COLUMN disabled_tools TEXT',
    'ALTER TABLE users ADD COLUMN full_name TEXT',
    'ALTER TABLE users ADD COLUMN username TEXT',
)


class Database:
    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute('PRAGMA journal_mode=WAL')
        await self._conn.execute('PRAGMA busy_timeout=5000')
        await self._conn.executescript(SCHEMA)
        for migration in MIGRATIONS:
            try:
                await self._conn.execute(migration)
            except aiosqlite.OperationalError:
                pass  # column already exists
        await self._conn.commit()
        logger.info(f'Database connected: {self.path}')

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError('Database is not connected')
        return self._conn

    # ---- meta (key-value) ----

    async def get_meta(self, key: str) -> str | None:
        async with self.conn.execute(
            'SELECT value FROM meta WHERE key = ?', (key,)
        ) as cur:
            row = await cur.fetchone()
        return row['value'] if row else None

    async def set_meta(self, key: str, value: str) -> None:
        await self.conn.execute(
            'INSERT INTO meta (key, value) VALUES (?, ?) '
            'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (key, value),
        )
        await self.conn.commit()

    # ---- users ----

    async def get_selected_model(self, user_id: int) -> str | None:
        async with self.conn.execute(
            'SELECT selected_model FROM users WHERE user_id = ?', (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return row['selected_model'] if row else None

    async def set_selected_model(self, user_id: int, model_name: str | None) -> None:
        await self.conn.execute(
            'INSERT INTO users (user_id, selected_model) VALUES (?, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET selected_model = excluded.selected_model',
            (user_id, model_name),
        )
        await self.conn.commit()

    async def get_style(self, user_id: int) -> str | None:
        async with self.conn.execute(
            'SELECT style_name FROM users WHERE user_id = ?', (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return row['style_name'] if row else None

    async def set_style(self, user_id: int, style_name: str | None) -> None:
        await self.conn.execute(
            'INSERT INTO users (user_id, style_name) VALUES (?, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET style_name = excluded.style_name',
            (user_id, style_name),
        )
        await self.conn.commit()

    async def set_user_identity(self, user_id: int, full_name: str | None,
                                username: str | None) -> None:
        await self.conn.execute(
            'INSERT INTO users (user_id, full_name, username) VALUES (?, ?, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET '
            'full_name = excluded.full_name, username = excluded.username',
            (user_id, full_name, username),
        )
        await self.conn.commit()

    async def get_user_identity(self, user_id: int) -> tuple[str | None, str | None]:
        async with self.conn.execute(
            'SELECT full_name, username FROM users WHERE user_id = ?', (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return (row['full_name'], row['username']) if row else (None, None)

    async def get_disabled_tools(self, user_id: int) -> set[str]:
        async with self.conn.execute(
            'SELECT disabled_tools FROM users WHERE user_id = ?', (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row or not row['disabled_tools']:
            return set()
        try:
            return set(json.loads(row['disabled_tools']))
        except json.JSONDecodeError:
            return set()

    async def set_disabled_tools(self, user_id: int, disabled: set[str]) -> None:
        await self.conn.execute(
            'INSERT INTO users (user_id, disabled_tools) VALUES (?, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET disabled_tools = excluded.disabled_tools',
            (user_id, json.dumps(sorted(disabled))),
        )
        await self.conn.commit()

    # ---- memories ----

    async def list_memories(self, user_id: int) -> list[dict]:
        async with self.conn.execute(
            'SELECT id, content, created_at FROM memories WHERE user_id = ? ORDER BY id',
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def add_memory(self, user_id: int, content: str, max_items: int) -> None:
        await self.conn.execute(
            'INSERT INTO memories (user_id, content) VALUES (?, ?)', (user_id, content)
        )
        # keep only the newest max_items entries
        await self.conn.execute(
            'DELETE FROM memories WHERE user_id = ? AND id NOT IN '
            '(SELECT id FROM memories WHERE user_id = ? ORDER BY id DESC LIMIT ?)',
            (user_id, user_id, max_items),
        )
        await self.conn.commit()

    async def delete_memory(self, user_id: int, memory_id: int) -> bool:
        cur = await self.conn.execute(
            'DELETE FROM memories WHERE user_id = ? AND id = ?', (user_id, memory_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def clear_memories(self, user_id: int) -> int:
        cur = await self.conn.execute(
            'DELETE FROM memories WHERE user_id = ?', (user_id,)
        )
        await self.conn.commit()
        return cur.rowcount

    # ---- chat history ----

    async def get_history(self, user_id: int) -> list | None:
        async with self.conn.execute(
            'SELECT messages_json FROM chat_history WHERE user_id = ?', (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row['messages_json'])
        except json.JSONDecodeError:
            logger.error(f'Corrupted chat history for user {user_id}, dropping it')
            await self.delete_history(user_id)
            return None

    async def save_history(self, user_id: int, messages: list) -> None:
        await self.conn.execute(
            'INSERT INTO chat_history (user_id, messages_json, updated_at) '
            "VALUES (?, ?, datetime('now')) "
            'ON CONFLICT(user_id) DO UPDATE SET '
            'messages_json = excluded.messages_json, updated_at = excluded.updated_at',
            (user_id, json.dumps(messages, ensure_ascii=False)),
        )
        await self.conn.commit()

    async def delete_history(self, user_id: int) -> bool:
        cur = await self.conn.execute('DELETE FROM chat_history WHERE user_id = ?', (user_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    # ---- stats ----

    async def add_stats(self, user_id: int, *, messages_sent: int = 0,
                        voice_messages_sent: int = 0, speech2text_seconds: float = 0,
                        prompt_tokens: int = 0, completion_tokens: int = 0,
                        images_generated: int = 0, cost_usd: float = 0) -> None:
        await self.conn.execute(
            '''INSERT INTO stats (user_id, messages_sent, voice_messages_sent,
                                  speech2text_seconds, prompt_tokens, completion_tokens,
                                  images_generated, cost_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 messages_sent       = messages_sent + excluded.messages_sent,
                 voice_messages_sent = voice_messages_sent + excluded.voice_messages_sent,
                 speech2text_seconds = speech2text_seconds + excluded.speech2text_seconds,
                 prompt_tokens       = prompt_tokens + excluded.prompt_tokens,
                 completion_tokens   = completion_tokens + excluded.completion_tokens,
                 images_generated    = images_generated + excluded.images_generated,
                 cost_usd            = cost_usd + excluded.cost_usd''',
            (user_id, messages_sent, voice_messages_sent, speech2text_seconds,
             prompt_tokens, completion_tokens, images_generated, cost_usd),
        )
        await self.conn.commit()

    async def get_stats(self, user_id: int) -> dict | None:
        async with self.conn.execute(
            'SELECT * FROM stats WHERE user_id = ?', (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    # ---- rate limiting ----

    async def rate_check_and_record(self, user_id: int, window_seconds: int,
                                    limit: int, record: bool = True) -> tuple[bool, int]:
        '''
        Sliding-window rate limit. Returns (allowed, used_count_in_window).
        With record=False only reports the current usage without consuming it.
        '''
        now = time.time()
        await self.conn.execute(
            'DELETE FROM rate_events WHERE user_id = ? AND ts <= ?',
            (user_id, now - window_seconds),
        )
        async with self.conn.execute(
            'SELECT COUNT(*) AS c FROM rate_events WHERE user_id = ?', (user_id,)
        ) as cur:
            used = (await cur.fetchone())['c']
        allowed = used < limit
        if allowed and record:
            await self.conn.execute(
                'INSERT INTO rate_events (user_id, ts) VALUES (?, ?)', (user_id, now)
            )
            used += 1
        await self.conn.commit()
        return allowed, used

    # ---- files registry ----

    async def list_files(self, owner: str) -> list[dict]:
        async with self.conn.execute(
            'SELECT filename, summary, processed FROM files WHERE owner = ? ORDER BY added_at',
            (owner,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def upsert_file(self, owner: str, filename: str, summary: str | None,
                          processed: bool) -> None:
        await self.conn.execute(
            'INSERT INTO files (owner, filename, summary, processed) VALUES (?, ?, ?, ?) '
            'ON CONFLICT(owner, filename) DO UPDATE SET '
            'summary = excluded.summary, processed = excluded.processed',
            (owner, filename, summary, int(processed)),
        )
        await self.conn.commit()

    async def list_file_owners(self) -> list[str]:
        async with self.conn.execute('SELECT DISTINCT owner FROM files') as cur:
            rows = await cur.fetchall()
        return [r['owner'] for r in rows]

    async def delete_file(self, owner: str, filename: str) -> bool:
        cur = await self.conn.execute(
            'DELETE FROM files WHERE owner = ? AND filename = ?', (owner, filename)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def delete_files(self, owner: str) -> int:
        cur = await self.conn.execute('DELETE FROM files WHERE owner = ?', (owner,))
        await self.conn.commit()
        return cur.rowcount
