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
