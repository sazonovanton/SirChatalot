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

class GoogleEngine:
    def __init__(self):
        self.api_key = config.get("Search", "APIKey")
        self.cse_id = config.get("Search", "CSEID")
        self.base_url = "https://www.googleapis.com/customsearch/v1"
        logger.info("Google Engine Initialized")

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
            "q": query
        }
        try:
            logger.debug(f"Searching for: {query}")
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    data = await response.json()
                    data = await self.format_data(data)
                    return data
        except Exception as e:
            logger.error(f"Error while searching: {e}")
            return None
        
if __name__ == "__main__":
    engine = GoogleEngine()
    loop = asyncio.get_event_loop()
    data = loop.run_until_complete(engine.search("Cats and Dogs"))
    print(json.dumps(data, indent=2))
    print(f'Length: {len(data)}')