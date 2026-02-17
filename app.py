"""
FastAPI приложение KM_track
Трекер маршрутов и аналитика спортивных мероприятий

Точка входа: uvicorn app:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from pathlib import Path

from src.config import settings
from src.core.dependencies import init_app_state
from src.core.exceptions import KMTrackException

# Инициализация приложения
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager для инициализации и cleanup приложения"""
    
    # === STARTUP ===
    settings.logger.info("=" * 50)
    settings.logger.info(f"🚀 {settings.API_TITLE} v{settings.API_VERSION}")
    settings.logger.info("=" * 50)
    
    # Инициализирование глобального состояния
    app_state = init_app_state()
    settings.logger.info(f"✓ Application state initialized: {app_state}")
    settings.logger.info("✓ CORS enabled for: " + ", ".join(settings.CORS_ORIGINS))
    settings.logger.info("✓ Static files mounted")
    settings.logger.info("✓ Templates configured")
    settings.logger.info("\nReady to process requests!")
    settings.logger.info(f"📍 Swagger UI: http://localhost:8000/docs")
    settings.logger.info(f"📍 ReDoc: http://localhost:8000/redoc")
    settings.logger.info("=" * 50)
    
    yield  # Приложение работает здесь
    
    # === SHUTDOWN ===
    settings.logger.info("Shutting down...")


app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,  # Использует context manager
)

# Настройка логирования
logging.getLogger("fastapi").setLevel(logging.INFO)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Пути
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
LEGACY_STATIC_DIR = BASE_DIR / "legacy" / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
LEGACY_TEMPLATES_DIR = BASE_DIR / "legacy" / "templates"

# Подключение статических файлов
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    settings.logger.info(f"Static files mounted: {STATIC_DIR}")

# Подключение legacy статических файлов
if LEGACY_STATIC_DIR.exists():
    app.mount("/legacy/static", StaticFiles(directory=str(LEGACY_STATIC_DIR)), name="legacy_static")
    settings.logger.info(f"Legacy static files mounted: {LEGACY_STATIC_DIR}")

# Подключение шаблонов (текущих и legacy)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
settings.logger.info(f"Templates directory: {TEMPLATES_DIR}")

# Подключение legacy шаблонов
legacy_templates = Jinja2Templates(directory=str(LEGACY_TEMPLATES_DIR))
settings.logger.info(f"Legacy templates directory: {LEGACY_TEMPLATES_DIR}")


# --- ОБРАБОТЧИКИ ИСКЛЮЧЕНИЙ ---

@app.exception_handler(KMTrackException)
async def km_track_exception_handler(request, exc: KMTrackException):
    """Обработчик кастомных исключений приложения"""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error": exc.__class__.__name__},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Обработчик HTTP исключений"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Обработчик общих исключений"""
    settings.logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )



# --- HEALTH CHECK ---

@app.get("/health", tags=["System"])
async def health_check():
    """Проверка здоровья приложения"""
    return {
        "status": "ok",
        "service": settings.API_TITLE,
        "version": settings.API_VERSION,
    }


@app.get("/", tags=["Info"])
async def root():
    """Информация о приложении"""
    return {
        "title": settings.API_TITLE,
        "description": settings.API_DESCRIPTION,
        "version": settings.API_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


# --- РЕГИСТРАЦИЯ РОУТЕРОВ ---

from src.tracker.router import router as tracker_router

app.include_router(tracker_router, tags=["tracker"])

# TODO: Подключить src/analytics/router.py когда он будет создан
# from src.analytics.router import router as analytics_router
# app.include_router(analytics_router, prefix="/api", tags=["analytics"])


# --- ГЛАВНАЯ ТОЧКА ВХОДА ---

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
