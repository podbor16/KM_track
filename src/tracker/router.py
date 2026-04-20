"""
Главный роутер трекера.
Подключает страницы и API-эндпоинты из подмодулей.
"""

from fastapi import APIRouter

from src.tracker.routers.pages import router as pages_router
from src.tracker.routers.api import router as api_router

router = APIRouter(prefix="", tags=["tracker"])
router.include_router(pages_router)
router.include_router(api_router)
