# Description: Web search engines 

import configparser
config = configparser.ConfigParser()
config.read('./data/.config')
LogLevel = config.get("Logging", "LogLevel") if config.has_option("Logging", "LogLevel") else "WARNING"

# logging
import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-WebEngines")
LogLevel = getattr(logging, LogLevel.upper())
logger.setLevel(LogLevel)
handler = TimedRotatingFileHandler('./logs/sirchatalot.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7)
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

import os
import asyncio
import json
import time
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

class GoogleEngine:
    '''
    Google Search Engine
    '''
    def __init__(self):
        self.api_key = config.get("Web", "APIKey")
        self.cse_id = config.get("Web", "CSEID")
        self.search_results  = config.getint("Web", "SearchResults") if config.has_option("Web", "SearchResults") else 5
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
        self.trim_len = config.getint("Web", "TrimLength") if config.has_option("Web", "TrimLength") else None
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