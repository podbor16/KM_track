"""
FastAPI приложение KM_track
Трекер маршрутов и аналитика спортивных мероприятий

Точка входа: uvicorn app:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from pathlib import Path

from src.config import settings
from src.core.dependencies import init_app_state
from src.core.exceptions import KMTrackException
from src.analytics.db_connection_optimized import initialize_connection_pool

# Пути (нужны до lifespan)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


# Инициализация приложения
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager для инициализации и cleanup приложения"""
    
    # === STARTUP ===
    settings.logger.info("=" * 50)
    settings.logger.info(f"Запуск {settings.API_TITLE} v{settings.API_VERSION}")
    settings.logger.info("=" * 50)

    # Загрузка конфигураций мероприятий из YAML
    from src.config.event_loader import load_all_events
    settings.EVENTS = load_all_events(BASE_DIR / "config" / "events")
    settings.logger.info(
        f"Загружено мероприятий: {len(settings.EVENTS)} — {list(settings.EVENTS)}"
    )

    # Инициализирование глобального состояния
    app_state = init_app_state()
    settings.logger.info(f"AppState инициализирован: {app_state}")
    
    # Инициализируем пул БД соединений
    pool = initialize_connection_pool(pool_size=5)
    settings.logger.info(f"📍 Swagger UI: http://localhost:8000/docs")
    settings.logger.info(f"📍 ReDoc: http://localhost:8000/redoc")
    settings.logger.info(f"📍 Трекер: http://localhost:8000/tracker")
    
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
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Подключение статических файлов
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    settings.logger.info(f"Static files mounted: {STATIC_DIR}")

settings.logger.info(f"Templates directory: {TEMPLATES_DIR}")


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


# --- РЕГИСТРАЦИЯ РОУТЕРОВ ---

from src.tracker.router import router as tracker_router

app.include_router(tracker_router)


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
