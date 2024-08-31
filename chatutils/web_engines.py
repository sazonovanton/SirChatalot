# Description: Web search engines 

from chatutils.misc import setup_logging, read_config
config = read_config('./data/.config')
logger = setup_logging(logger_name='SirChatalot-WebEngines', log_level=config.get('Logging', 'LogLevel', fallback='WARNING'))

import asyncio
import aiohttp
from bs4 import BeautifulSoup

class GoogleEngine:
    '''
    Google Search Engine
    '''
    def __init__(self):
        self.api_key = config.get("Web", "APIKey")
        self.cse_id = config.get("Web", "CSEID")
        self.search_results  = config.getint("Web", "SearchResults", fallback=5)
        self.search_results = min(self.search_results, 10)
        self.search_results = max(self.search_results, 1)
        self.base_url = "https://www.googleapis.com/customsearch/v1"
        logger.info('Google Engine Initialized')

    async def format_data(self, data):
        results = []
        for item in data["items"]:
            result = {
                "title": item["title"],
                "link": item["link"],
                "snippet": item["snippet"]
            }
            results.append(result)
        return results

    async def search(self, query):
        params = {
            "key": self.api_key,
            "cx": self.cse_id,
            "q": query,
            "num": self.search_results
        }
        try:
            logger.debug(f'Searching for: "{query}". Results number: {self.search_results}')
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    data = await response.json()
                    data = await self.format_data(data)
                    return data
        except Exception as e:
            logger.error(f'Error while searching: {e}')
            return None

class URLOpen:
    '''
    URL Open
    Gets the content of a URL, parses it and returns the text
    Deletes unnecessary tags and returns the text in the body
    '''
    def __init__(self):
        self.trim_len = config.getint("Web", "TrimLength", fallback=None)
        logger.info(f'URL Open Initialized, trim length: {self.trim_len}')

    async def parse_data(self, data):
        try:
            soup = BeautifulSoup(data, 'html.parser')
            body = soup.find('body')
            text = ''
            for tag in body.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a', 'li', 'ul', 'ol', 'blockquote']):
                text += tag.get_text().strip() + '\n'
            text = text.replace('\n', ' ')
            if self.trim_len is not None:
                text = text[:self.trim_len]
            if len(text) < 5:
                text = None
            return text
        except Exception as e:
            logger.error(f'Error while parsing data: {e}')
            return None

    async def open_url(self, url):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.text()
                    data = await self.parse_data(data)
                    return data
        except Exception as e:
            logger.error(f'Error while opening URL: {e}')
            return None
        
if __name__ == "__main__":
    urlopener = URLOpen()
    url = 'https://www.wikipedia.org/'
    data = asyncio.run(urlopener.open_url(url))
    print(data)