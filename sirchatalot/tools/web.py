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


class GoogleSearch:
    def __init__(self, cfg: WebSearchConfig):
        self.cfg = cfg
        self.base_url = 'https://www.googleapis.com/customsearch/v1'

    async def search(self, query: str) -> list[dict] | None:
        params = {'key': self.cfg.api_key, 'cx': self.cfg.cse_id,
                  'q': query, 'num': self.cfg.results}
        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.get(self.base_url, params=params) as response:
                    data = await response.json()
            return [{'title': item['title'], 'link': item['link'], 'snippet': item['snippet']}
                    for item in data.get('items', [])]
        except Exception as e:
            logger.error(f'Web search failed: {e}')
            return None


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
    def __init__(self, cfg: UrlOpenConfig):
        self.cfg = cfg

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
        try:
            connector = aiohttp.TCPConnector(resolver=_SafeResolver())
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT,
                                             connector=connector) as session:
                # follow redirects manually so every hop is validated BEFORE it is fetched
                for _ in range(4):
                    reason = await self.check_url(url)
                    if reason is not None:
                        logger.warning(f'URL rejected ({reason}): {url}')
                        return None
                    async with session.get(url, allow_redirects=False) as response:
                        if response.status in (301, 302, 303, 307, 308):
                            location = response.headers.get('Location')
                            if not location:
                                return None
                            url = str(response.url.join(aiohttp.client.URL(location)))
                            continue
                        raw = await response.content.read(MAX_RESPONSE_BYTES)
                    return self._parse(raw)
            logger.warning(f'Too many redirects for URL: {url}')
            return None
        except Exception as e:
            logger.error(f'Error while opening URL {url}: {e}')
            return None

    def _parse(self, raw: bytes) -> str | None:
        try:
            soup = BeautifulSoup(raw, 'html.parser')
            body = soup.find('body')
            if body is None:
                return None
            text = '\n'.join(
                tag.get_text().strip()
                for tag in body.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a',
                                          'li', 'ul', 'ol', 'blockquote'])
            ).replace('\n', ' ')
            if self.cfg.trim_length is not None:
                text = text[:self.cfg.trim_length]
            return text if len(text) >= 5 else None
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
