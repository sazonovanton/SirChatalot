'''
Application wiring: build services from config, register handlers, run polling.
'''

import asyncio
import contextlib
import os
import sys
import time

from telegram.error import InvalidToken
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from sirchatalot.chat_manager import ChatManager
from sirchatalot.config import AppConfig, ConfigError, TelegramNetworkConfig, load_config
from sirchatalot.db import Database
from sirchatalot.health import HEARTBEAT_PATH, write_heartbeat
from sirchatalot.logging_setup import get_logger, setup_logging
from sirchatalot.model_registry import ModelRegistry
from sirchatalot.tg import handlers
from sirchatalot.tg.services import Services

logger = get_logger('app')

COMMON_FILES_DIR = './data/files/common'

DOCUMENT_FILTER = (
    filters.Document.MimeType('application/pdf')
    | filters.Document.MimeType('application/msword')
    | filters.Document.MimeType('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    | filters.Document.MimeType('application/vnd.ms-powerpoint')
    | filters.Document.MimeType('application/vnd.openxmlformats-officedocument.presentationml.presentation')
    | filters.Document.MimeType('text/plain')
    | filters.Document.MimeType('text/csv')
    | filters.Document.MimeType('text/markdown')
    # clients often send text files with a generic mime type; match by extension too
    | filters.Document.FileExtension('txt')
    | filters.Document.FileExtension('md')
    | filters.Document.FileExtension('csv')
    | filters.Document.FileExtension('log')
)


def build_services(cfg: AppConfig, db: Database) -> Services:
    registry = ModelRegistry(cfg, db)

    image_engine = None
    if cfg.image_generation is not None:
        from sirchatalot.media.images import ImageEngine
        image_engine = ImageEngine(cfg.image_generation, end_user_id=cfg.chat.end_user_id,
                                   proxy=cfg.proxies.llm)

    audio_engine = None
    if cfg.audio is not None:
        from sirchatalot.media.audio import AudioEngine
        audio_engine = AudioEngine(cfg.audio, proxy=cfg.proxies.llm)

    web_search = None
    url_opener = None
    if cfg.web is not None:
        from sirchatalot.tools.web import UrlOpener, make_search_engine
        if cfg.web.search is not None:
            web_search = make_search_engine(cfg.web.search, proxy=cfg.proxies.search)
        if cfg.web.url_open is not None and cfg.web.url_open.enabled:
            url_opener = UrlOpener(cfg.web.url_open, proxy=cfg.proxies.jina)

    files_proc = None
    files_rag = None
    if cfg.files is not None:
        from sirchatalot.files.embeddings import make_embeddings_engine
        from sirchatalot.files.extract import FilesProcessor
        from sirchatalot.files.rag import FilesRAG
        files_proc = FilesProcessor()
        files_rag = FilesRAG(cfg.files, make_embeddings_engine(cfg.files.embeddings,
                                                               proxy=cfg.proxies.llm))

    memory = None
    if cfg.memory is not None:
        from sirchatalot.memory import MemoryStore
        memory = MemoryStore(cfg.memory, db)

    chat = ChatManager(cfg, db, registry,
                       image_engine=image_engine, audio_engine=audio_engine,
                       web_search=web_search, url_opener=url_opener,
                       files_rag=files_rag, memory=memory)
    return Services(cfg=cfg, db=db, registry=registry, chat=chat,
                    files_proc=files_proc, files_rag=files_rag)


def embeddings_fingerprint(cfg: AppConfig) -> str:
    emb = cfg.files.embeddings
    if emb.provider == 'local':
        return 'local:onnx-minilm-l6-v2'
    return f'{emb.provider}:{emb.model}:{emb.base_url or "default"}'


async def reindex_if_embeddings_changed(services: Services,
                                        files_dir: str = './data/files') -> None:
    '''
    Vectors from different embedding models are incompatible. Track the
    configured embeddings identity in the DB; when it changes, drop the vector
    store and re-embed every registered file from disk.
    '''
    if services.files_rag is None:
        return
    fingerprint = embeddings_fingerprint(services.cfg)
    stored = await services.db.get_meta('embeddings_fingerprint')
    if stored == fingerprint:
        return
    if stored is None and await services.files_rag.count() == 0:
        await services.db.set_meta('embeddings_fingerprint', fingerprint)
        return

    logger.warning(f'Embeddings changed ({stored} -> {fingerprint}); '
                   f'reindexing all files...')
    print(f'Embeddings model changed — reindexing all uploaded files, please wait...')
    await services.files_rag.reset()
    reindexed = missing = failed = 0
    for owner in await services.db.list_file_owners():
        owner_dir = os.path.join(files_dir, owner)
        for entry in await services.db.list_files(owner):
            filename = entry['filename']
            path = os.path.join(owner_dir, filename)
            if not os.path.exists(path):
                logger.warning(f'Source file missing, dropping from registry: {path}')
                await services.db.delete_file(owner, filename)
                missing += 1
                continue
            text = await services.files_proc.convert_to_text(path)
            processed = bool(text) and await services.files_rag.process_text(
                text, user_id=owner, filename=filename)
            if processed:
                reindexed += 1
            else:
                failed += 1
                await services.db.upsert_file(owner, filename, entry['summary'], False)
                logger.error(f'Could not reindex {path}')
    await services.db.set_meta('embeddings_fingerprint', fingerprint)
    logger.warning(f'Reindexing done: {reindexed} ok, {missing} missing, {failed} failed')
    print(f'Reindexing done: {reindexed} ok, {missing} missing, {failed} failed')


async def ingest_common_files(services: Services) -> None:
    '''Process files from ./data/files/common into the RAG database as user "common".'''
    if services.files_rag is None or not os.path.isdir(COMMON_FILES_DIR):
        return
    known = {f['filename']: f for f in await services.db.list_files('common')}
    for name in sorted(os.listdir(COMMON_FILES_DIR)):
        path = os.path.join(COMMON_FILES_DIR, name)
        if not os.path.isfile(path):
            continue
        if known.get(name, {}).get('processed'):
            continue
        text = await services.files_proc.convert_to_text(path)
        if text is None:
            logger.error(f'Could not convert common file {name} to text')
            continue
        processed = await services.files_rag.process_text(text, user_id='common', filename=name)
        if not processed:
            logger.error(f'Could not process common file {name} into the RAG dataset')
            continue
        summary = await services.chat.summarize_text(text[:4096]) or ''
        await services.db.upsert_file('common', name, summary, True)
        logger.info(f'Common file {name} was processed into the RAG dataset')


class ErrorNotifier:
    '''Global PTB error handler: log everything, tell the user something went
    wrong, and notify the admin (throttled so an error storm does not flood).'''

    THROTTLE_SECONDS = 300

    def __init__(self, admin_id: int | None):
        self.admin_id = admin_id
        self._last_sent: dict[str, float] = {}

    def _should_notify(self, key: str) -> bool:
        import time
        now = time.time()
        last = self._last_sent.get(key)
        if last is not None and now - last < self.THROTTLE_SECONDS:
            return False
        self._last_sent[key] = now
        return True

    async def __call__(self, update, context) -> None:
        error = context.error
        logger.error('Unhandled error in handler', exc_info=error)
        message = getattr(update, 'effective_message', None)
        if message is not None:
            try:
                await message.reply_text('Sorry, something went wrong. '
                                         'The administrator has been notified.')
            except Exception:
                pass
        if self.admin_id is None:
            return
        key = f'{type(error).__name__}: {error}'[:200]
        if not self._should_notify(key):
            return
        user = getattr(update, 'effective_user', None)
        text = (f'⚠️ SirChatalot error\n'
                f'User: {user.id if user else "?"}\n'
                f'{key}')
        try:
            await context.bot.send_message(chat_id=self.admin_id, text=text)
        except Exception:
            logger.exception('Could not notify admin about an error')


class ConnectionWatchdog:
    '''
    Liveness for the Telegram connection.

    Every heartbeat_seconds it pings the Bot API and rewrites the heartbeat file
    the container HEALTHCHECK reads. If the API stays unreachable for
    watchdog_seconds it stops polling and asks run() for a full reconnect —
    python-telegram-bot retries getUpdates forever, but a proxy that dropped the
    underlying connections is only really fixed by rebuilding the HTTP clients.
    '''

    def __init__(self, net: TelegramNetworkConfig, path: str = HEARTBEAT_PATH):
        self.net = net
        self.path = path
        self.restart_requested = False
        self._task: asyncio.Task | None = None
        self._last_ok = 0.0
        self._failures = 0

    def start(self, application: Application) -> None:
        self.restart_requested = False
        self._last_ok = time.time()
        self._failures = 0
        write_heartbeat(self.path, ok=True, last_ok=self._last_ok)
        self._task = asyncio.create_task(self._loop(application))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self, application: Application) -> None:
        while True:
            await asyncio.sleep(self.net.heartbeat_seconds)
            error = await self._probe(application)
            ok = error is None
            now = time.time()
            if ok:
                if self._failures:
                    logger.warning(f'Telegram API is reachable again after '
                                   f'{self._failures} failed probe(s)')
                self._failures = 0
                self._last_ok = now
            else:
                self._failures += 1
                # an outage can last hours; report it without filling the log
                if self._failures == 1 or self._failures % 10 == 0:
                    logger.warning(f'Telegram API probe failed '
                                   f'({self._failures} in a row): {error}')
            write_heartbeat(self.path, ok=ok, last_ok=self._last_ok, now=now)
            if ok or not self.net.watchdog_seconds:
                continue
            down_for = now - self._last_ok
            if down_for >= self.net.watchdog_seconds:
                logger.critical(f'Telegram API unreachable for {down_for:.0f}s — '
                                f'reconnecting from scratch')
                self.restart_requested = True
                application.stop_running()
                return

    async def _probe(self, application: Application) -> str | None:
        '''Ping the Bot API; returns None on success or a description of the failure.'''
        limit = self.net.connect_timeout + self.net.read_timeout + 5
        try:
            await asyncio.wait_for(application.bot.get_me(), timeout=limit)
            return None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return f'{type(e).__name__}: {e}'


def bot_commands(cfg: AppConfig) -> list[tuple[str, str]]:
    '''Commands shown in the Telegram command menu (set_my_commands).'''
    commands = [
        ('help', 'Show help'),
        ('retry', 'Regenerate the last answer'),
        ('undo', 'Remove the last exchange'),
        ('delete', 'Delete chat history'),
        ('model', 'Choose the AI model'),
        ('style', 'Choose a bot style'),
        ('tools', 'Enable/disable AI tools'),
        ('statistics', 'Show usage statistics'),
        ('limit', 'Check your rate limit'),
    ]
    if cfg.memory is not None:
        commands.append(('memory', 'View/clear what the bot remembers'))
    if cfg.image_generation is not None:
        commands.append(('imagine', 'Generate an image'))
    if cfg.files is not None:
        commands.append(('listfiles', 'List your files'))
        commands.append(('deletefiles', 'Delete all your files'))
    return commands


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler('start', handlers.start))
    application.add_handler(CommandHandler('help', handlers.help_command))
    application.add_handler(CommandHandler('retry', handlers.retry_command))
    application.add_handler(CommandHandler('undo', handlers.undo_command))
    application.add_handler(CommandHandler('delete', handlers.delete_command))
    application.add_handler(CommandHandler('statistics', handlers.statistics_command))
    application.add_handler(CommandHandler('limit', handlers.limit_command))
    application.add_handler(CommandHandler('style', handlers.style_command))
    application.add_handler(CommandHandler('model', handlers.model_command))
    application.add_handler(CommandHandler('imagine', handlers.imagine_command))
    application.add_handler(CommandHandler('listfiles', handlers.list_files_command))
    application.add_handler(CommandHandler('deletefiles', handlers.delete_files_command))
    application.add_handler(CommandHandler('memory', handlers.memory_command))
    application.add_handler(CommandHandler('tools', handlers.tools_command))

    application.add_handler(CallbackQueryHandler(handlers.model_button, pattern=r'^model:'))
    application.add_handler(CallbackQueryHandler(handlers.style_button, pattern=r'^style:'))
    application.add_handler(CallbackQueryHandler(handlers.memory_button, pattern=r'^memory:'))
    application.add_handler(CallbackQueryHandler(handlers.tools_button, pattern=r'^tools:'))
    application.add_handler(CallbackQueryHandler(handlers.files_button, pattern=r'^files:'))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.answer))
    application.add_handler(MessageHandler(
        filters.VOICE | filters.VIDEO | filters.VIDEO_NOTE, handlers.answer_voice_or_video))
    application.add_handler(MessageHandler(filters.PHOTO, handlers.process_image))
    application.add_handler(MessageHandler(DOCUMENT_FILTER, handlers.downloader))


def build_application(cfg: AppConfig, db: Database,
                      watchdog: ConnectionWatchdog) -> Application:
    '''Build a ready-to-poll Application. Called again on every reconnect, so
    everything bound to the event loop (HTTP clients, DB, MCP) is created here
    and torn down in post_shutdown.'''
    mcp_manager = None

    async def post_init(application: Application) -> None:
        nonlocal mcp_manager
        await db.connect()
        services = build_services(cfg, db)
        application.bot_data['services'] = services
        if cfg.mcp_servers:
            from sirchatalot.mcp_client import MCPManager
            from sirchatalot.tools import registry as tool_registry
            mcp_manager = MCPManager(cfg.mcp_servers, tool_registry)
            await mcp_manager.start()
        try:
            await application.bot.set_my_commands(bot_commands(cfg))
        except Exception:
            logger.exception('Could not set the bot command menu')
        await reindex_if_embeddings_changed(services)
        await ingest_common_files(services)
        watchdog.start(application)

    async def post_shutdown(application: Application) -> None:
        await watchdog.stop()
        if mcp_manager is not None:
            await mcp_manager.stop()
        await db.close()

    net = cfg.telegram.network
    builder = (Application.builder()
               .token(cfg.telegram.token)
               .connect_timeout(net.connect_timeout)
               .read_timeout(net.read_timeout)
               .write_timeout(net.write_timeout)
               .pool_timeout(net.pool_timeout)
               .connection_pool_size(net.connection_pool_size)
               # getUpdates gets its own client: PTB defaults it to a single
               # connection with a 1s pool timeout, which a proxy easily exhausts
               .get_updates_connect_timeout(net.connect_timeout)
               .get_updates_read_timeout(net.read_timeout)
               .get_updates_write_timeout(net.write_timeout)
               .get_updates_pool_timeout(net.pool_timeout)
               .get_updates_connection_pool_size(net.get_updates_pool_size)
               .post_init(post_init)
               .post_shutdown(post_shutdown))
    if cfg.proxies.telegram:
        builder = (builder.proxy(cfg.proxies.telegram)
                   .get_updates_proxy(cfg.proxies.telegram))
    application = builder.build()
    register_handlers(application)
    application.add_error_handler(ErrorNotifier(cfg.telegram.admin_id))
    return application


# backoff between reconnects; the last value repeats
RESTART_DELAYS = (5, 15, 30, 60, 120)
# a run that lasted this long counts as healthy: the next failure starts over
RESTART_BACKOFF_RESET = 300


def run() -> None:
    try:
        cfg = load_config()
    except ConfigError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    setup_logging(cfg.logging.level)
    logger.info('***** Starting chatbot... *****')
    print('***** Starting chatbot... *****')
    print(f'Models: {", ".join(m.name for m in cfg.models)} (default: {cfg.default_model})')
    if cfg.fallback_chain:
        print(f'Fallback chain: {" -> ".join(cfg.fallback_chain)}')
    if cfg.telegram.access_codes:
        print(f'Access codes are set ({len(cfg.telegram.access_codes)}); '
              f'the bot is whitelist-only.')
    else:
        print('No access codes set. The bot is available to everyone.')

    os.makedirs('./data/chats', exist_ok=True)
    net = cfg.telegram.network
    watchdog = ConnectionWatchdog(net)
    db = Database()
    attempt = 0

    while True:
        try:
            application = build_application(cfg, db, watchdog)
        except Exception:
            logger.exception('Could not build the application')
            print('Could not build the application, see the log', file=sys.stderr)
            sys.exit(1)

        started = time.monotonic()
        try:
            # bootstrap_retries=-1: keep retrying the initial connection instead
            # of dying when Telegram (or the proxy) is down at startup
            application.run_polling(poll_interval=net.poll_interval,
                                    timeout=int(net.poll_timeout),
                                    bootstrap_retries=-1)
        except InvalidToken:
            logger.critical('Invalid Telegram token')
            print('Invalid Telegram token', file=sys.stderr)
            sys.exit(1)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            logger.exception('Polling stopped with an error')
            if time.monotonic() - started > RESTART_BACKOFF_RESET:
                attempt = 0
            delay = RESTART_DELAYS[min(attempt, len(RESTART_DELAYS) - 1)]
            attempt += 1
            logger.warning(f'Restarting the bot in {delay}s')
            print(f'Polling stopped with an error, restarting in {delay}s', file=sys.stderr)
            time.sleep(delay)
            continue

        if not watchdog.restart_requested:
            logger.info('***** Bot stopped *****')
            return
        attempt = 0
        logger.warning('Reconnecting to Telegram after a connectivity outage')
        time.sleep(RESTART_DELAYS[0])
