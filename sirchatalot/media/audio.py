'''
Speech-to-text via the OpenAI audio API (Whisper or compatible).
'''

import asyncio
import os

import openai
from openai import AsyncOpenAI

from sirchatalot.config import AudioConfig
from sirchatalot.logging_setup import get_logger

logger = get_logger('audio')


class AudioEngine:
    def __init__(self, cfg: AudioConfig, proxy: str | None = None):
        self.cfg = cfg
        from sirchatalot.engine import openai_http_client
        self.client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url,
                                  http_client=openai_http_client(proxy))

    async def duration_seconds(self, file_path: str) -> float:
        from pydub import AudioSegment
        audio = await asyncio.to_thread(AudioSegment.from_file, file_path)
        return len(audio) / 1000.0

    async def _convert(self, file_path: str) -> str:
        '''Convert to the configured format off the event loop (pydub/ffmpeg).'''
        from pydub import AudioSegment

        def convert():
            converted = f'{file_path}.{self.cfg.format}'
            audio = AudioSegment.from_file(file_path)
            audio.export(converted, format=self.cfg.format)
            return converted

        return await asyncio.to_thread(convert)

    async def transcribe(self, file_path: str) -> str | None:
        converted = None
        try:
            converted = await self._convert(file_path)
            with open(converted, 'rb') as audio:
                transcript = await self.client.audio.transcriptions.create(
                    model=self.cfg.model, file=audio,
                )
            return transcript.text
        except openai.RateLimitError as e:
            logger.error(f'Transcription rate limited: {e}')
            return None
        except Exception:
            logger.exception('Could not transcribe audio')
            return None
        finally:
            if converted is not None and os.path.exists(converted):
                os.remove(converted)
