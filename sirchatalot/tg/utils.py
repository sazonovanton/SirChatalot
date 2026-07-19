'''Telegram helpers: message sending with markdown fallback, image resizing.'''

import asyncio
import base64
import io

from telegram import Update
from telegram.helpers import escape_markdown

from sirchatalot.logging_setup import get_logger

logger = get_logger('tg')

MAX_MESSAGE_LENGTH = 4096


async def send_message(update: Update, text: str, reply_to_message: bool = False) -> None:
    '''
    Send text in chunks, trying plain markdown first and falling back to
    escaped MarkdownV2 and then to plain text.
    '''
    message = update.effective_message
    if message is None or not text:
        return
    parts = [text[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(text), MAX_MESSAGE_LENGTH)]
    for index, part in enumerate(parts):
        reply_id = message.message_id if (index == 0 and reply_to_message) else None
        try:
            await message.reply_markdown(part, reply_to_message_id=reply_id)
        except Exception:
            try:
                await message.reply_markdown_v2(
                    escape_markdown(part, version=2), reply_to_message_id=reply_id)
            except Exception:
                await message.reply_text(part, reply_to_message_id=reply_id)


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
