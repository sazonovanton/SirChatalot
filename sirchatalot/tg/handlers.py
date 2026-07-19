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
from sirchatalot.tg.utils import resize_image_b64, send_message

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


async def _reply_outcome(update: Update, context, outcome) -> None:
    services = get_services(context)
    if outcome is None:
        await update.effective_message.reply_text(GENERIC_ERROR)
        return
    for image_bytes in outcome.media:
        await update.effective_message.reply_photo(photo=image_bytes)
    if outcome.text:
        await send_message(update, outcome.text,
                           reply_to_message=services.cfg.telegram.reply_to_message)


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
    text += '/delete - Delete chat history\n'
    text += '/statistics - Show statistics\n'
    text += '/limit - Check your rate limit\n'
    text += '/style - Choose a style for the bot\n'
    text += '/model - Choose the AI model\n'
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
        text += ('\nImage generation flags for /imagine: `--natural`, `--vivid`, `--sd`, '
                 '`--hd`, `--horizontal`, `--vertical`, `--revision`.\n'
                 'Example: `/imagine a cat on a table --natural`\n'
                 'You can also just ask the bot to draw something.\n')
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
    await context.bot.send_chat_action(chat_id=update.effective_chat.id,
                                       action=ChatAction.TYPING)
    outcome = await services.chat.process_text(update.effective_user.id,
                                               update.message.text)
    await _reply_outcome(update, context, outcome)


@is_authorized
async def answer_voice_or_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    if services.chat.audio_engine is None:
        await update.effective_message.reply_text('Sorry, speech-to-text is not available.')
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id,
                                       action=ChatAction.TYPING)
    media = update.message.voice or update.message.video or update.message.video_note
    tg_file = await context.bot.get_file(media.file_id)
    extension = os.path.splitext(tg_file.file_path or '')[1] or (
        '.ogg' if update.message.voice else '.mp4')
    os.makedirs(VOICE_DIR, exist_ok=True)
    file_path = os.path.join(VOICE_DIR, f'{media.file_unique_id}{extension}')
    try:
        await tg_file.download_to_drive(custom_path=file_path)
        result = await services.chat.process_audio(update.effective_user.id, file_path)
    finally:
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
            outcome = await services.chat.process_text(user_id, caption)
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
    await context.bot.send_chat_action(chat_id=update.effective_chat.id,
                                       action=ChatAction.TYPING)
    prompt = update.message.text.removeprefix('/imagine').strip()
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
        await context.bot.send_chat_action(chat_id=update.effective_chat.id,
                                           action=ChatAction.TYPING)
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

        text = await services.files_proc.convert_to_text(file_path)
        if text is None:
            await progress.edit_text('Sorry, could not extract text from the file.')
            return
        processed = await services.files_rag.process_text(text, user_id=user_id,
                                                          filename=filename)
        if not processed:
            await progress.edit_text('Sorry, could not process the file into the RAG dataset.')
            return
        summary = await services.chat.summarize_text(text[:4096]) or ''
        await services.db.upsert_file(str(user_id), filename, summary, True)
        await progress.edit_text(f'File {filename} was processed.\n\nSummary:\n{summary}')
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


@is_authorized
async def delete_files_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    if services.files_rag is None:
        await update.effective_message.reply_text('Sorry, working with files is not enabled.')
        return
    user_id = update.effective_user.id
    try:
        user_dir = os.path.join(FILES_DIR, str(user_id))
        if os.path.exists(user_dir):
            for name in os.listdir(user_dir):
                os.remove(os.path.join(user_dir, name))
        removed = await services.files_rag.remove_user(user_id)
        await services.db.delete_files(str(user_id))
        if removed:
            await update.effective_message.reply_text('Files and RAG dataset were deleted.')
        else:
            await update.effective_message.reply_text('Error removing the RAG dataset.')
    except Exception:
        logger.exception(f'Error deleting files for user {user_id}')
        await update.effective_message.reply_text(
            'Sorry, something went wrong while deleting files.')
