"""
HTML-страницы приложения KM_track.
Все эндпоинты, возвращающие HTMLResponse (Jinja2 шаблоны).
"""

import hmac
import logging
from typing import Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.config.event_loader import get_event_by_name, get_event_by_db_id, get_history_enabled
from src.krasmarafon.services.diploma_service import get_diploma_data
from src.core.auth import (
    COOKIE_NAME,
    EXPIRY_SECONDS,
    create_session_cookie,
    require_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pages"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


def _get_deploy_version() -> str:
    """Git short hash текущего коммита — меняется с каждым деплоем."""
    import subprocess as _sp
    import time as _t
    try:
        r = _sp.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3, cwd=BASE_DIR,
        )
        v = r.stdout.strip()
        if v:
            return v
    except Exception:
        pass
    return str(int(_t.time()))


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["v"] = _get_deploy_version()
templates.env.globals["history_enabled"] = get_history_enabled


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def _build_event_config(
    event_id: Optional[int] = None,
    event_code: Optional[str] = None,
) -> dict:
    """Строит dict для window.EVENT_CONFIG в шаблоне tracker.html.

    Приоритет: event_id (из БД) > event_code (из YAML) > CURRENT_EVENT.
    Использует settings.EVENTS как единственный источник правды.
    """
    from src.analytics.db_connection_optimized import get_event_info_by_id, get_event_info

    # Резолвим event_id если не задан
    if not event_id:
        resolved_code = event_code or settings.CURRENT_EVENT
        event_cfg = settings.EVENTS.get(resolved_code)
        if event_cfg:
            # Сначала пробуем db_event_id из YAML
            tracked = event_cfg.get_tracked()
            if tracked and tracked.db_event_id:
                event_id = tracked.db_event_id
            else:
                # Резолвим через БД по имени события
                try:
                    fallback_info = get_event_info(event_cfg.name, datetime.now().year) or {}
                    event_id = fallback_info.get('id') or None
                except Exception:
                    pass

    ev_info: dict = {}
    if event_id:
        ev_info = get_event_info_by_id(event_id) or {}

    # Определяем code по event_name из БД, сопоставляя с YAML
    db_event_name = ev_info.get('event_name', '')
    resolved_code = event_code or settings.CURRENT_EVENT
    if db_event_name:
        match = get_event_by_name(settings.EVENTS, db_event_name)
        if match:
            resolved_code = match.code

    event_cfg = settings.EVENTS.get(resolved_code)

    return {
        'id': event_id or ev_info.get('id'),
        'code': resolved_code,
        'name': event_cfg.display_name if event_cfg else resolved_code,
        'year': ev_info.get('event_year') or datetime.now().year,
        'distance': str(ev_info.get('event_distance') or ''),
        'title': event_cfg.title if event_cfg else f"{resolved_code} | Трекер",
        'description': event_cfg.description if event_cfg else '',
        'coordinates': [56.0075, 92.7246],  # центр карты (Красноярск)
    }


async def _tracker_response(
    request: Request,
    event_id: Optional[int] = None,
    event_code: Optional[str] = None,
):
    """Рендер страницы трекера с динамическим event_config."""
    event_cfg = _build_event_config(event_id=event_id, event_code=event_code)
    return templates.TemplateResponse("krasmarafon/tracker.html", {
        "request": request,
        "event_title": event_cfg["title"],
        "event_config": event_cfg,
        "events": list(settings.EVENTS.keys()),
    })


# ============================================================================
# ТРЕКЕР
# ============================================================================

@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Главная страница — domain-aware. Выбирает страницу по домену."""
    domain = getattr(request.state, "domain", "krasmarafon")
    if domain == "triatleta":
        return templates.TemplateResponse("race_triatleta/index.html",
                                          {"request": request, "v": _get_deploy_version()})
    if domain == "siberman":
        return templates.TemplateResponse("siberman/results.html", {"request": request})
    return await _tracker_response(request)


@router.get("/tracker", response_class=HTMLResponse)
async def tracker_page(request: Request, event_id: Optional[int] = Query(None)):
    """Трекер. event_id опционален — если не задан, берётся CURRENT_EVENT."""
    return await _tracker_response(request, event_id=event_id)


@router.get("/tracker/{event:path}", response_class=HTMLResponse)
async def tracker_event_page(request: Request, event: str):
    """Трекер для конкретного события по коду (например /tracker/night_run)."""
    if event not in settings.EVENTS:
        logger.warning(f"Неизвестный код события: {event}, используется CURRENT_EVENT")
        event = settings.CURRENT_EVENT
    return await _tracker_response(request, event_code=event)


# ============================================================================
# СТАТИЧЕСКИЕ СТРАНИЦЫ
# ============================================================================

@router.get("/start_list", response_class=HTMLResponse)
async def start_list_page(request: Request):
    """Стартовый список участников."""
    return templates.TemplateResponse("krasmarafon/start_list.html", {
        "request": request,
        "event": settings.CURRENT_EVENT,
    })


@router.get("/analytics")
async def analytics_page():
    """Legacy URL — перенаправляем в админку."""
    return RedirectResponse("/admin", status_code=302)


def _diploma_event_ids() -> list[int]:
    """event_id всех дистанций, у которых включена печать диплома — общий
    список, нужен и /athlete-profile (история спортсмена), и /results
    (кнопка диплома прямо в результатах забега)."""
    return [
        d.db_event_id
        for event in settings.EVENTS.values()
        for d in event.distances
        if d.diploma is not None and d.db_event_id is not None
    ]


@router.get("/results", response_class=HTMLResponse)
async def results_page(request: Request):
    """Результаты забега."""
    return templates.TemplateResponse("krasmarafon/results.html", {
        "request": request,
        "event": settings.CURRENT_EVENT,
        "diploma_event_ids": _diploma_event_ids(),
    })


@router.get("/history")
async def history_page(request: Request):
    """История: поиск по спортсмену и по забегу. Временно скрыто, пока
    историческая база 2013-2023 не загружена — см. get_history_enabled()."""
    if not get_history_enabled():
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("krasmarafon/history.html", {"request": request})


@router.get("/athlete-profile")
async def athlete_profile_page(request: Request):
    """Профиль спортсмена со всеми его результатами. Временно скрыто, см. history_page()."""
    if not get_history_enabled():
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("krasmarafon/athlete-profile.html", {
        "request": request,
        "diploma_event_ids": _diploma_event_ids(),
    })


@router.get("/diploma/{event_id}/{bib}", response_class=HTMLResponse)
async def diploma_page(request: Request, event_id: int, bib: str):
    """Публичный диплом участника — фон+медаль от дизайнера (per-дистанция
    в конфиге события), поверх — ФИО/чистое время/места. Без авторизации
    и без общей шапки сайта — самостоятельная полноэкранная страница,
    можно переслать прямой ссылкой."""
    event_cfg, distance_cfg = get_event_by_db_id(settings.EVENTS, event_id)
    if event_cfg is None or distance_cfg is None or distance_cfg.diploma is None:
        raise HTTPException(status_code=404, detail="Диплом для этого события/дистанции недоступен")

    data = get_diploma_data(event_id, bib)
    if data is None:
        raise HTTPException(status_code=404, detail="Результат участника не найден")

    return templates.TemplateResponse("krasmarafon/diploma.html", {
        "request": request,
        "event": event_cfg,
        "distance": distance_cfg,
        "diploma": data,
    })


@router.get("/race-analysis", response_class=HTMLResponse)
async def race_analysis_page(request: Request):
    """Анализ забегов с выбором события и года."""
    return templates.TemplateResponse("krasmarafon/race-analysis.html", {"request": request})


# ============================================================================
# АВТОРИЗАЦИЯ
# ============================================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    domain = getattr(request.state, "domain", "krasmarafon")
    if domain == "siberman":
        return templates.TemplateResponse("siberman/login.html", {"request": request, "error": None})
    return templates.TemplateResponse("krasmarafon/login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    domain = getattr(request.state, "domain", "krasmarafon")
    creds_ok = (
        username == settings.ADMIN_USERNAME
        and hmac.compare_digest(password, settings.ADMIN_PASSWORD)
    )
    if creds_ok:
        cookie_value = create_session_cookie(username)
        redirect_target = "/admin" if domain == "siberman" else "/business-analytics"
        response = RedirectResponse(redirect_target, status_code=302)
        response.set_cookie(
            COOKIE_NAME,
            cookie_value,
            httponly=True,
            max_age=EXPIRY_SECONDS,
            samesite="lax",
        )
        return response
    login_template = "siberman/login.html" if domain == "siberman" else "krasmarafon/login.html"
    return templates.TemplateResponse(
        login_template,
        {"request": {}, "error": "Неверный логин или пароль"},
        status_code=401,
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user=Depends(require_auth)):
    if isinstance(user, RedirectResponse):
        return user
    if "triatleta" in request.headers.get("host", ""):
        return RedirectResponse("/24h/admin")
    domain = getattr(request.state, "domain", "krasmarafon")
    if domain == "siberman":
        return templates.TemplateResponse("siberman/admin.html", {"request": request})
    return templates.TemplateResponse("krasmarafon/admin.html", {"request": request})


@router.get("/admin/server-metrics", response_class=HTMLResponse)
async def server_metrics_page(
    request: Request,
    user=Depends(require_auth),
):
    """Дашборд реальной нагрузки на сервер."""
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("krasmarafon/server-metrics.html", {"request": request})
