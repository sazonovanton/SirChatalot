'''All Telegram command/message/callback handlers.'''

import os
import re
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from sirchatalot.logging_setup import get_logger
from sirchatalot.tg import ratelimit
from sirchatalot.tg.auth import check_user, is_authorized
from sirchatalot.tg.services import get_services
from sirchatalot.tg.utils import (
    StatusReporter,
    resize_image_b64,
    send_message,
    typing_action,
)

logger = get_logger('handlers')

FILES_DIR = './data/files'
VOICE_DIR = './data/voice'

GENERIC_ERROR = 'Sorry, something went wrong. You can try later or /delete your session.'


def sanitize_filename(filename: str | None) -> str:
    '''Strip any path components and unsafe characters from an uploaded filename.'''
    name = os.path.basename(filename or '')
    name = re.sub(r'[^\w.() -]', '_', name, flags=re.UNICODE).strip('. ')
    if not name or name.startswith('.'):
        root, ext = os.path.splitext(filename or '')
        name = f'{uuid.uuid4().hex}{ext if len(ext) <= 10 else ""}'
    return name


def _track(context, user_id: int, messages) -> None:
    '''Remember the ids of the bot's answer messages for this user's last turn,
    so /retry and /undo can delete them (best effort, in-memory).'''
    ids = [m.message_id for m in messages if m is not None]
    context.application.bot_data.setdefault('answer_ids', {})[user_id] = ids


async def _delete_tracked(update, context, user_id: int) -> None:
    ids = context.application.bot_data.get('answer_ids', {}).pop(user_id, [])
    for message_id in ids:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id,
                                             message_id=message_id)
        except Exception:
            logger.debug(f'Could not delete message {message_id}', exc_info=True)


async def _reply_outcome(update: Update, context, outcome) -> None:
    services = get_services(context)
    if outcome is None:
        await update.effective_message.reply_text(GENERIC_ERROR)
        return
    sent = []
    for image_bytes in outcome.media:
        sent.append(await update.effective_message.reply_photo(photo=image_bytes))
    if outcome.text:
        sent += await send_message(update, outcome.text,
                                   reply_to_message=services.cfg.telegram.reply_to_message)
    _track(context, update.effective_user.id, sent)


# ---- commands ----

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    access = await check_user(update, context, update.message.text if update.message else None)
    if access is not True:
        return
    services = get_services(context)
    user = update.effective_user
    outcome = await services.chat.process_text(user.id, f"Hi! I'm {user.full_name}!")
    await _reply_outcome(update, context, outcome)


@is_authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    cfg = services.cfg
    text = 'This is a bot that allows you to chat with an AI.\n\n'
    text += 'Commands:\n'
    text += '/start - Start the bot\n'
    text += '/help - Show this message\n'
    text += '/retry - Regenerate the answer to your last message\n'
    text += '/undo - Remove the last exchange from the history\n'
    text += '/delete - Delete chat history\n'
    text += '/statistics - Show statistics\n'
    text += '/limit - Check your rate limit\n'
    text += '/style - Choose a style for the bot\n'
    text += '/model - Choose the AI model\n'
    text += '/tools - Enable/disable tools available to the AI\n'
    if cfg.memory is not None:
        text += '/memory - View and clear what the bot remembers about you\n'
    if cfg.image_generation is not None:
        text += '/imagine <prompt> - Generate an image\n'
    if cfg.files is not None:
        text += '/listfiles - List your files in the RAG database\n'
        text += '/deletefiles - Delete all your files\n'
        text += ('\nYou can send documents (PDF, DOCX, PPTX, TXT...) to the bot. '
                 'It will use them to answer your questions (agentic RAG).\n')
    text += '\nYou can also send an image if the current model supports vision.\n'
    if cfg.audio is not None:
        text += 'The bot will answer to your voice messages if you send them.\n'
    if cfg.web is not None and cfg.web.search is not None:
        text += '\nYou can ask the bot to search the web for something.\n'
    if cfg.web is not None and cfg.web.url_open is not None and cfg.web.url_open.enabled:
        text += 'The bot can also open links you send it.\n'
    if cfg.image_generation is not None:
        from sirchatalot.media.images import _is_dalle
        text += '\nImage generation: `/imagine <prompt>`'
        if cfg.image_generation.api == 'images' and _is_dalle(cfg.image_generation.model):
            text += (' with flags `--natural`, `--vivid`, `--sd`, `--hd`, '
                     '`--horizontal`, `--vertical`, `--revision`.\n'
                     'Example: `/imagine a cat on a table --natural`\n')
        elif cfg.image_generation.api == 'images':
            text += (' with flags `--horizontal`, `--vertical`.\n'
                     'Example: `/imagine a cat on a table --horizontal`\n')
        else:
            text += (' with flags `--ratio 16:9` (aspect ratio), `--res 2K` '
                     '(512/1K/2K/4K), `--horizontal`, `--vertical`, `--square`.\n'
                     'Example: `/imagine a cat on a table --ratio 16:9 --res 2K`\n'
                     '(support depends on the model)\n')
        text += 'You can also just ask the bot to draw something.\n'
    await send_message(update, text)


@is_authorized
async def statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    text = await services.chat.stats_text(update.effective_user.id)
    await update.effective_message.reply_text(text or 'There are no statistics yet.')


@is_authorized
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    deleted = await services.chat.delete_chat(update.effective_user.id)
    if deleted:
        await update.effective_message.reply_text('Chat history deleted')
    else:
        await update.effective_message.reply_text(
            'It seems like there is no history with you.')


@is_authorized
async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    allowed, used, limit = await ratelimit.check(
        services.cfg, services.db, update.effective_user.id, record=False)
    if limit is None:
        await update.effective_message.reply_text('Unlimited')
        return
    window = services.cfg.rate_limit.window_seconds
    text = f'You have used {used}/{limit} messages per {window} seconds.'
    if not allowed:
        text += ' Please wait.'
    await update.effective_message.reply_text(text)


# ---- model selection ----

def _model_keyboard(services, current: str | None) -> InlineKeyboardMarkup:
    current = current or services.cfg.default_model
    buttons = []
    for spec in services.cfg.models:
        label = f'✅ {spec.name}' if spec.name == current else spec.name
        buttons.append([InlineKeyboardButton(label, callback_data=f'model:{spec.name}')])
    return InlineKeyboardMarkup(buttons)


@is_authorized
async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    current = await services.db.get_selected_model(update.effective_user.id)
    lines = ['Choose the AI model. Current selection is marked with ✅.\n']
    for spec in services.cfg.models:
        caps = [c for c, on in (('vision', spec.vision), ('tools', spec.tools)) if on]
        lines.append(f'* {spec.name}' + (f' ({", ".join(caps)})' if caps else ''))
    await update.effective_message.reply_text(
        '\n'.join(lines), reply_markup=_model_keyboard(services, current))


@is_authorized
async def model_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    query = update.callback_query
    await query.answer()
    name = query.data.removeprefix('model:')
    user_id = update.effective_user.id
    if not await services.registry.select(user_id, name):
        await query.edit_message_text('This model is not available anymore.')
        return
    logger.info(f'User {user_id} switched model to {name}')
    await query.edit_message_text(f'Model switched to {name}.')


# ---- memory ----

def _memory_keyboard(memories) -> InlineKeyboardMarkup | None:
    if not memories:
        return None
    rows = []
    row = []
    for index, memory in enumerate(memories, 1):
        row.append(InlineKeyboardButton(f'🗑 {index}',
                                        callback_data=f'memory:del:{memory["id"]}'))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton('🧹 Clear all', callback_data='memory:clear')])
    return InlineKeyboardMarkup(rows)


def _memory_text(memories) -> str:
    if not memories:
        return 'I have no memories about you.'
    lines = ['What I remember about you:\n']
    lines += [f'{i}. {m["content"]}' for i, m in enumerate(memories, 1)]
    lines.append('\nUse the buttons to delete a memory by its number.')
    return '\n'.join(lines)


@is_authorized
async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    if services.chat.memory is None:
        await update.effective_message.reply_text('Memory is not enabled.')
        return
    memories = await services.chat.memory.list(update.effective_user.id)
    await update.effective_message.reply_text(
        _memory_text(memories), reply_markup=_memory_keyboard(memories))


@is_authorized
async def memory_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    query = update.callback_query
    await query.answer()
    if services.chat.memory is None:
        return
    user_id = update.effective_user.id
    action = query.data.removeprefix('memory:')
    if action == 'clear':
        await services.chat.memory.clear(user_id)
    elif action.startswith('del:'):
        await services.chat.memory.delete(user_id, int(action.removeprefix('del:')))
    memories = await services.chat.memory.list(user_id)
    await query.edit_message_text(_memory_text(memories),
                                  reply_markup=_memory_keyboard(memories))


# ---- per-user tool toggles ----

def _tool_groups(services) -> list[str]:
    from sirchatalot.tools import ToolContext, registry as tool_registry
    chat = services.chat
    probe = ToolContext(user_id=0, image_engine=chat.image_engine,
                        web_search=chat.web_search, url_opener=chat.url_opener,
                        files_rag=chat.files_rag, memory=chat.memory)
    return tool_registry.groups(probe)


def _tools_view(services, disabled: set[str]):
    groups = _tool_groups(services)
    mcp_names = {s.name for s in services.cfg.mcp_servers}
    if not groups:
        return 'No tools are available in this deployment.', None
    rows = []
    for group in groups:
        label = f'MCP: {group}' if group in mcp_names else group
        mark = '🚫' if group in disabled else '✅'
        rows.append([InlineKeyboardButton(f'{mark} {label}',
                                          callback_data=f'tools:{group}')])
    text = ('Tools available to the AI. Tap to enable/disable a tool '
            '(or a whole MCP server) for your chats.')
    return text, InlineKeyboardMarkup(rows)


@is_authorized
async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    disabled = await services.db.get_disabled_tools(update.effective_user.id)
    text, keyboard = _tools_view(services, disabled)
    await update.effective_message.reply_text(text, reply_markup=keyboard)


@is_authorized
async def tools_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    group = query.data.removeprefix('tools:')
    disabled = await services.db.get_disabled_tools(user_id)
    disabled ^= {group}
    await services.db.set_disabled_tools(user_id, disabled)
    logger.info(f'User {user_id} toggled tool group {group} '
                f'({"off" if group in disabled else "on"})')
    text, keyboard = _tools_view(services, disabled)
    await query.edit_message_text(text, reply_markup=keyboard)


# ---- styles ----

@is_authorized
async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    styles = services.cfg.styles
    if not styles:
        await update.effective_message.reply_text('No styles are configured.')
        return
    keyboard = [[InlineKeyboardButton(name, callback_data=f'style:{name}')]
                for name in styles]
    keyboard.append([InlineKeyboardButton('[Default]', callback_data='style:default')])
    msg = ('Please choose a style for the bot.\n'
           'Your current chat session will be deleted.\n\n'
           'Styles description:\n')
    for name, style in styles.items():
        msg += f'* {name}: {style.description}\n'
    await update.effective_message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))


@is_authorized
async def style_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    query = update.callback_query
    await query.answer()
    name = query.data.removeprefix('style:')
    user = update.effective_user
    style = None if name == 'default' else name
    if not await services.chat.set_style(user.id, style):
        await query.edit_message_text('This style is not available.')
        return
    logger.info(f'User {user.id} switched style to {name}')
    outcome = await services.chat.process_text(
        user.id, f"Hi, I'm {user.full_name}! Please introduce yourself.")
    await query.edit_message_text(outcome.text if outcome and outcome.text
                                  else 'Style changed.')


# ---- messages ----

@is_authorized
async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    status = StatusReporter(update)
    async with typing_action(context, update.effective_chat.id):
        outcome = await services.chat.process_text(update.effective_user.id,
                                                   update.message.text,
                                                   on_status=status)
    await status.cleanup()
    await _reply_outcome(update, context, outcome)


@is_authorized
async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''Regenerate the answer to the last message.'''
    services = get_services(context)
    user_id = update.effective_user.id
    status = StatusReporter(update)
    async with typing_action(context, update.effective_chat.id):
        outcome = await services.chat.retry(user_id, on_status=status)
    await status.cleanup()
    if outcome is None:
        await update.effective_message.reply_text('Nothing to retry yet.')
        return
    # drop the previous answer from the chat, then post the new one
    await _delete_tracked(update, context, user_id)
    await _reply_outcome(update, context, outcome)


@is_authorized
async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    '''Remove the last exchange from the history.'''
    services = get_services(context)
    user_id = update.effective_user.id
    if await services.chat.undo(user_id):
        await _delete_tracked(update, context, user_id)
        await update.effective_message.reply_text(
            'Last exchange removed. The conversation continues from the previous point.')
    else:
        await update.effective_message.reply_text('Nothing to undo.')


@is_authorized
async def answer_voice_or_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    if services.chat.audio_engine is None:
        await update.effective_message.reply_text('Sorry, speech-to-text is not available.')
        return
    media = update.message.voice or update.message.video or update.message.video_note
    async with typing_action(context, update.effective_chat.id):
        tg_file = await context.bot.get_file(media.file_id)
        extension = os.path.splitext(tg_file.file_path or '')[1] or (
            '.ogg' if update.message.voice else '.mp4')
        os.makedirs(VOICE_DIR, exist_ok=True)
        file_path = os.path.join(VOICE_DIR, f'{media.file_unique_id}{extension}')
        status = StatusReporter(update)
        try:
            await tg_file.download_to_drive(custom_path=file_path)
            result = await services.chat.process_audio(update.effective_user.id, file_path,
                                                       on_status=status)
        finally:
            await status.cleanup()
            if os.path.exists(file_path):
                os.remove(file_path)
    if isinstance(result, str):
        await send_message(update, result,
                           reply_to_message=services.cfg.telegram.reply_to_message)
    else:
        await _reply_outcome(update, context, result)


@is_authorized
async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    user_id = update.effective_user.id
    spec = await services.registry.spec_for_user(user_id)
    if not spec.vision:
        await update.effective_message.reply_text(
            f'Your current model ({spec.name}) does not support images. '
            f'Use /model to switch to a vision-capable model.')
        return
    try:
        tg_file = await context.bot.get_file(update.message.photo[-1].file_id)
        image_bytes = await tg_file.download_as_bytearray()
        image_b64 = await resize_image_b64(bytes(image_bytes),
                                           services.cfg.chat.image_size)
        if image_b64 is None or not await services.chat.add_image(user_id, image_b64):
            await update.effective_message.reply_text(
                'Sorry, something went wrong with image processing.')
            return
        caption = update.message.caption
        if caption:
            status = StatusReporter(update)
            async with typing_action(context, update.effective_chat.id):
                outcome = await services.chat.process_text(user_id, caption,
                                                           on_status=status)
            await status.cleanup()
            await _reply_outcome(update, context, outcome)
        else:
            await update.effective_message.reply_text(
                "Image received. I'll wait for your text before answering to it.")
    except Exception:
        logger.exception(f'Could not process image from user {user_id}')
        await update.effective_message.reply_text(
            'Sorry, something went wrong while processing the image.')


@is_authorized
async def imagine_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    if services.chat.image_engine is None:
        await update.effective_message.reply_text('Sorry, image generation is not supported.')
        return
    # strip the command itself, including the /imagine@botname group-chat form
    prompt = re.sub(r'^/\w+(@\w+)?\s*', '', update.message.text).strip()
    async with typing_action(context, update.effective_chat.id):
        image_bytes, text = await services.chat.imagine(update.effective_user.id, prompt)
    if image_bytes is None:
        await update.effective_message.reply_text(text or GENERIC_ERROR)
        return
    await update.effective_message.reply_photo(photo=image_bytes, caption=text)


# ---- files ----

@is_authorized
async def downloader(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    if services.files_rag is None:
        await update.effective_message.reply_text('Sorry, working with files is not enabled.')
        return
    user_id = update.effective_user.id
    try:
        document = update.message.document
        filename = sanitize_filename(document.file_name)
        tg_file = await context.bot.get_file(document.file_id)
        size_mb = (tg_file.file_size or 0) / 1024 / 1024
        if size_mb > services.cfg.files.max_file_size_mb:
            await update.effective_message.reply_text(
                f'Sorry, the file is too big. Max file size is '
                f'{services.cfg.files.max_file_size_mb} MB.')
            return
        user_dir = os.path.join(FILES_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        file_path = os.path.join(user_dir, filename)
        await tg_file.download_to_drive(custom_path=file_path)
        logger.info(f'File {filename} saved for user {user_id}')
        progress = await update.effective_message.reply_text(
            f'File {filename} was saved. Processing the file...')

        async with typing_action(context, update.effective_chat.id):
            text = await services.files_proc.convert_to_text(file_path)
            if text is None:
                await progress.edit_text('Sorry, could not extract text from the file.')
                return
            processed = await services.files_rag.process_text(text, user_id=user_id,
                                                              filename=filename)
            if not processed:
                await progress.edit_text(
                    'Sorry, could not process the file into the RAG dataset.')
                return
            summary = await services.chat.summarize_text(text[:4096]) or ''
            await services.db.upsert_file(str(user_id), filename, summary, True)
        note = ''
        spec = await services.registry.spec_for_user(user_id)
        if not spec.tools:
            note = (f'\n\n⚠️ Your current model ({spec.name}) does not support tools, '
                    f'so it cannot search this file. Use /model to switch.')
        await progress.edit_text(f'File {filename} was processed.\n\nSummary:\n{summary}{note}')
    except BadRequest as e:
        logger.error(f'File download failed: {e}')
        await update.effective_message.reply_text(
            'Sorry, it seems like the file is too big. Telegram limits bot file '
            'downloads to 20 MB. Please try a smaller file.')
    except Exception:
        logger.exception(f'Error processing file from user {user_id}')
        await update.effective_message.reply_text(
            'Sorry, something went wrong while processing the file.')


@is_authorized
async def list_files_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    if services.files_rag is None:
        await update.effective_message.reply_text('Sorry, working with files is not enabled.')
        return
    user_files = await services.db.list_files(str(update.effective_user.id))
    common_files = await services.db.list_files('common')
    if not user_files and not common_files:
        await update.effective_message.reply_text('No files found.')
        return
    text = ''
    if user_files:
        text += '📁 *Your Files:*\n\n'
        text += ''.join(f'{i}. 📄 `{f["filename"]}`\n' for i, f in enumerate(user_files, 1))
    if common_files:
        text += '📁 *Common Files:*\n\n'
        text += ''.join(f'{i}. 📄 `{f["filename"]}`\n' for i, f in enumerate(common_files, 1))
    await send_message(update, text)


def _file_key(filename: str) -> str:
    '''Short stable id for callback_data (which is limited to 64 bytes).'''
    import hashlib
    return hashlib.sha1(filename.encode('utf-8')).hexdigest()[:16]


async def _files_view(services, user_id: int):
    files = await services.db.list_files(str(user_id))
    if not files:
        return 'No files found.', None
    lines = ['Your files — tap to delete one:\n']
    rows = []
    for i, f in enumerate(files, 1):
        lines.append(f'{i}. {f["filename"]}')
        rows.append([InlineKeyboardButton(f'🗑 {i}. {f["filename"][:40]}',
                                          callback_data=f'files:del:{_file_key(f["filename"])}')])
    rows.append([InlineKeyboardButton('🧹 Delete all files', callback_data='files:clear')])
    return '\n'.join(lines), InlineKeyboardMarkup(rows)


async def _delete_one_file(services, user_id: int, filename: str) -> None:
    path = os.path.join(FILES_DIR, str(user_id), filename)
    if os.path.exists(path):
        os.remove(path)
    await services.files_rag.remove_file(user_id, filename)
    await services.db.delete_file(str(user_id), filename)
    logger.info(f'File {filename} deleted for user {user_id}')


@is_authorized
async def delete_files_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    if services.files_rag is None:
        await update.effective_message.reply_text('Sorry, working with files is not enabled.')
        return
    text, keyboard = await _files_view(services, update.effective_user.id)
    await update.effective_message.reply_text(text, reply_markup=keyboard)


@is_authorized
async def files_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    query = update.callback_query
    await query.answer()
    if services.files_rag is None:
        return
    user_id = update.effective_user.id
    action = query.data.removeprefix('files:')
    try:
        if action == 'clear':
            user_dir = os.path.join(FILES_DIR, str(user_id))
            if os.path.exists(user_dir):
                for name in os.listdir(user_dir):
                    os.remove(os.path.join(user_dir, name))
            await services.files_rag.remove_user(user_id)
            await services.db.delete_files(str(user_id))
        elif action.startswith('del:'):
            key = action.removeprefix('del:')
            for f in await services.db.list_files(str(user_id)):
                if _file_key(f['filename']) == key:
                    await _delete_one_file(services, user_id, f['filename'])
                    break
        text, keyboard = await _files_view(services, user_id)
        await query.edit_message_text(text, reply_markup=keyboard)
    except Exception:
        logger.exception(f'Error deleting files for user {user_id}')
        await query.edit_message_text('Sorry, something went wrong while deleting files.')
