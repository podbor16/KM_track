import asyncio
import hmac
import subprocess
import sys
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel

from src.config import settings
from src.core.auth import (
    COOKIE_NAME, EXPIRY_SECONDS, create_session_cookie, require_auth_for, api_require_auth,
)
from src.race_triatleta.service import get_standings, get_all_laps

_require_auth = require_auth_for("/24h/login")

TRI_EVENT_ID = 1
TRI_LOADER_NAME = "tri_24h"
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOADERS_DIR = BASE_DIR / "config" / "loader"


class YamlBody(BaseModel):
    yaml: str


router = APIRouter(tags=["Triatleta"])
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

@router.get("/24h", response_class=HTMLResponse)
@router.get("/24h/", response_class=HTMLResponse)
async def tri_home(request: Request):
    return templates.TemplateResponse("race_triatleta/tri_results.html", {
        "request": request,
        "event_id": TRI_EVENT_ID,
    })



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@router.get("/api/tri/standings")
async def tri_standings(category: str = None):
    rows = get_standings(TRI_EVENT_ID, category or None)
    return {"standings": rows}


@router.get("/api/tri/laps")
async def tri_laps():
    return {"laps": get_all_laps(TRI_EVENT_ID)}


# ---------------------------------------------------------------------------
# Admin page
# ---------------------------------------------------------------------------

@router.get("/24h/login", response_class=HTMLResponse)
async def tri_login_page(request: Request):
    return templates.TemplateResponse("race_triatleta/login.html", {"request": request, "error": None})


@router.post("/24h/login")
async def tri_login_submit(username: str = Form(...), password: str = Form(...)):
    creds_ok = (
        username == settings.ADMIN_USERNAME
        and hmac.compare_digest(password, settings.ADMIN_PASSWORD)
    )
    if creds_ok:
        cookie_value = create_session_cookie(username)
        response = RedirectResponse("/24h/admin", status_code=302)
        response.set_cookie(
            COOKIE_NAME, cookie_value, httponly=True,
            max_age=EXPIRY_SECONDS, samesite="lax",
        )
        return response
    return templates.TemplateResponse(
        "race_triatleta/login.html",
        {"request": {}, "error": "Неверный логин или пароль"},
        status_code=401,
    )


@router.get("/24h/logout")
async def tri_logout():
    response = RedirectResponse("/24h/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/24h/admin", response_class=HTMLResponse)
async def tri_admin_page(request: Request, user=Depends(_require_auth)):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("race_triatleta/tri_admin.html", {"request": request})



# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

def _tri_systemctl(action: str, timeout: int = 30) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["sudo", "systemctl", action, f"km_tri_loader@{TRI_LOADER_NAME}.service"],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


@router.get("/api/tri/admin/loader")
async def tri_loader_status(user: str = Depends(api_require_auth)):
    ok, _ = _tri_systemctl("is-active", timeout=10)
    return [{"name": TRI_LOADER_NAME, "status": "active" if ok else "inactive"}]


@router.post("/api/tri/admin/loader/start")
async def tri_loader_start(user: str = Depends(api_require_auth)):
    ok, output = _tri_systemctl("start")
    return {"status": "ok" if ok else "error", "output": output}


@router.post("/api/tri/admin/loader/stop")
async def tri_loader_stop(user: str = Depends(api_require_auth)):
    ok, output = _tri_systemctl("stop")
    return {"status": "ok" if ok else "error", "output": output}


@router.post("/api/tri/admin/loader/restart")
async def tri_loader_restart(user: str = Depends(api_require_auth)):
    ok, output = _tri_systemctl("restart")
    return {"status": "ok" if ok else "error", "output": output}


@router.post("/api/tri/admin/loader/init")
async def tri_loader_init(user: str = Depends(api_require_auth)):
    env_file = LOADERS_DIR / f"{TRI_LOADER_NAME}.env"
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
            sys.executable, str(BASE_DIR / "load_tri_results.py"),
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
            if "Вставлено:" in line or "Добавлено" in line:
                try:
                    inserted = int(''.join(filter(str.isdigit, line.split(":")[-1].split()[0])))
                except Exception:
                    pass

        success = proc.returncode == 0
        return {"status": "ok" if success else "error", "inserted": inserted, "output": output[-3000:]}
    except asyncio.TimeoutError:
        return {"status": "error", "inserted": 0, "output": "Timeout: Copernico API не ответил за 3 минуты"}
    except Exception as e:
        return {"status": "error", "inserted": 0, "output": str(e)}


@router.post("/api/tri/admin/loader/resync")
async def tri_loader_resync(user: str = Depends(api_require_auth)):
    """Удаляет все круги события и заново импортирует из Copernico."""
    env_file = LOADERS_DIR / f"{TRI_LOADER_NAME}.env"
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
            sys.executable, str(BASE_DIR / "load_tri_results.py"),
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
            if "Вставлено кругов" in line:
                try:
                    inserted = int(''.join(filter(str.isdigit, line.split(":")[-1].split()[0])))
                except Exception:
                    pass
        return {"status": "ok" if success else "error", "inserted": inserted, "output": output[-3000:]}
    except asyncio.TimeoutError:
        return {"status": "error", "inserted": 0, "output": "Timeout"}
    except Exception as e:
        return {"status": "error", "inserted": 0, "output": str(e)}


# ---------------------------------------------------------------------------
# Preset API
# ---------------------------------------------------------------------------

TRI_PRESET_PATH = BASE_DIR / "config" / "copernico" / "tri_24h_2026.yaml"


@router.get("/api/tri/admin/preset")
async def tri_get_preset(user: str = Depends(api_require_auth)):
    if not TRI_PRESET_PATH.exists():
        raise HTTPException(status_code=404, detail="Пресет не найден")
    return {"yaml": TRI_PRESET_PATH.read_text(encoding="utf-8")}


@router.put("/api/tri/admin/preset")
async def tri_save_preset(body: YamlBody, user: str = Depends(api_require_auth)):
    import yaml as _yaml
    content = body.yaml
    try:
        _yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Невалидный YAML: {e}")
    TRI_PRESET_PATH.write_text(content, encoding="utf-8")
    return {"status": "ok"}
