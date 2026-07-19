'''Service container shared by all handlers via application.bot_data.'''

from dataclasses import dataclass

from sirchatalot.chat_manager import ChatManager
from sirchatalot.config import AppConfig
from sirchatalot.db import Database
from sirchatalot.model_registry import ModelRegistry


@dataclass
class Services:
    cfg: AppConfig
    db: Database
    registry: ModelRegistry
    chat: ChatManager
    files_proc: object | None = None   # files.extract.FilesProcessor
    files_rag: object | None = None    # files.rag.FilesRAG


def get_services(context) -> Services:
    return context.application.bot_data['services']
