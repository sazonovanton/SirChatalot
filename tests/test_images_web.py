'''Tests for chat-mode image generation and local page extraction.'''

from types import SimpleNamespace

import pytest

from sirchatalot.config import ImageGenConfig, UrlOpenConfig
from sirchatalot.media.images import extract_b64_from_chat_message
from sirchatalot.tools.web import UrlOpener


def message(**kwargs):
    return SimpleNamespace(model_extra=None, content=None, **kwargs)


def test_extract_b64_from_chat_message():
    msg = message(images=[{'type': 'image_url',
                           'image_url': {'url': 'data:image/png;base64,QUJD'}}])
    assert extract_b64_from_chat_message(msg) == 'QUJD'


def test_extract_b64_from_model_extra():
    msg = SimpleNamespace(
        content='here you go',
        model_extra={'images': [{'image_url': {'url': 'data:image/png;base64,WFla'}}]})
    assert extract_b64_from_chat_message(msg) == 'WFla'


def test_extract_b64_missing_or_invalid():
    assert extract_b64_from_chat_message(message(images=None)) is None
    assert extract_b64_from_chat_message(message(images=[])) is None
    # a plain https URL (not a data URL) is not accepted
    msg = message(images=[{'image_url': {'url': 'https://example.com/x.png'}}])
    assert extract_b64_from_chat_message(msg) is None


def test_image_api_config_validation():
    assert ImageGenConfig(api_key='k', api='chat').api == 'chat'
    assert ImageGenConfig(api_key='k').api == 'images'
    with pytest.raises(Exception, match='images.*chat'):
        ImageGenConfig(api_key='k', api='completions')


def test_local_extraction_uses_trafilatura():
    opener = UrlOpener(UrlOpenConfig(trim_length=None))
    html = ('<html><body><nav>Home About Login Register Cookie settings</nav>'
            '<article><h1>The Article</h1>'
            + ''.join(f'<p>Paragraph {i} with meaningful sentence content '
                      f'about the topic at hand.</p>' for i in range(8))
            + '</article><footer>© 2026 Junk Corp · Privacy · Terms</footer>'
            '</body></html>').encode()
    text = opener._parse(html)
    assert text is not None
    assert 'Paragraph 3' in text
    assert 'Privacy' not in text  # boilerplate stripped


def test_parse_falls_back_to_bs4_on_garbage():
    opener = UrlOpener(UrlOpenConfig(trim_length=None))
    html = b'<body><p>tiny but real text of the page</p></body>'
    assert 'tiny but real' in (opener._parse(html) or '')


def test_audio_api_config_validation():
    from sirchatalot.config import AudioConfig
    assert AudioConfig(api_key='k').api == 'transcriptions'
    assert AudioConfig(api_key='k', api='chat', format='wav').api == 'chat'
    with pytest.raises(Exception, match='transcriptions.*chat'):
        AudioConfig(api_key='k', api='whisper')
    with pytest.raises(Exception, match='wav or mp3'):
        AudioConfig(api_key='k', api='chat', format='ogg')


async def test_chat_image_fallback_to_image_only():
    '''image+text rejected -> retry with image-only succeeds.'''
    from types import SimpleNamespace
    import openai
    from sirchatalot.config import ImageGenConfig
    from sirchatalot.media.images import ImageEngine

    engine = ImageEngine(ImageGenConfig(api_key='k', api='chat', model='flux-image-only'))
    calls = []

    async def fake_create(*, model, messages, extra_body, **k):
        calls.append(extra_body['modalities'])
        if extra_body['modalities'] == ['image', 'text']:
            raise openai.NotFoundError(
                'no modalities', response=SimpleNamespace(status_code=404, request=None,
                                                          headers={}), body=None)
        msg = SimpleNamespace(
            content=None, model_extra=None,
            images=[{'image_url': {'url': 'data:image/png;base64,SU1H'}}])
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    engine.client.chat.completions.create = fake_create
    b64, caption = await engine._generate('a cat', '1024x1024', 'vivid', 'standard', None)
    assert b64 == 'SU1H'
    assert caption is None                      # image-only, no text
    assert calls == [['image', 'text'], ['image']]   # tried both, in order


async def test_chat_image_with_text_caption():
    from types import SimpleNamespace
    from sirchatalot.config import ImageGenConfig
    from sirchatalot.media.images import ImageEngine

    engine = ImageEngine(ImageGenConfig(api_key='k', api='chat', model='gemini-image'))

    async def fake_create(*, model, messages, extra_body, **k):
        msg = SimpleNamespace(
            content='here is your cat', model_extra=None,
            images=[{'image_url': {'url': 'data:image/png;base64,QQ=='}}])
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    engine.client.chat.completions.create = fake_create
    b64, caption = await engine._generate('a cat', '1024x1024', 'vivid', 'standard', None)
    assert b64 == 'QQ==' and caption == 'here is your cat'


def test_parse_image_config():
    from sirchatalot.media.images import parse_image_config
    p, cfg = parse_image_config('a cat --ratio 16:9 --res 2K')
    assert p == 'a cat' and cfg == {'aspect_ratio': '16:9', 'image_size': '2K'}
    p, cfg = parse_image_config('sunset --horizontal')
    assert p == 'sunset' and cfg == {'aspect_ratio': '16:9'}
    p, cfg = parse_image_config('portrait --vertical')
    assert cfg == {'aspect_ratio': '9:16'}
    p, cfg = parse_image_config('logo --square')
    assert cfg == {'aspect_ratio': '1:1'}
    # invalid values are dropped, prompt still cleaned of the flag token
    p, cfg = parse_image_config('x --ratio 7:3 --res 8K')
    assert 'aspect_ratio' not in cfg and 'image_size' not in cfg
    # no flags
    p, cfg = parse_image_config('just a prompt')
    assert p == 'just a prompt' and cfg == {}


async def test_chat_image_config_sent_and_fallback():
    from types import SimpleNamespace
    import openai
    from sirchatalot.config import ImageGenConfig
    from sirchatalot.media.images import ImageEngine

    engine = ImageEngine(ImageGenConfig(api_key='k', api='chat', model='gemini-image'))
    sent = []

    async def fake_create(*, model, messages, extra_body, **k):
        sent.append(extra_body)
        # reject the image_config variant, accept the plain one
        if 'image_config' in extra_body:
            raise openai.BadRequestError(
                'bad config', response=SimpleNamespace(status_code=400, request=None,
                                                       headers={}), body=None)
        msg = SimpleNamespace(content=None, model_extra=None,
                              images=[{'image_url': {'url': 'data:image/png;base64,SU1H'}}])
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    engine.client.chat.completions.create = fake_create
    b64, _ = await engine.imagine('a cat --ratio 16:9', user_id=1)
    assert b64 == 'SU1H'
    # first attempt carried the config, then fell back without it
    assert sent[0].get('image_config') == {'aspect_ratio': '16:9'}
    assert 'image_config' not in sent[1]


async def test_chat_image_config_success_first_try():
    from types import SimpleNamespace
    from sirchatalot.config import ImageGenConfig
    from sirchatalot.media.images import ImageEngine

    engine = ImageEngine(ImageGenConfig(api_key='k', api='chat', model='gemini-image'))
    sent = []

    async def fake_create(*, model, messages, extra_body, **k):
        sent.append(extra_body)
        msg = SimpleNamespace(content='ok', model_extra=None,
                              images=[{'image_url': {'url': 'data:image/png;base64,QQ=='}}])
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    engine.client.chat.completions.create = fake_create
    b64, caption = await engine.imagine('a cat --res 4K', user_id=1)
    assert b64 == 'QQ==' and caption == 'ok'
    assert len(sent) == 1
    assert sent[0]['image_config'] == {'image_size': '4K'}
    assert sent[0]['modalities'] == ['image', 'text']
