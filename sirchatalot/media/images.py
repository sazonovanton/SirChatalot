'''
Image generation via the OpenAI images API (DALL-E / gpt-image-1 / any
OpenAI-compatible image provider).
'''

import hashlib
import time

import openai
from openai import AsyncOpenAI

from sirchatalot.config import ImageGenConfig
from sirchatalot.logging_setup import get_logger

logger = get_logger('images')


class ImageEngine:
    def __init__(self, cfg: ImageGenConfig, end_user_id: bool = True):
        self.cfg = cfg
        self.end_user_id = end_user_id
        self.client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        self._rate_events: dict[int, list[float]] = {}

    def rate_limited(self, user_id) -> bool:
        if self.cfg.rate_limit is None or user_id is None:
            return False
        now = time.time()
        events = [t for t in self._rate_events.get(user_id, [])
                  if now - t < self.cfg.rate_limit.window_seconds]
        if len(events) >= self.cfg.rate_limit.count:
            self._rate_events[user_id] = events
            return True
        events.append(now)
        self._rate_events[user_id] = events
        return False

    async def imagine(self, prompt: str, user_id=None) -> tuple[str | None, str | None]:
        '''
        Generate an image for the /imagine command.
        Prompt flags: --natural/--vivid, --sd/--hd, --horizontal/--vertical, --revision.
        Returns (b64_image, caption): (None, message) on failure/rate limit.
        '''
        if self.rate_limited(user_id):
            limit = self.cfg.rate_limit
            return None, (f'Image generation is rate limited (only {limit.count} images per '
                          f'{round(limit.window_seconds / 60)} minutes are allowed). '
                          f'Please try again later.')
        size, style, quality = self.cfg.size, self.cfg.style, self.cfg.quality
        prompt = prompt.replace('—', '--')
        revision = '--revision' in prompt
        flags = {'--revision': None, '--natural': ('style', 'natural'), '--vivid': ('style', 'vivid'),
                 '--sd': ('quality', 'standard'), '--hd': ('quality', 'hd'),
                 '--horizontal': ('size', '1792x1024'), '--vertical': ('size', '1024x1792')}
        applied = {}
        for flag, setting in flags.items():
            if flag in prompt:
                prompt = prompt.replace(flag, '')
                if setting:
                    applied[setting[0]] = setting[1]
        size = applied.get('size', size)
        style = applied.get('style', style)
        quality = applied.get('quality', quality)
        prompt = prompt.strip()
        if not prompt:
            return None, 'No text prompt was given. Please try again.'
        b64_image, revised_prompt = await self._generate(prompt, size, style, quality, user_id)
        if b64_image is None:
            return None, revised_prompt
        return b64_image, (f'Revised prompt: {revised_prompt}' if revision and revised_prompt else None)

    async def generate_image(self, prompt: str, image_orientation: str | None = None,
                             image_style: str | None = None) -> tuple[str | None, str | None]:
        '''Tool entry point. Returns (b64_image, revised_prompt/error message).'''
        size = {'landscape': '1792x1024', 'portrait': '1024x1792'}.get(image_orientation, '1024x1024')
        style = image_style if image_style in ('natural', 'vivid') else self.cfg.style
        return await self._generate(prompt, size, style, self.cfg.quality, None)

    async def _generate(self, prompt, size, style, quality, user_id):
        try:
            user = (hashlib.sha1(str(user_id).encode('utf-8')).hexdigest()
                    if self.end_user_id and user_id is not None else None)
            kwargs = {'user': user} if user else {}
            response = await self.client.images.generate(
                model=self.cfg.model, prompt=prompt, size=size, quality=quality,
                n=1, response_format='b64_json', style=style, **kwargs,
            )
            item = response.data[0]
            return item.b64_json, getattr(item, 'revised_prompt', None)
        except openai.BadRequestError as e:
            logger.error(f'Image generation rejected: {e}')
            if 'content_policy_violation' in str(e):
                return None, ('Your request was rejected because it may violate content policy. '
                              'Please review it and try again.')
            return None, 'Your request was rejected. Please review it and try again.'
        except openai.RateLimitError as e:
            logger.error(f'Image generation rate limited by API: {e}')
            return None, 'Service is getting rate limited. Please try again later.'
        except Exception:
            logger.exception('Could not generate image')
            return None, None
