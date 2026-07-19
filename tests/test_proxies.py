'''Proxy configuration wiring tests.'''

from sirchatalot.config import UrlOpenConfig, WebSearchConfig
from sirchatalot.engine import LLMEngine, openai_http_client
from sirchatalot.model_registry import ModelRegistry
from sirchatalot.tools.web import UrlOpener, make_search_engine
from tests.conftest import make_config


def test_proxies_config_defaults():
    cfg = make_config()
    assert cfg.proxies.telegram is None
    assert cfg.proxies.llm is None
    cfg = make_config(proxies={'telegram': 'http://t:1', 'llm': 'http://l:1',
                               'search': 'http://s:1', 'jina': 'http://j:1'})
    assert cfg.proxies.search == 'http://s:1'


def test_llm_engine_proxy_resolution():
    cfg = make_config()
    spec = cfg.model_spec('primary')
    assert LLMEngine(spec).proxy is None
    assert LLMEngine(spec, default_proxy='http://global:1').proxy == 'http://global:1'
    spec_own = spec.model_copy(update={'proxy': 'http://own:1'})
    assert LLMEngine(spec_own, default_proxy='http://global:1').proxy == 'http://own:1'


async def test_registry_applies_default_llm_proxy(db):
    cfg = make_config(proxies={'llm': 'http://llmproxy:3128'})
    registry = ModelRegistry(cfg, db)
    assert all(e.proxy == 'http://llmproxy:3128' for e in registry.engines.values())


def test_openai_http_client():
    assert openai_http_client(None) is None
    client = openai_http_client('http://p:1')
    assert client is not None


def test_search_and_urlopener_carry_proxy():
    search = make_search_engine(
        WebSearchConfig(provider='tavily', api_key='k'), proxy='http://s:1')
    assert search.proxy == 'http://s:1'
    opener = UrlOpener(UrlOpenConfig(), proxy='http://j:1')
    assert opener.proxy == 'http://j:1'
    assert UrlOpener(UrlOpenConfig()).proxy is None
