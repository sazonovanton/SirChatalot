'''
Image generation via the OpenAI images API (DALL-E / gpt-image-1 / any
OpenAI-compatible image provider).
'''

import re
import time

import openai
from openai import AsyncOpenAI

from sirchatalot.config import ImageGenConfig
from sirchatalot.engine import hashed_user
from sirchatalot.logging_setup import get_logger

logger = get_logger('images')

# dall-e-2/3 accept style/response_format/standard-hd quality; gpt-image-1 and
# most compatible providers reject them and return b64 by default
ORIENTATION_SIZES = {
    'dall-e': {'landscape': '1792x1024', 'portrait': '1024x1792'},
    'other': {'landscape': '1536x1024', 'portrait': '1024x1536'},
}


def _is_dalle(model: str) -> bool:
    return model.lower().startswith('dall-e')


# OpenRouter chat-mode image_config (providers clamp to their supported subset)
ALLOWED_RATIOS = {'1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3',
                  '4:5', '5:4', '21:9', '9:21'}
ALLOWED_SIZES = {'512': '512', '1K': '1K', '2K': '2K', '4K': '4K'}
ORIENTATION_RATIOS = {'landscape': '16:9', 'portrait': '9:16', 'square': '1:1'}


def parse_image_config(prompt: str) -> tuple[str, dict]:
    '''
    Extract chat-mode image flags from a prompt, returning (cleaned_prompt, config).
    Flags: --ratio W:H, --res 512|1K|2K|4K, --horizontal/--vertical/--square.
    '''
    config = {}
    m = re.search(r'--ratio\s+(\d+:\d+)', prompt)
    if m and m.group(1) in ALLOWED_RATIOS:
        config['aspect_ratio'] = m.group(1)
    prompt = re.sub(r'--ratio\s+\S+', '', prompt)
    m = re.search(r'--res\s+(\S+)', prompt)
    if m and m.group(1).upper().replace('к', 'K') in ALLOWED_SIZES:
        config['image_size'] = ALLOWED_SIZES[m.group(1).upper().replace('к', 'K')]
    prompt = re.sub(r'--res\s+\S+', '', prompt)
    for flag, ratio in (('--horizontal', '16:9'), ('--vertical', '9:16'),
                        ('--square', '1:1')):
        if flag in prompt:
            config.setdefault('aspect_ratio', ratio)
            prompt = prompt.replace(flag, '')
    return prompt.strip(), config


class ImageEngine:
    def __init__(self, cfg: ImageGenConfig, end_user_id: bool = True,
                 proxy: str | None = None):
        self.cfg = cfg
        self.end_user_id = end_user_id
        from sirchatalot.engine import openai_http_client
        self.client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url,
                                  http_client=openai_http_client(proxy))
        self._rate_events: dict[int, list[float]] = {}

    def rate_limited(self, user_id) -> bool:
        if self.cfg.rate_limit is None or user_id is None:
            return False
        now = time.time()
        events = [t for t in self._rate_events.get(user_id, ())
                  if now - t < self.cfg.rate_limit.window_seconds]
        if len(events) >= self.cfg.rate_limit.count:
            self._rate_events[user_id] = events
            return True
        events.append(now)
        self._rate_events[user_id] = events
        # keep the dict from growing unboundedly across users
        for uid in [u for u, ts in self._rate_events.items()
                    if not ts or now - ts[-1] >= self.cfg.rate_limit.window_seconds]:
            del self._rate_events[uid]
        return False

    def _rate_limit_message(self) -> str:
        limit = self.cfg.rate_limit
        return (f'Image generation is rate limited (only {limit.count} images per '
                f'{round(limit.window_seconds / 60)} minutes are allowed). '
                f'Please try again later.')

    async def imagine(self, prompt: str, user_id=None) -> tuple[str | None, str | None]:
        '''
        Generate an image for the /imagine command.
        Prompt flags: --natural/--vivid, --sd/--hd, --horizontal/--vertical, --revision.
        Returns (b64_image, caption): (None, message) on failure/rate limit.
        '''
        if self.rate_limited(user_id):
            return None, self._rate_limit_message()
        prompt = prompt.replace('—', '--')
        if self.cfg.api == 'chat':
            prompt, image_config = parse_image_config(prompt)
            if not prompt:
                return None, 'No text prompt was given. Please try again.'
            b64_image, caption = await self._generate(
                prompt, None, None, None, user_id, image_config=image_config)
            return (b64_image, caption) if b64_image else (None, caption)
        sizes = ORIENTATION_SIZES['dall-e' if _is_dalle(self.cfg.model) else 'other']
        size, style, quality = self.cfg.size, self.cfg.style, self.cfg.quality
        revision = '--revision' in prompt
        flags = {'--revision': None, '--natural': ('style', 'natural'), '--vivid': ('style', 'vivid'),
                 '--sd': ('quality', 'standard'), '--hd': ('quality', 'hd'),
                 '--horizontal': ('size', sizes['landscape']),
                 '--vertical': ('size', sizes['portrait'])}
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
                             image_style: str | None = None,
                             user_id=None) -> tuple[str | None, str | None]:
        '''Tool entry point. Returns (b64_image, revised_prompt/error message).'''
        if self.rate_limited(user_id):
            return None, self._rate_limit_message()
        if self.cfg.api == 'chat':
            image_config = {}
            if image_orientation in ORIENTATION_RATIOS:
                image_config['aspect_ratio'] = ORIENTATION_RATIOS[image_orientation]
            return await self._generate(prompt, None, None, None, user_id,
                                        image_config=image_config)
        sizes = ORIENTATION_SIZES['dall-e' if _is_dalle(self.cfg.model) else 'other']
        size = sizes.get(image_orientation, '1024x1024')
        style = image_style if image_style in ('natural', 'vivid') else self.cfg.style
        return await self._generate(prompt, size, style, self.cfg.quality, user_id)

    async def _generate(self, prompt, size, style, quality, user_id, image_config=None):
        try:
            if self.cfg.api == 'chat':
                return await self._generate_via_chat(prompt, image_config)
            kwargs = {}
            if self.end_user_id and user_id is not None:
                kwargs['user'] = hashed_user(user_id)
            if _is_dalle(self.cfg.model):
                kwargs.update(response_format='b64_json', style=style, quality=quality)
            response = await self.client.images.generate(
                model=self.cfg.model, prompt=prompt, size=size, n=1, **kwargs,
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
        except openai.NotFoundError as e:
            logger.error(f'Image model/endpoint not found: {e}')
            return None, (f'The configured image model "{self.cfg.model}" does not support '
                          f'image generation on this endpoint. Please check the '
                          f'image_generation section of the config (model and api mode).')
        except Exception:
            logger.exception('Could not generate image')
            return None, None

    async def _generate_via_chat(self, prompt, image_config=None):
        '''
        Image generation through chat completions with modalities (the OpenRouter
        way, e.g. google/gemini-2.5-flash-image). Tries in order, stopping at the
        first success:
          * image+text with image_config (aspect ratio / size)
          * image+text without config (models that reject image_config)
          * image-only variants of both (some FLUX models reject image+text)
        '''
        attempts = []
        for modalities in (['image', 'text'], ['image']):
            if image_config:
                attempts.append({'modalities': modalities, 'image_config': image_config})
            attempts.append({'modalities': modalities})

        last_error = None
        for extra in attempts:
            try:
                response = await self.client.chat.completions.create(
                    model=self.cfg.model,
                    messages=[{'role': 'user', 'content': prompt}],
                    extra_body=extra,
                )
            except (openai.NotFoundError, openai.BadRequestError) as e:
                last_error = e
                logger.warning(f'Model {self.cfg.model} rejected image request '
                               f'({list(extra)}): {e}')
                continue
            message = response.choices[0].message
            b64 = extract_b64_from_chat_message(message)
            if b64 is not None:
                caption = (message.content or '').strip() or None
                return b64, caption
            logger.error(f'Chat image generation returned no image (model '
                         f'{self.cfg.model}, {list(extra)})')
        if last_error is not None:
            raise last_error   # formatted by _generate's error branches
        return None, (f'The model "{self.cfg.model}" did not return an image. '
                      f'Check that it is an image-capable model.')


def extract_b64_from_chat_message(message) -> str | None:
    '''Pull the first base64 image out of a chat message with an `images` field
    (data URLs like data:image/png;base64,...).'''
    images = getattr(message, 'images', None)
    if not images and getattr(message, 'model_extra', None):
        images = message.model_extra.get('images')
    if not images:
        return None
    first = images[0]
    if not isinstance(first, dict):
        first = getattr(first, 'model_dump', lambda: {})()
    url = ((first.get('image_url') or {}).get('url')
           if isinstance(first.get('image_url'), dict) else first.get('url', ''))
    if not url or not url.startswith('data:'):
        return None
    _, _, payload = url.partition('base64,')
    return payload or None
