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
            if self.cfg.api == 'chat':
                return await self._transcribe_via_chat(converted)
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

    async def _transcribe_via_chat(self, file_path: str) -> str | None:
        '''Transcription by a multimodal model via chat completions with an
        input_audio content part (the OpenRouter way).'''
        import base64
        with open(file_path, 'rb') as f:
            audio_b64 = base64.b64encode(f.read()).decode('utf-8')
        response = await self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[{'role': 'user', 'content': [
                {'type': 'text',
                 'text': 'Transcribe this audio recording. Output the transcript '
                         'text only, in the original language, without commentary.'},
                {'type': 'input_audio',
                 'input_audio': {'data': audio_b64, 'format': self.cfg.format}},
            ]}],
        )
        text = (response.choices[0].message.content or '').strip()
        return text or None
