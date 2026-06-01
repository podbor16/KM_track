"""
HTML-страницы приложения KM_track.
Все эндпоинты, возвращающие HTMLResponse (Jinja2 шаблоны).
"""

import hmac
import logging
from typing import Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.config.event_loader import get_event_by_name
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
    return templates.TemplateResponse("tracker.html", {
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
    """Главная страница — трекер текущего события."""
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
    return templates.TemplateResponse("start_list.html", {
        "request": request,
        "event": settings.CURRENT_EVENT,
    })


@router.get("/analytics")
async def analytics_page():
    """Legacy URL — перенаправляем в админку."""
    return RedirectResponse("/admin", status_code=302)


@router.get("/results", response_class=HTMLResponse)
async def results_page(request: Request):
    """Результаты забега."""
    return templates.TemplateResponse("results.html", {
        "request": request,
        "event": settings.CURRENT_EVENT,
    })


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """История: поиск по спортсмену и по забегу."""
    return templates.TemplateResponse("history.html", {"request": request})


@router.get("/athlete-profile", response_class=HTMLResponse)
async def athlete_profile_page(request: Request):
    """Профиль спортсмена со всеми его результатами."""
    return templates.TemplateResponse("athlete-profile.html", {"request": request})


@router.get("/race-analysis", response_class=HTMLResponse)
async def race_analysis_page(request: Request):
    """Анализ забегов с выбором события и года."""
    return templates.TemplateResponse("race-analysis.html", {"request": request})


# ============================================================================
# АВТОРИЗАЦИЯ
# ============================================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(
    username: str = Form(...),
    password: str = Form(...),
):
    creds_ok = (
        username == settings.ADMIN_USERNAME
        and hmac.compare_digest(password, settings.ADMIN_PASSWORD)
    )
    if creds_ok:
        cookie_value = create_session_cookie(username)
        response = RedirectResponse("/business-analytics", status_code=302)
        response.set_cookie(
            COOKIE_NAME,
            cookie_value,
            httponly=True,
            max_age=EXPIRY_SECONDS,
            samesite="lax",
        )
        return response
    return templates.TemplateResponse(
        "login.html",
        {"request": {}, "error": "Неверный логин или пароль"},
        status_code=401,
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ============================================================================
# БИЗНЕС-АНАЛИТИКА (защищённая страница)
# ============================================================================

@router.get("/business-analytics")
async def business_analytics_page():
    """Бизнес-аналитика переехала в /admin → вкладка Аналитика."""
    return RedirectResponse("/admin", status_code=302)


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user=Depends(require_auth)):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("admin.html", {"request": request})


@router.get("/admin/server-metrics", response_class=HTMLResponse)
async def server_metrics_page(
    request: Request,
    user=Depends(require_auth),
):
    """Дашборд реальной нагрузки на сервер."""
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("server-metrics.html", {"request": request})
