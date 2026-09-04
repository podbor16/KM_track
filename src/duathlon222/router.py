import asyncio
import subprocess
import sys
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel

from src.config import settings
from src.config.event_loader import load_events_cached
from src.core.auth import (
    COOKIE_NAME, EXPIRY_SECONDS, create_session_cookie, require_auth_for, api_require_auth,
)
from src.duathlon222.service import get_standings, get_participant, get_stage_mark_broadcast, get_available_marks

_require_auth = require_auth_for("/duathlon222/login")

# Год по умолчанию — на него редиректит "голый" /duathlon222 (обратная
# совместимость с URL, который был единственным до 2026-09-03) и на него же
# смотрит админка/загрузчик (управление "текущей" гонкой — не архивное,
# организаторам не нужно выбирать год для управления systemd-сервисом).
CURRENT_YEAR = 2026
DUATHLON_LOADER_NAME = "duathlon_222"
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOADERS_DIR = BASE_DIR / "config" / "loader"
PRESET_PATH = BASE_DIR / "config" / "copernico" / "duathlon_222_2026.yaml"


def _year_exists(year: int) -> bool:
    """Есть ли вообще конфиг события на этот год (config/events/*.yaml с
    code == "duathlon_222_{year}") — 404 для несуществующего года, но НЕ для
    года, у которого просто ещё не заполнен db_event_id (см. _resolve_event_id)."""
    return f"duathlon_222_{year}" in load_events_cached()


def _resolve_event_id(year: int) -> Optional[int]:
    """db_event_id для конкретного года по config/events/*.yaml, где
    code == "duathlon_222_{year}" (см. EventConfig в src/config/event_loader.py).
    Новый год — новый YAML-файл с этим code, без правок роутера. None, если
    db_event_id ещё не заполнен в YAML (до вставки записи в БД) — не ошибка,
    get_standings/get_participant с event_id=None просто вернут пустые данные."""
    events = load_events_cached()
    event = events.get(f"duathlon_222_{year}")
    if event is None or not event.distances:
        return None
    return event.distances[0].db_event_id


class YamlBody(BaseModel):
    yaml: str


router = APIRouter(tags=["Duathlon222"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _get_deploy_version() -> str:
    import subprocess as _sp, time as _t
    try:
        r = _sp.run(["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, timeout=3, cwd=str(BASE_DIR))
        v = r.stdout.strip()
        if v:
            return v
    except Exception:
        pass
    return str(int(_t.time()))


templates.env.globals["v"] = _get_deploy_version()


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@router.get("/duathlon222", response_class=HTMLResponse)
@router.get("/duathlon222/", response_class=HTMLResponse)
async def duathlon_home_redirect():
    """Обратная совместимость с URL без года (единственный вариант до
    2026-09-03) — редирект на текущий год."""
    return RedirectResponse(f"/duathlon222_{CURRENT_YEAR}", status_code=307)


@router.get("/duathlon222/participant/{start_number}", response_class=HTMLResponse)
async def duathlon_participant_page_redirect(start_number: int):
    return RedirectResponse(f"/duathlon222_{CURRENT_YEAR}/participant/{start_number}", status_code=307)


@router.get("/duathlon222_{year}", response_class=HTMLResponse)
@router.get("/duathlon222_{year}/", response_class=HTMLResponse)
async def duathlon_home(request: Request, year: int):
    if not _year_exists(year):
        raise HTTPException(status_code=404, detail=f"Дуатлон 222 за {year} год не найден")
    return templates.TemplateResponse("race_triatleta/duathlon_results.html", {
        "request": request,
        "year": year,
    })


@router.get("/duathlon222_{year}/participant/{start_number}", response_class=HTMLResponse)
async def duathlon_participant_page(request: Request, year: int, start_number: int):
    if not _year_exists(year):
        raise HTTPException(status_code=404, detail=f"Дуатлон 222 за {year} год не найден")
    return templates.TemplateResponse("race_triatleta/duathlon_participant.html", {
        "request": request,
        "year": year,
        "start_number": start_number,
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@router.get("/api/duathlon222_{year}/standings")
async def duathlon_standings(year: int, gender: str = None):
    if not _year_exists(year):
        raise HTTPException(status_code=404, detail=f"Дуатлон 222 за {year} год не найден")
    rows = get_standings(_resolve_event_id(year), gender or None)
    return {"standings": rows}


@router.get("/api/duathlon222_{year}/available-marks/{stage}")
async def duathlon_available_marks(year: int, stage: str, gender: str = None, user: str = Depends(api_require_auth)):
    """Список отметок этапа с данными — заполняет выпадающий список выбора
    отметки в генераторе постов (/duathlon222/admin)."""
    if stage not in ("run1", "bike", "run2"):
        raise HTTPException(status_code=400, detail="stage: run1 | bike | run2")
    if gender not in (None, "M", "F"):
        raise HTTPException(status_code=400, detail="gender: M | F")
    if not _year_exists(year):
        raise HTTPException(status_code=404, detail=f"Дуатлон 222 за {year} год не найден")
    return {"marks": get_available_marks(_resolve_event_id(year), stage, gender)}


@router.get("/api/duathlon222_{year}/stage-mark/{stage}")
async def duathlon_stage_mark(
    year: int, stage: str, gender: str = None, lap: int = None, user: str = Depends(api_require_auth),
):
    """Снимок «кто где был на отметке этапа» — для поста трансляции в
    /duathlon222/admin. Авторизация как у остальной админки — не публичный
    эндпоинт (не нужен на самой странице результатов). lap не передан —
    берётся самая дальняя (последняя) отметка пула, как раньше."""
    if stage not in ("run1", "bike", "run2"):
        raise HTTPException(status_code=400, detail="stage: run1 | bike | run2")
    if gender not in (None, "M", "F"):
        raise HTTPException(status_code=400, detail="gender: M | F")
    if not _year_exists(year):
        raise HTTPException(status_code=404, detail=f"Дуатлон 222 за {year} год не найден")
    data = get_stage_mark_broadcast(_resolve_event_id(year), stage, gender, lap)
    if data is None:
        return {"available": False}
    return {"available": True, **data}


@router.get("/api/duathlon222_{year}/participant/{start_number}")
async def duathlon_participant_api(year: int, start_number: int):
    if not _year_exists(year):
        raise HTTPException(status_code=404, detail=f"Дуатлон 222 за {year} год не найден")
    data = get_participant(_resolve_event_id(year), start_number)
    if data is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    return data


# ---------------------------------------------------------------------------
# Admin page
# ---------------------------------------------------------------------------

@router.get("/duathlon222/login", response_class=HTMLResponse)
async def duathlon_login_page(request: Request):
    return templates.TemplateResponse("race_triatleta/duathlon_login.html", {"request": request, "error": None})


@router.post("/duathlon222/login")
async def duathlon_login_submit(username: str = Form(...), password: str = Form(...)):
    import hmac
    creds_ok = (
        username == settings.ADMIN_USERNAME
        and hmac.compare_digest(password, settings.ADMIN_PASSWORD)
    )
    if creds_ok:
        cookie_value = create_session_cookie(username)
        response = RedirectResponse("/duathlon222/admin", status_code=302)
        response.set_cookie(
            COOKIE_NAME, cookie_value, httponly=True,
            max_age=EXPIRY_SECONDS, samesite="lax",
        )
        return response
    return templates.TemplateResponse(
        "race_triatleta/duathlon_login.html",
        {"request": {}, "error": "Неверный логин или пароль"},
        status_code=401,
    )


@router.get("/duathlon222/logout")
async def duathlon_logout():
    response = RedirectResponse("/duathlon222/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/duathlon222/admin", response_class=HTMLResponse)
async def duathlon_admin_page(request: Request, user=Depends(_require_auth)):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("race_triatleta/duathlon_admin.html", {"request": request})


# ---------------------------------------------------------------------------
# Admin API — loader control
# ---------------------------------------------------------------------------

def _duathlon_systemctl(action: str, timeout: int = 30) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["sudo", "systemctl", action, f"km_duathlon_loader@{DUATHLON_LOADER_NAME}.service"],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


@router.get("/api/duathlon222/admin/loader")
async def duathlon_loader_status(user: str = Depends(api_require_auth)):
    ok, _ = _duathlon_systemctl("is-active", timeout=10)
    return [{"name": DUATHLON_LOADER_NAME, "status": "active" if ok else "inactive"}]


@router.post("/api/duathlon222/admin/loader/start")
async def duathlon_loader_start(user: str = Depends(api_require_auth)):
    ok, output = _duathlon_systemctl("start")
    return {"status": "ok" if ok else "error", "output": output}


@router.post("/api/duathlon222/admin/loader/stop")
async def duathlon_loader_stop(user: str = Depends(api_require_auth)):
    ok, output = _duathlon_systemctl("stop")
    return {"status": "ok" if ok else "error", "output": output}


@router.post("/api/duathlon222/admin/loader/restart")
async def duathlon_loader_restart(user: str = Depends(api_require_auth)):
    ok, output = _duathlon_systemctl("restart")
    return {"status": "ok" if ok else "error", "output": output}


@router.post("/api/duathlon222/admin/loader/init")
async def duathlon_loader_init(user: str = Depends(api_require_auth)):
    env_file = LOADERS_DIR / f"{DUATHLON_LOADER_NAME}.env"
    if not env_file.exists():
        raise HTTPException(status_code=404, detail="Конфиг загрузчика не найден")

    config_path = None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("LOADER_CONFIG="):
            config_path = line.split("=", 1)[1].strip()
    if not config_path:
        raise HTTPException(status_code=400, detail="LOADER_CONFIG не найден в .env файле")

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(BASE_DIR / "load_duathlon_results.py"),
            "--config", config_path,
            "--init",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BASE_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        output = (stdout + stderr).decode("utf-8", errors="replace")

        inserted = 0
        for line in output.splitlines():
            if "Участников:" in line:
                try:
                    # split(":") ломался на таймстемпе строки лога ("16:49:56"
                    # тоже содержит ":") — брал минуты вместо счётчика после
                    # "Участников:". Найдено 2026-09-04 при проверке фикса
                    # пересинхронизации: admin-панель показывала "49" вместо
                    # реальных 14. split() по самой метке — не по любому ":".
                    inserted = int(''.join(filter(str.isdigit, line.split("Участников:", 1)[1].split(",")[0])))
                except Exception:
                    pass

        success = proc.returncode == 0
        return {"status": "ok" if success else "error", "inserted": inserted, "output": output[-3000:]}
    except asyncio.TimeoutError:
        return {"status": "error", "inserted": 0, "output": "Timeout: Copernico API не ответил за 3 минуты"}
    except Exception as e:
        return {"status": "error", "inserted": 0, "output": str(e)}


@router.post("/api/duathlon222/admin/loader/resync")
async def duathlon_loader_resync(user: str = Depends(api_require_auth)):
    """Сбрасывает этапы всех участников и заново импортирует из Copernico."""
    env_file = LOADERS_DIR / f"{DUATHLON_LOADER_NAME}.env"
    if not env_file.exists():
        raise HTTPException(status_code=404, detail="Конфиг загрузчика не найден")

    config_path = None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("LOADER_CONFIG="):
            config_path = line.split("=", 1)[1].strip()
    if not config_path:
        raise HTTPException(status_code=400, detail="LOADER_CONFIG не найден в .env файле")

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(BASE_DIR / "load_duathlon_results.py"),
            "--config", config_path,
            "--resync",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BASE_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        output = (stdout + stderr).decode("utf-8", errors="replace")
        success = proc.returncode == 0
        inserted = 0
        for line in output.splitlines():
            if "Участников:" in line:
                try:
                    # split(":") ломался на таймстемпе строки лога ("16:49:56"
                    # тоже содержит ":") — брал минуты вместо счётчика после
                    # "Участников:". Найдено 2026-09-04 при проверке фикса
                    # пересинхронизации: admin-панель показывала "49" вместо
                    # реальных 14. split() по самой метке — не по любому ":".
                    inserted = int(''.join(filter(str.isdigit, line.split("Участников:", 1)[1].split(",")[0])))
                except Exception:
                    pass
        return {"status": "ok" if success else "error", "inserted": inserted, "output": output[-3000:]}
    except asyncio.TimeoutError:
        return {"status": "error", "inserted": 0, "output": "Timeout"}
    except Exception as e:
        return {"status": "error", "inserted": 0, "output": str(e)}


# ---------------------------------------------------------------------------
# Admin API — preset editor
# ---------------------------------------------------------------------------

@router.get("/api/duathlon222/admin/preset")
async def duathlon_get_preset(user: str = Depends(api_require_auth)):
    if not PRESET_PATH.exists():
        raise HTTPException(status_code=404, detail="Пресет не найден")
    return {"yaml": PRESET_PATH.read_text(encoding="utf-8")}


@router.put("/api/duathlon222/admin/preset")
async def duathlon_save_preset(body: YamlBody, user: str = Depends(api_require_auth)):
    import yaml as _yaml
    content = body.yaml
    try:
        _yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Невалидный YAML: {e}")
    PRESET_PATH.write_text(content, encoding="utf-8")
    return {"status": "ok"}
