import asyncio
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
from src.duathlon222.service import get_standings

_require_auth = require_auth_for("/duathlon222/login")

DUATHLON_EVENT_ID = 1  # TODO: заменить на реальный id после INSERT INTO duathlon_222.events
DUATHLON_LOADER_NAME = "duathlon_222"
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOADERS_DIR = BASE_DIR / "config" / "loader"
PRESET_PATH = BASE_DIR / "config" / "copernico" / "duathlon_222_2026.yaml"


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
async def duathlon_home(request: Request):
    return templates.TemplateResponse("race_triatleta/duathlon_results.html", {
        "request": request,
        "event_id": DUATHLON_EVENT_ID,
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@router.get("/api/duathlon222/standings")
async def duathlon_standings(gender: str = None):
    rows = get_standings(DUATHLON_EVENT_ID, gender or None)
    return {"standings": rows}


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
                    inserted = int(''.join(filter(str.isdigit, line.split(":")[1].split(",")[0])))
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
                    inserted = int(''.join(filter(str.isdigit, line.split(":")[1].split(",")[0])))
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
