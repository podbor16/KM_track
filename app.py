"""
FastAPI приложение KM_track
Трекер маршрутов и аналитика спортивных мероприятий

Точка входа: uvicorn app:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import logging
import time as _time
from pathlib import Path

from src.config import settings
from src.core.dependencies import init_app_state
from src.core.exceptions import KMTrackException
from src.analytics.db_connection_optimized import initialize_connection_pool
from src.monitoring.collector import MetricsCollector

# Пути (нужны до lifespan)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
metrics_collector = MetricsCollector(db_path=str(DATA_DIR / "server_metrics.db"))


# Инициализация приложения
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager для инициализации и cleanup приложения"""
    
    # === STARTUP ===
    settings.logger.info("=" * 50)
    settings.logger.info(f"Запуск {settings.API_TITLE} v{settings.API_VERSION}")
    settings.logger.info("=" * 50)

    # Загрузка конфигураций мероприятий из YAML
    from src.config.event_loader import load_all_events, get_active_event
    settings.EVENTS = load_all_events(BASE_DIR / "config" / "events")
    settings.logger.info(
        f"Загружено мероприятий: {len(settings.EVENTS)} — {list(settings.EVENTS)}"
    )
    active = get_active_event(settings.EVENTS)
    if active:
        settings.CURRENT_EVENT = active.code
        settings.logger.info(f"Активное мероприятие: {active.code} ({active.display_name})")
    else:
        settings.logger.warning("Активное мероприятие не задано в конфигах (is_active: true)")

    # Инициализирование глобального состояния
    app_state = init_app_state()
    settings.logger.info(f"AppState инициализирован: {app_state}")
    
    # Инициализируем пул БД соединений
    pool = initialize_connection_pool(pool_size=5)
    settings.logger.info(f"📍 Swagger UI: http://localhost:8000/docs")
    settings.logger.info(f"📍 ReDoc: http://localhost:8000/redoc")
    settings.logger.info(f"📍 Трекер: http://localhost:8000/tracker")

    # Прогрев кеша: загрузка результатов активных мероприятий в фоне
    import asyncio
    async def _prewarm_cache():
        try:
            from src.analytics.db_connection_optimized import get_pooled_connection
            from src.tracker.services.results_service import build_event_results
            # Загружаем все event_id которые реально есть в БД
            conn = get_pooled_connection()
            if not conn:
                return
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT DISTINCT event_id FROM results ORDER BY event_id")
            event_ids = [row['event_id'] for row in cur.fetchall()]
            cur.close()
            conn.close()
            for eid in event_ids:
                await asyncio.get_event_loop().run_in_executor(
                    None, build_event_results, eid, None, None, settings.EVENTS
                )
                settings.logger.info(f"Cache pre-warmed: event_id={eid}")
        except Exception as _e:
            settings.logger.warning(f"Cache pre-warm failed: {_e}")
    asyncio.create_task(_prewarm_cache())

    # === SSE BACKGROUND TASKS ===
    from src.tracker.services.notification_hub import tracker_hub, notification_hub
    from src.tracker.services.results_service import build_event_results
    from src.config.event_loader import load_events_cached, get_active_event as _get_active

    async def _tracker_broadcast():
        """Строит позиции участников каждые 2 сек и рассылает через TrackerHub."""
        while True:
            try:
                events = load_events_cached()
                active = _get_active(events)
                if active:
                    for dist in active.distances:
                        if not dist.tracked:
                            continue
                        result = await asyncio.get_event_loop().run_in_executor(
                            None, build_event_results,
                            dist.db_event_id, None, None, events
                        )
                        if result:
                            await tracker_hub.broadcast(
                                dist.db_event_id, result.model_dump_json()
                            )
            except Exception as _e:
                settings.logger.warning(f"[SSE] tracker_broadcast error: {_e}")
            await asyncio.sleep(2)

    async def _results_watcher():
        """Следит за новыми финишами; уведомляет results_updated."""
        from src.analytics.db_connection_optimized import get_pooled_connection
        last: dict[int, int] = {}
        while True:
            try:
                conn = get_pooled_connection()
                if conn:
                    cur = conn.cursor(dictionary=True)
                    cur.execute(
                        "SELECT event_id, COUNT(*) AS cnt FROM results GROUP BY event_id"
                    )
                    for row in cur.fetchall():
                        eid, cnt = row["event_id"], row["cnt"]
                        if eid in last and last[eid] != cnt:
                            await notification_hub.broadcast(
                                "results_updated", {"event_id": eid}
                            )
                        last[eid] = cnt
                    cur.close()
                    conn.close()
            except Exception as _e:
                settings.logger.warning(f"[SSE] results_watcher error: {_e}")
            await asyncio.sleep(5)

    async def _startlist_watcher():
        """Следит за новыми регистрациями в leads; уведомляет startlist_updated."""
        from src.analytics.db_connection_optimized import get_pooled_connection
        last: dict[int, int] = {}
        while True:
            try:
                conn = get_pooled_connection()
                if conn:
                    cur = conn.cursor(dictionary=True)
                    cur.execute(
                        "SELECT event_id, COUNT(*) AS cnt FROM leads GROUP BY event_id"
                    )
                    for row in cur.fetchall():
                        eid, cnt = row["event_id"], row["cnt"]
                        if eid in last and last[eid] != cnt:
                            await notification_hub.broadcast("startlist_updated")
                        last[eid] = cnt
                    cur.close()
                    conn.close()
            except Exception as _e:
                settings.logger.warning(f"[SSE] startlist_watcher error: {_e}")
            await asyncio.sleep(15)

    async def _metrics_flusher():
        """Каждые 60с снимает bucket метрик и пишет в SQLite."""
        while True:
            await asyncio.sleep(60)
            sse_count = tracker_hub.total_sse_count()
            await metrics_collector.flush(sse_connections=sse_count)

    _sse_tasks = [
        asyncio.create_task(_tracker_broadcast()),
        asyncio.create_task(_results_watcher()),
        asyncio.create_task(_startlist_watcher()),
        asyncio.create_task(_metrics_flusher()),
    ]
    settings.logger.info("[SSE] Background tasks started: tracker_broadcast, results_watcher, startlist_watcher, metrics_flusher")

    yield  # Приложение работает здесь

    # === SHUTDOWN ===
    for _t in _sse_tasks:
        _t.cancel()
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

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_perf_logger = logging.getLogger("km_track.perf")

@app.middleware("http")
async def log_request_duration(request: Request, call_next):
    # BaseHTTPMiddleware несовместим с SSE-стримингом — пропускаем без обработки
    if request.url.path.startswith("/api/sse") or request.url.path == "/api/admin/metrics/live":
        return await call_next(request)
    start = _time.time()
    response = await call_next(request)
    duration = _time.time() - start
    response.headers["X-Process-Time"] = f"{duration:.3f}"
    if duration > 0.5:
        _perf_logger.warning(f"SLOW {request.method} {request.url.path} {duration:.3f}s")
    else:
        _perf_logger.debug(f"{request.method} {request.url.path} {duration:.3f}s {response.status_code}")
    metrics_collector.record(
        ip=request.client.host if request.client else None,
        duration_ms=duration * 1000,
        status=response.status_code,
    )
    return response

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
