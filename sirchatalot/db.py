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
'''


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

    async def delete_files(self, owner: str) -> int:
        cur = await self.conn.execute('DELETE FROM files WHERE owner = ?', (owner,))
        await self.conn.commit()
        return cur.rowcount
