"""
Главный роутер трекера.
Подключает страницы и API-эндпоинты из подмодулей.
"""

from fastapi import APIRouter

from src.tracker.routers.pages import router as pages_router
from src.tracker.routers.api import router as api_router
from src.tracker.routers.admin import router as admin_router
from src.tracker.routers.webhook import router as webhook_router

router = APIRouter(prefix="", tags=["tracker"])
router.include_router(pages_router)
router.include_router(api_router)
router.include_router(admin_router)
router.include_router(webhook_router)
