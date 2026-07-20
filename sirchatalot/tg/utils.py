'''Telegram helpers: MarkdownV2 rendering with fallback, typing indicator,
image resizing.'''

import asyncio
import base64
import contextlib
import io

import telegramify_markdown
from telegram import Update
from telegram.constants import ChatAction

from sirchatalot.logging_setup import get_logger

logger = get_logger('tg')

MAX_MESSAGE_LENGTH = 4096
# MarkdownV2 escaping can grow the text, keep headroom in source chunks
SOURCE_CHUNK_LENGTH = 3400


def split_for_telegram(text: str, limit: int = SOURCE_CHUNK_LENGTH) -> list[str]:
    '''Split text into chunks, preferring paragraph and then line boundaries so
    markdown structure survives the split.'''
    parts = []
    while len(text) > limit:
        cut = text.rfind('\n\n', 0, limit)
        if cut < limit // 2:
            cut = text.rfind('\n', 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip('\n')
    if text:
        parts.append(text)
    return parts


async def send_message(update: Update, text: str, reply_to_message: bool = False) -> list:
    '''
    Send text rendered as Telegram MarkdownV2 (converted from the model's
    GitHub-style markdown), falling back to plain text per chunk.
    Returns the sent Message objects.
    '''
    message = update.effective_message
    if message is None or not text:
        return []
    sent = []
    for index, part in enumerate(split_for_telegram(text)):
        reply_id = message.message_id if (index == 0 and reply_to_message) else None
        try:
            rendered = telegramify_markdown.markdownify(part)
            sent.append(await message.reply_text(rendered, parse_mode='MarkdownV2',
                                                 reply_to_message_id=reply_id))
        except Exception as e:
            logger.debug(f'MarkdownV2 send failed ({e}), falling back to plain text')
            for plain in split_for_telegram(part, MAX_MESSAGE_LENGTH):
                sent.append(await message.reply_text(plain, reply_to_message_id=reply_id))
                reply_id = None
    return sent


class StatusReporter:
    '''Live tool-activity status: a small message created on first update,
    edited on subsequent ones and deleted before the final answer.'''

    def __init__(self, update: Update):
        self.update = update
        self.message = None
        self._last_text = None

    async def __call__(self, text: str) -> None:
        if not text or text == self._last_text:
            return
        self._last_text = text
        try:
            if self.message is None:
                self.message = await self.update.effective_message.reply_text(text)
            else:
                await self.message.edit_text(text)
        except Exception:
            logger.debug('Could not update status message', exc_info=True)

    async def cleanup(self) -> None:
        if self.message is not None:
            try:
                await self.message.delete()
            except Exception:
                logger.debug('Could not delete status message', exc_info=True)
            self.message = None


@contextlib.asynccontextmanager
async def typing_action(context, chat_id: int):
    '''Keep the "typing..." indicator alive while the body runs (Telegram shows
    it for ~5 seconds per send, so it is refreshed periodically).'''
    async def loop():
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id,
                                                   action=ChatAction.TYPING)
            except Exception:
                pass
            await asyncio.sleep(4.5)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def resize_image_b64(image_bytes: bytes, max_side: int) -> str | None:
    '''Downscale an image to max_side on the long side, return base64 JPEG.'''
    def resize() -> str:
        from PIL import Image
        image = Image.open(io.BytesIO(image_bytes))
        width, height = image.size
        if max(width, height) > max_side:
            if width >= height:
                new_size = (max_side, max(int(height / width * max_side), 1))
            else:
                new_size = (max(int(width / height * max_side), 1), max_side)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    try:
        return await asyncio.to_thread(resize)
    except Exception:
        logger.exception('Could not resize image')
        return None
