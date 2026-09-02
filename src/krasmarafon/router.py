"""
Главный роутер трекера.
Подключает страницы и API-эндпоинты из подмодулей.
"""

from fastapi import APIRouter

from src.krasmarafon.routers.pages import router as pages_router
from src.krasmarafon.routers.api import router as api_router
from src.krasmarafon.routers.admin import router as admin_router
from src.krasmarafon.routers.webhook import router as webhook_router

router = APIRouter(prefix="", tags=["tracker"])
router.include_router(pages_router)
router.include_router(api_router)
router.include_router(admin_router)
router.include_router(webhook_router)

from src.race_triatleta.router import router as triatleta_router
router.include_router(triatleta_router)

from src.duathlon222.router import router as duathlon222_router
router.include_router(duathlon222_router)

from src.siberman.router import router as siberman_router
router.include_router(siberman_router)
