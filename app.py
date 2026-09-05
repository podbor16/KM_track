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
from fastapi.responses import JSONResponse, HTMLResponse
import json
import logging
import os
import time as _time
from pathlib import Path

from src.config import settings
from src.config.event_loader import get_maintenance_enabled, get_duathlon222_maintenance_enabled
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

def _build_full_payload(result) -> str:
    """Полный снапшот результатов события (без диффа — диф каждое SSE-подключение
    считает само, относительно своего последнего отправленного состояния;
    см. sse_tracker() в api.py). Общий на всех прев-стейт в проде приводил к
    тому, что поздно подключившийся клиент навсегда терял изменение, если оно
    уже попало в "базу сравнения" лидера до его подключения."""
    return json.dumps({
        'server_time_unix': result.server_time_unix,
        'race_gun_unix_ms': result.race_gun_unix_ms,
        'total_distance_km': result.total_distance_km,
        'total_results': result.total_results,
        'results': result.results,
    }, default=str)


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
    
    # Инициализируем пул БД соединений (pool_size=2: 2 workers × 2 = 4 < max_connections=20)
    pool = initialize_connection_pool(pool_size=2)
    settings.logger.info(f"📍 Swagger UI: http://localhost:8000/docs")
    settings.logger.info(f"📍 ReDoc: http://localhost:8000/redoc")
    settings.logger.info(f"📍 Трекер: http://localhost:8000/tracker")

    # Прогрев кеша: загрузка результатов активных мероприятий в фоне
    import asyncio
    async def _prewarm_cache():
        try:
            from src.analytics.db_connection_optimized import get_pooled_connection
            from src.krasmarafon.services.results_service import build_event_results
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

    # === REDIS ===
    import redis.asyncio as aioredis
    from src.krasmarafon.services.notification_hub import tracker_hub, notification_hub
    from src.krasmarafon.services.results_service import build_event_results
    from src.config.event_loader import load_events_cached, get_active_event as _get_active
    from src.analytics.db_connection_optimized import get_pooled_connection

    worker_id = str(os.getpid())
    redis_client = aioredis.Redis(host="127.0.0.1", port=6379, db=0, decode_responses=False)
    try:
        await redis_client.ping()
        settings.logger.info(f"[Redis] Connected, worker_id={worker_id}")
    except Exception as _redis_err:
        if settings.DEBUG:
            settings.logger.warning(f"[Redis] Not available (DEBUG mode) — SSE disabled: {_redis_err}")
            redis_client = None
        else:
            raise

    # === SSE BACKGROUND TASKS ===

    async def _tracker_broadcast():
        """Лидер-воркер: строит позиции каждые 2 сек, публикует в Redis."""
        is_leader = False
        while True:
            try:
                if not is_leader:
                    is_leader = bool(
                        await redis_client.set("tracker:leader", worker_id, nx=True, ex=6)
                    )
                    if is_leader:
                        settings.logger.info(f"[SSE] Leader acquired: pid={worker_id}")
                else:
                    current = await redis_client.get("tracker:leader")
                    is_leader = bool(current and current.decode() == worker_id)
                    if is_leader:
                        await redis_client.expire("tracker:leader", 6)

                if is_leader:
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
                                payload = _build_full_payload(result)
                                await redis_client.publish(
                                    f"tracker:event:{dist.db_event_id}",
                                    payload
                                )
            except Exception as _e:
                settings.logger.warning(f"[SSE] tracker_broadcast error: {_e}")
            await asyncio.sleep(2)

    async def _redis_tracker_subscriber():
        """Все воркеры: получают данные из Redis, рассылают локальным SSE-клиентам."""
        while True:
            try:
                pubsub = redis_client.pubsub()
                await pubsub.psubscribe("tracker:event:*")
                async for message in pubsub.listen():
                    if message["type"] == "pmessage":
                        channel = message["channel"].decode()
                        event_id = int(channel.split(":")[-1])
                        await tracker_hub.broadcast(event_id, message["data"].decode())
            except Exception as _e:
                settings.logger.warning(f"[Redis] tracker subscriber error, reconnecting: {_e}")
                await asyncio.sleep(1)

    async def _results_watcher():
        """Лидер-воркер: следит за новыми финишами, публикует уведомление в Redis."""
        last: dict[int, int] = {}
        while True:
            try:
                current = await redis_client.get("tracker:leader")
                if current and current.decode() == worker_id:
                    conn = get_pooled_connection()
                    if conn:
                        cur = conn.cursor(dictionary=True)
                        cur.execute(
                            "SELECT event_id, COUNT(*) AS cnt FROM results GROUP BY event_id"
                        )
                        for row in cur.fetchall():
                            eid, cnt = row["event_id"], row["cnt"]
                            if eid in last and last[eid] != cnt:
                                await redis_client.publish(
                                    "tracker:notification",
                                    json.dumps({"type": "results_updated", "event_id": eid})
                                )
                            last[eid] = cnt
                        cur.close()
                        conn.close()
            except Exception as _e:
                settings.logger.warning(f"[SSE] results_watcher error: {_e}")
            await asyncio.sleep(5)

    async def _startlist_watcher():
        """Лидер-воркер: следит за новыми регистрациями, публикует уведомление в Redis."""
        last: dict[int, int] = {}
        while True:
            try:
                current = await redis_client.get("tracker:leader")
                if current and current.decode() == worker_id:
                    conn = get_pooled_connection()
                    if conn:
                        cur = conn.cursor(dictionary=True)
                        cur.execute(
                            "SELECT event_id, COUNT(*) AS cnt FROM leads GROUP BY event_id"
                        )
                        for row in cur.fetchall():
                            eid, cnt = row["event_id"], row["cnt"]
                            if eid in last and last[eid] != cnt:
                                await redis_client.publish(
                                    "tracker:notification",
                                    json.dumps({"type": "startlist_updated"})
                                )
                            last[eid] = cnt
                        cur.close()
                        conn.close()
            except Exception as _e:
                settings.logger.warning(f"[SSE] startlist_watcher error: {_e}")
            await asyncio.sleep(15)

    async def _siberman_copernico_run_poller():
        """Лидер-воркер: опрашивает Copernico для бегового этапа Siberman.
        Задача крутится всегда — реальный fetch+apply происходит только
        для года(ов) с race_config.copernico_run_enabled=1. Кнопки
        "Включить"/"Выключить" в админке (POST .../copernico-run-toggle)
        полностью управляют этим циклом — отдельного запуска процесса не
        требуется (2026-08-06: раньше поллер был отдельным CLI-скриптом,
        запускаемым вручную по SSH — copernico_run_poller.py оставлен как
        fallback для локальной отладки без Redis)."""
        from src.siberman.db import get_siberman_connection
        from src.siberman.copernico_run import apply_copernico_snapshot, fetch_run_snapshot, load_preset_config
        preset_path = BASE_DIR / "config" / "copernico" / "siberman2026.yaml"
        cfg = load_preset_config(str(preset_path))

        def _run_cycle_sync() -> None:
            conn = get_siberman_connection()
            if conn is None:
                return
            try:
                cur = conn.cursor()
                cur.execute("SELECT race_year FROM race_config WHERE copernico_run_enabled=1")
                years = [row[0] for row in cur.fetchall()]
                if not years:
                    return
                runners = fetch_run_snapshot(cfg)
                if not runners:
                    return
                for year in years:
                    apply_copernico_snapshot(conn, year, runners, cfg)
            finally:
                conn.close()

        # Временная диагностика (2026-08-08, задача "путь данных от
        # Copernico до лайв результатов иногда занимает 3-4 минуты" —
        # найдено пользователем на живой гонке): логируем РЕАЛЬНЫЙ разрыв
        # между итерациями цикла (ожидается ~20с) и время выполнения самого
        # цикла — если разрыв заметно больше 20с, значит планирование этой
        # asyncio-задачи где-то стопорится (например, лидер-воркер занят
        # синхронным блокирующим кодом в event loop от HTTP-запроса), а не
        # сам Copernico/БД (apply_copernico_snapshot сам по себе <2с,
        # проверено вручную). Не убирать до подтверждения причины.
        last_tick = asyncio.get_event_loop().time()
        while True:
            now = asyncio.get_event_loop().time()
            gap = now - last_tick
            last_tick = now
            if gap > 25:
                settings.logger.warning(f"[siberman] copernico_run_poller: разрыв между циклами {gap:.1f}с (ожидалось ~20с)")
            try:
                current = await redis_client.get("tracker:leader")
                if current and current.decode() == worker_id:
                    t0 = asyncio.get_event_loop().time()
                    await asyncio.get_event_loop().run_in_executor(None, _run_cycle_sync)
                    dt = asyncio.get_event_loop().time() - t0
                    if dt > 3:
                        settings.logger.warning(f"[siberman] copernico_run_poller: цикл выполнялся {dt:.1f}с")
            except Exception as _e:
                settings.logger.warning(f"[siberman] copernico_run_poller error: {_e}")
            await asyncio.sleep(20)

    async def _siberman_google_sheet_poller():
        """Лидер-воркер: синхронизирует Siberman с Google Таблицей для
        года(ов) с race_config.google_sheet_sync_enabled=1 — см.
        google_sheet_sync.py. Управляется кнопками "Включить"/"Выключить"
        в админке, без отдельного запуска процесса (google_sheet_poller.py
        оставлен как CLI-fallback для локальной отладки без Redis)."""
        from src.siberman.db import get_siberman_connection
        from src.siberman.google_sheet_sync import sync_google_sheet

        def _run_cycle_sync() -> None:
            conn = get_siberman_connection()
            if conn is None:
                return
            try:
                cur = conn.cursor()
                cur.execute("SELECT race_year FROM race_config WHERE google_sheet_sync_enabled=1")
                years = [row[0] for row in cur.fetchall()]
                for year in years:
                    sync_google_sheet(conn, year)
            finally:
                conn.close()

        while True:
            try:
                current = await redis_client.get("tracker:leader")
                if current and current.decode() == worker_id:
                    await asyncio.get_event_loop().run_in_executor(None, _run_cycle_sync)
            except Exception as _e:
                settings.logger.warning(f"[siberman] google_sheet_poller error: {_e}")
            await asyncio.sleep(20)

    async def _redis_notification_subscriber():
        """Все воркеры: получают уведомления из Redis, рассылают через NotificationHub."""
        while True:
            try:
                pubsub = redis_client.pubsub()
                await pubsub.subscribe("tracker:notification")
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        payload = json.loads(message["data"].decode())
                        await notification_hub.broadcast(
                            payload["type"], payload.get("payload")
                        )
            except Exception as _e:
                settings.logger.warning(f"[Redis] notification subscriber error, reconnecting: {_e}")
                await asyncio.sleep(1)

    async def _metrics_flusher():
        """Каждые 60с снимает bucket метрик и пишет в SQLite."""
        while True:
            await asyncio.sleep(60)
            sse_count = tracker_hub.total_sse_count() + notification_hub.total_sse_count()
            await metrics_collector.flush(sse_connections=sse_count)

    _sse_tasks = [asyncio.create_task(_metrics_flusher())]
    if redis_client is not None:
        _sse_tasks += [
            asyncio.create_task(_tracker_broadcast()),
            asyncio.create_task(_redis_tracker_subscriber()),
            asyncio.create_task(_results_watcher()),
            asyncio.create_task(_startlist_watcher()),
            asyncio.create_task(_redis_notification_subscriber()),
            asyncio.create_task(_siberman_copernico_run_poller()),
            asyncio.create_task(_siberman_google_sheet_poller()),
        ]
        settings.logger.info(
            "[SSE] Background tasks started: tracker_broadcast, redis_tracker_subscriber, "
            "results_watcher, startlist_watcher, redis_notification_subscriber, metrics_flusher, "
            "siberman_copernico_run_poller, siberman_google_sheet_poller"
        )
    else:
        settings.logger.warning("[SSE] Redis unavailable — SSE tasks skipped (DEBUG mode)")

    yield  # Приложение работает здесь

    # === SHUTDOWN ===
    for _t in _sse_tasks:
        _t.cancel()
    if redis_client is not None:
        await redis_client.aclose()
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

# --- ТЕХНИЧЕСКИЕ РАБОТЫ ---
# Заглушка на все публичные URL, кроме админки/авторизации/статики —
# переключается мгновенно (без деплоя) через /admin, см.
# get_maintenance_enabled()/set_maintenance_enabled() в event_loader.py
# и POST /api/admin/maintenance-toggle в src/krasmarafon/routers/admin.py.
_MAINTENANCE_ALLOWED_PREFIXES = (
    "/admin",
    "/24h/admin",
    "/login",
    "/logout",
    "/api/admin",
    "/api/tri/admin",
    "/api/siberman/admin",
    "/static",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
)
_MAINTENANCE_ICON_SVG = (
    '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round">'
    '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 '
    '7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>'
)
_MAINTENANCE_TITLE = "Ведутся технические работы"
_MAINTENANCE_TEXT = (
    "В системе электронного хронометража ведутся технические работы.<br>"
    "Данные временно не доступны, следите за обновлением."
)

_MAINTENANCE_PAGES = {
    "krasmarafon": f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Технические работы — Красмарафон</title>
<link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: Arial, sans-serif; background: #1a1a1a; min-height: 100vh; display: flex; flex-direction: column; }}
.topbar {{ background: #222; border-bottom: 3px solid #e84c8c; padding: 12px 24px; display: flex; align-items: center; }}
.topbar img {{ height: 26px; width: auto; display: block; }}
.wrap {{ flex: 1; display: flex; align-items: center; justify-content: center; padding: 40px 16px; }}
.card {{ background: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 8px; padding: 44px 36px; max-width: 440px; width: 100%; text-align: center; }}
.icon {{ width: 46px; height: 46px; margin: 0 auto 20px; color: #e84c8c; }}
h1 {{ color: #fff; font-size: 20px; font-weight: 700; margin-bottom: 12px; letter-spacing: .3px; }}
p {{ color: #ccc; font-size: 15px; line-height: 1.55; }}
</style></head><body>
<div class="topbar"><img src="/static/images/krasmarafon/logo-mark.png" alt="Красмарафон"></div>
<div class="wrap"><div class="card">{_MAINTENANCE_ICON_SVG}<h1>{_MAINTENANCE_TITLE}</h1><p>{_MAINTENANCE_TEXT}</p></div></div>
</body></html>""",
    "siberman": f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Технические работы — Siberman</title>
<link rel="icon" href="/static/images/siberman/favicon.ico" sizes="any">
<style>
:root {{ --red: #BE0A21; --blue: #6AABD7; --bg: #071622; --bg2: #0c2035; --border: rgba(106,171,215,.18); --text: #e4eef6; --muted: #7aaabf; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px; }}
.logo-name {{ font-size: 26px; font-weight: 800; letter-spacing: 1px; text-align: center; margin-bottom: 28px; }}
.logo-name .m {{ color: var(--red); }}
.card {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 10px; padding: 40px 32px; max-width: 400px; width: 100%; text-align: center; }}
.icon {{ width: 44px; height: 44px; margin: 0 auto 18px; color: var(--blue); }}
h1 {{ font-size: 18px; font-weight: 700; margin-bottom: 10px; }}
p {{ color: var(--muted); font-size: 14px; line-height: 1.55; }}
</style></head><body>
<div><div class="logo-name">SIBER<span class="m">M</span>AN</div>
<div class="card">{_MAINTENANCE_ICON_SVG}<h1>{_MAINTENANCE_TITLE}</h1><p>{_MAINTENANCE_TEXT}</p></div></div>
</body></html>""",
    "triatleta": f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Технические работы — Triatleta 24h</title>
<style>
:root {{ --bg: #f5f5f5; --surface: #fff; --border: #e8e8e8; --accent: #FF8562; --text: #050505; --muted: #888; --header-bg: linear-gradient(135deg, #050505 0%, #263146 100%); }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, sans-serif; background: var(--bg); min-height: 100vh; display: flex; flex-direction: column; }}
.topbar {{ background: var(--header-bg); border-bottom: 3px solid var(--accent); padding: 16px 24px; color: #fff; font-weight: 800; letter-spacing: 1px; }}
.wrap {{ flex: 1; display: flex; align-items: center; justify-content: center; padding: 40px 16px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 40px 32px; max-width: 420px; width: 100%; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
.icon {{ width: 44px; height: 44px; margin: 0 auto 18px; color: var(--accent); }}
h1 {{ color: var(--text); font-size: 18px; font-weight: 700; margin-bottom: 10px; }}
p {{ color: var(--muted); font-size: 14px; line-height: 1.55; }}
</style></head><body>
<div class="topbar">TRIATLETA 24H</div>
<div class="wrap"><div class="card">{_MAINTENANCE_ICON_SVG}<h1>{_MAINTENANCE_TITLE}</h1><p>{_MAINTENANCE_TEXT}</p></div></div>
</body></html>""",
}


def _maintenance_domain(request: Request) -> str:
    host = request.headers.get("host", "").lower().split(":")[0]
    if "triatleta" in host:
        return "triatleta"
    if "siberman" in host:
        return "siberman"
    return "krasmarafon"


@app.middleware("http")
async def maintenance_mode_middleware(request: Request, call_next):
    if get_maintenance_enabled() and not request.url.path.startswith(_MAINTENANCE_ALLOWED_PREFIXES):
        domain = _maintenance_domain(request)
        return HTMLResponse(
            _MAINTENANCE_PAGES[domain],
            status_code=503,
            headers={"Retry-After": "3600"},
        )
    return await call_next(request)


# --- ТЕХНИЧЕСКИЕ РАБОТЫ — ТОЛЬКО ДУАТЛОН 222 ---
# Независимый флаг от maintenance_mode_middleware выше — Дуатлон 222 делит
# домен live-race.triatleta.ru с суточной гонкой (та же "triatleta" ветка
# _maintenance_domain), поэтому общий флаг задел бы обе гонки разом.
# Переключается из /duathlon222/admin, см.
# get_duathlon222_maintenance_enabled()/set_duathlon222_maintenance_enabled()
# в event_loader.py и POST /api/duathlon222/admin/maintenance-toggle.
_DUATHLON222_PATH_PREFIXES = ("/duathlon222", "/api/duathlon222")
_DUATHLON222_MAINTENANCE_ALLOWED_PREFIXES = (
    "/duathlon222/admin",
    "/duathlon222/login",
    "/duathlon222/logout",
    "/api/duathlon222/admin",
)
_DUATHLON222_MAINTENANCE_PAGE = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Технические работы — 222 Дуатлон</title>
<style>
:root {{ --bg: #f5f5f5; --surface: #fff; --border: #e8e8e8; --accent: #FF8562; --text: #050505; --muted: #888; --header-bg: linear-gradient(135deg, #050505 0%, #263146 100%); }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, sans-serif; background: var(--bg); min-height: 100vh; display: flex; flex-direction: column; }}
.topbar {{ background: var(--header-bg); border-bottom: 3px solid var(--accent); padding: 16px 24px; color: #fff; font-weight: 800; letter-spacing: 1px; }}
.wrap {{ flex: 1; display: flex; align-items: center; justify-content: center; padding: 40px 16px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 40px 32px; max-width: 420px; width: 100%; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
.icon {{ width: 44px; height: 44px; margin: 0 auto 18px; color: var(--accent); }}
h1 {{ color: var(--text); font-size: 18px; font-weight: 700; margin-bottom: 10px; }}
p {{ color: var(--muted); font-size: 14px; line-height: 1.55; }}
</style></head><body>
<div class="topbar">222 ДУАТЛОН</div>
<div class="wrap"><div class="card">{_MAINTENANCE_ICON_SVG}<h1>{_MAINTENANCE_TITLE}</h1><p>{_MAINTENANCE_TEXT}</p></div></div>
</body></html>"""


@app.middleware("http")
async def duathlon222_maintenance_middleware(request: Request, call_next):
    path = request.url.path
    if (
        path.startswith(_DUATHLON222_PATH_PREFIXES)
        and not path.startswith(_DUATHLON222_MAINTENANCE_ALLOWED_PREFIXES)
        and get_duathlon222_maintenance_enabled()
    ):
        return HTMLResponse(
            _DUATHLON222_MAINTENANCE_PAGE,
            status_code=503,
            headers={"Retry-After": "3600"},
        )
    return await call_next(request)

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

@app.middleware("http")
async def domain_middleware(request: Request, call_next):
    host = request.headers.get("host", "").lower().split(":")[0]
    if "triatleta" in host:
        request.state.domain = "triatleta"
    elif "siberman" in host:
        request.state.domain = "siberman"
    else:
        request.state.domain = "krasmarafon"
    return await call_next(request)

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

from src.krasmarafon.router import router as tracker_router

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
