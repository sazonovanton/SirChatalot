'''
web_search and url_opener tools.

url_opener is SSRF-hardened: http/https only, hostnames resolving to private,
loopback or link-local addresses are rejected, response size is capped.
'''

import asyncio
import ipaddress
import socket
import urllib.parse

import aiohttp
from bs4 import BeautifulSoup

from sirchatalot.config import UrlOpenConfig, WebSearchConfig
from sirchatalot.logging_setup import get_logger
from sirchatalot.tools import ToolContext, ToolResult, registry

logger = get_logger('web')

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def read_capped(response, cap: int = MAX_RESPONSE_BYTES) -> bytes:
    '''Read the full body up to `cap` bytes. (StreamReader.read(n) returns the
    first buffered chunk only, which silently truncates pages.)'''
    chunks = []
    total = 0
    async for chunk in response.content.iter_chunked(64 * 1024):
        chunks.append(chunk)
        total += len(chunk)
        if total >= cap:
            break
    return b''.join(chunks)[:cap]
# many sites (e.g. Wikipedia) reject the default python client User-Agent
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
    'Accept-Language': 'en,ru;q=0.8',
}


class SearchEngine:
    '''Base for web search providers: fetch JSON, parse into title/link/snippet.'''

    def __init__(self, cfg: WebSearchConfig, proxy: str | None = None):
        self.cfg = cfg
        self.proxy = proxy

    async def search(self, query: str) -> list[dict] | None:
        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                data = await self._fetch(session, query)
            return self._parse(data)[:self.cfg.results]
        except Exception as e:
            logger.error(f'Web search failed ({self.cfg.provider}): {e}')
            return None

    async def _fetch(self, session, query: str) -> dict:
        raise NotImplementedError

    def _parse(self, data: dict) -> list[dict]:
        raise NotImplementedError


class GoogleSearch(SearchEngine):
    async def _fetch(self, session, query):
        params = {'key': self.cfg.api_key, 'cx': self.cfg.cse_id,
                  'q': query, 'num': self.cfg.results}
        async with session.get('https://www.googleapis.com/customsearch/v1',
                               params=params, proxy=self.proxy) as response:
            return await response.json()

    def _parse(self, data):
        return [{'title': i['title'], 'link': i['link'], 'snippet': i.get('snippet', '')}
                for i in data.get('items', [])]


class SearxngSearch(SearchEngine):
    async def _fetch(self, session, query):
        params = {'q': query, 'format': 'json'}
        async with session.get(f'{self.cfg.url.rstrip("/")}/search',
                               params=params, proxy=self.proxy) as response:
            return await response.json()

    def _parse(self, data):
        return [{'title': r.get('title', ''), 'link': r.get('url', ''),
                 'snippet': r.get('content', '')}
                for r in data.get('results', [])]


class TavilySearch(SearchEngine):
    async def _fetch(self, session, query):
        payload = {'api_key': self.cfg.api_key, 'query': query,
                   'max_results': self.cfg.results}
        async with session.post('https://api.tavily.com/search',
                                json=payload, proxy=self.proxy) as response:
            return await response.json()

    def _parse(self, data):
        return [{'title': r.get('title', ''), 'link': r.get('url', ''),
                 'snippet': r.get('content', '')}
                for r in data.get('results', [])]


class BraveSearch(SearchEngine):
    async def _fetch(self, session, query):
        headers = {'X-Subscription-Token': self.cfg.api_key,
                   'Accept': 'application/json'}
        params = {'q': query, 'count': self.cfg.results}
        async with session.get('https://api.search.brave.com/res/v1/web/search',
                               params=params, headers=headers,
                               proxy=self.proxy) as response:
            return await response.json()

    def _parse(self, data):
        return [{'title': r.get('title', ''), 'link': r.get('url', ''),
                 'snippet': r.get('description', '')}
                for r in (data.get('web') or {}).get('results', [])]


SEARCH_PROVIDERS = {
    'google': GoogleSearch,
    'searxng': SearxngSearch,
    'tavily': TavilySearch,
    'brave': BraveSearch,
}


def make_search_engine(cfg: WebSearchConfig, proxy: str | None = None) -> SearchEngine:
    return SEARCH_PROVIDERS[cfg.provider](cfg, proxy=proxy)


def _host_is_private(host: str) -> bool:
    '''Resolve host and check whether any address is non-public.'''
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            return True
    return False


class _SafeResolver(aiohttp.abc.AbstractResolver):
    '''
    DNS resolver that rejects non-public addresses at resolution time, so the
    address actually connected to is the one that was validated (prevents
    DNS-rebinding around a separate pre-flight check).
    '''

    def __init__(self):
        self._inner = aiohttp.resolver.ThreadedResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        results = await self._inner.resolve(host, port, family)
        for entry in results:
            if not ipaddress.ip_address(entry['host']).is_global:
                raise OSError(f'Refusing to connect to non-public address of {host}')
        return results

    async def close(self):
        await self._inner.close()


class UrlOpener:
    def __init__(self, cfg: UrlOpenConfig, proxy: str | None = None):
        self.cfg = cfg
        self.proxy = proxy

    async def check_url(self, url: str) -> str | None:
        '''Returns a rejection reason, or None if the URL is safe to fetch.'''
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return f'URL scheme "{parsed.scheme}" is not allowed'
        if not parsed.hostname:
            return 'URL has no host'
        if await asyncio.to_thread(_host_is_private, parsed.hostname):
            return 'URL host is not allowed'
        return None

    async def open_url(self, url: str) -> str | None:
        if self.cfg.via_jina:
            text = await self._open_via_jina(url)
            if text is not None:
                return text
            logger.warning(f'Jina Reader failed for {url}, falling back to direct fetch')
        return await self._open_direct(url)

    async def _open_via_jina(self, url: str) -> str | None:
        '''Fetch the page through the Jina Reader (returns clean markdown).'''
        reason = await self.check_url(url)
        if reason is not None:
            logger.warning(f'URL rejected ({reason}): {url}')
            return None
        headers = {}
        if self.cfg.jina_api_key:
            headers['Authorization'] = f'Bearer {self.cfg.jina_api_key}'
        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.get(f'https://r.jina.ai/{url}',
                                       headers=headers, proxy=self.proxy) as response:
                    if response.status != 200:
                        logger.warning(f'Jina Reader returned {response.status} for {url}')
                        return None
                    raw = await read_capped(response)
            text = raw.decode('utf-8', errors='replace').strip()
            if self.cfg.trim_length is not None:
                text = text[:self.cfg.trim_length]
            return text if len(text) >= 5 else None
        except Exception as e:
            logger.error(f'Jina Reader error for {url}: {e}')
            return None

    async def _open_direct(self, url: str) -> str | None:
        try:
            # with a proxy the target DNS is resolved by the proxy, so the
            # rebinding-safe resolver only applies to direct connections
            connector = (aiohttp.TCPConnector(resolver=_SafeResolver())
                         if not self.proxy else None)
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT,
                                             connector=connector) as session:
                # follow redirects manually so every hop is validated BEFORE it is fetched
                for _ in range(4):
                    reason = await self.check_url(url)
                    if reason is not None:
                        logger.warning(f'URL rejected ({reason}): {url}')
                        return None
                    async with session.get(url, allow_redirects=False,
                                           headers=BROWSER_HEADERS,
                                           proxy=self.proxy) as response:
                        if response.status in (301, 302, 303, 307, 308):
                            location = response.headers.get('Location')
                            if not location:
                                return None
                            url = str(response.url.join(aiohttp.client.URL(location)))
                            continue
                        if response.status >= 400:
                            logger.warning(f'URL returned {response.status}: {url}')
                            return None
                        raw = await read_capped(response)
                    return self._parse(raw)
            logger.warning(f'Too many redirects for URL: {url}')
            return None
        except Exception as e:
            logger.error(f'Error while opening URL {url}: {e}')
            return None

    def _parse(self, raw: bytes) -> str | None:
        '''Extract LLM-friendly text: trafilatura (main content as markdown)
        with a crude BeautifulSoup fallback.'''
        text = None
        try:
            import trafilatura
            text = trafilatura.extract(
                raw.decode('utf-8', errors='replace'),
                output_format='markdown', include_links=False, include_tables=True,
            )
        except Exception as e:
            logger.warning(f'trafilatura extraction failed: {e}')
        if not text:
            text = self._parse_bs4(raw)
        if not text:
            return None
        if self.cfg.trim_length is not None:
            text = text[:self.cfg.trim_length]
        return text if len(text) >= 5 else None

    def _parse_bs4(self, raw: bytes) -> str | None:
        try:
            soup = BeautifulSoup(raw, 'html.parser')
            body = soup.find('body')
            if body is None:
                return None
            return '\n'.join(
                tag.get_text().strip()
                for tag in body.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a',
                                          'li', 'ul', 'ol', 'blockquote'])
            ).replace('\n', ' ')
        except Exception as e:
            logger.error(f'Error while parsing URL content: {e}')
            return None


SEARCH_SCHEMA = {
    'type': 'function',
    'function': {
        'name': 'web_search',
        'description': 'Search the web using a search engine API',
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Query for web search'},
            },
            'required': ['query'],
        },
    },
}

URL_SCHEMA = {
    'type': 'function',
    'function': {
        'name': 'url_opener',
        'description': 'Open URL and get the content',
        'parameters': {
            'type': 'object',
            'properties': {
                'url': {'type': 'string', 'description': 'URL to open'},
            },
            'required': ['url'],
        },
    },
}


@registry.register(SEARCH_SCHEMA, requires='web_search')
async def web_search(ctx: ToolContext, query: str) -> ToolResult:
    results = await ctx.web_search.search(query)
    if results is None:
        return ToolResult(for_model='Error while searching the web')
    if not results:
        return ToolResult(for_model='No results found')
    lines = [f"{r['title']}\n{r['link']}\n{r['snippet']}" for r in results]
    return ToolResult(for_model=f'Web search results for "{query}":\n\n' + '\n\n'.join(lines))


@registry.register(URL_SCHEMA, requires='url_opener')
async def url_opener(ctx: ToolContext, url: str) -> ToolResult:
    content = await ctx.url_opener.open_url(url)
    if content is None:
        return ToolResult(for_model='Error while opening the URL or there was no content')
    if ctx.url_summarize and ctx.summary is not None:
        summarized = await ctx.summary(
            f'User message: {ctx.user_message}. Text from URL: {content}'
        )
        if summarized:
            content = summarized
    return ToolResult(for_model=f'URL ({url}) opened. Content: {content}')
