'''
Application wiring: build services from config, register handlers, run polling.
'''

import os
import sys

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from sirchatalot.chat_manager import ChatManager
from sirchatalot.config import AppConfig, ConfigError, load_config
from sirchatalot.db import Database
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
        from sirchatalot.files.embeddings import EmbeddingsEngine
        from sirchatalot.files.extract import FilesProcessor
        from sirchatalot.files.rag import FilesRAG
        files_proc = FilesProcessor()
        files_rag = FilesRAG(cfg.files, EmbeddingsEngine(cfg.files.embeddings,
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

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.answer))
    application.add_handler(MessageHandler(
        filters.VOICE | filters.VIDEO | filters.VIDEO_NOTE, handlers.answer_voice_or_video))
    application.add_handler(MessageHandler(filters.PHOTO, handlers.process_image))
    application.add_handler(MessageHandler(DOCUMENT_FILTER, handlers.downloader))


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
    db = Database()

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
        await ingest_common_files(services)

    async def post_shutdown(application: Application) -> None:
        if mcp_manager is not None:
            await mcp_manager.stop()
        await db.close()

    builder = (Application.builder()
               .token(cfg.telegram.token)
               .post_init(post_init)
               .post_shutdown(post_shutdown))
    if cfg.proxies.telegram:
        builder = (builder.proxy(cfg.proxies.telegram)
                   .get_updates_proxy(cfg.proxies.telegram))
    application = builder.build()
    register_handlers(application)
    application.run_polling()
