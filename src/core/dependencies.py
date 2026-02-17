"""
Dependency Injection функции для FastAPI
"""

from typing import Optional
from fastapi import Query

from src.core.state import AppState
from src.config import settings


# Глобальное состояние приложения
_app_state: Optional[AppState] = None


def init_app_state() -> AppState:
    """Инициализировать состояние приложения"""
    global _app_state
    if _app_state is None:
        _app_state = AppState()
    return _app_state


async def get_app_state() -> AppState:
    """Получить состояние приложения"""
    return init_app_state()


async def get_event(event: Optional[str] = Query(None)) -> str:
    """Получить ID события (параметр или дефолт)"""
    return event or settings.CURRENT_EVENT


__all__ = ["get_app_state", "get_event", "init_app_state"]
