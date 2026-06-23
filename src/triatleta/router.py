import asyncio
import subprocess
import sys
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.core.auth import require_auth, api_require_auth
from src.triatleta.service import get_standings, get_all_laps

TRI_EVENT_ID = 1
TRI_LOADER_NAME = "tri_24h"
BASE_DIR = Path(__file__).resolve().parent.parent.parent

router = APIRouter(tags=["Triatleta"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@router.get("/tri", response_class=HTMLResponse)
@router.get("/tri/", response_class=HTMLResponse)
async def tri_home(request: Request):
    return templates.TemplateResponse("tri_results.html", {
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

@router.get("/tri/admin", response_class=HTMLResponse)
async def tri_admin_page(request: Request, user=Depends(require_auth)):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("tri_admin.html", {"request": request})


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

def _tri_systemctl(action: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["sudo", "systemctl", action, f"km_tri_loader@{TRI_LOADER_NAME}.service"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


@router.get("/api/tri/admin/loader")
async def tri_loader_status(user: str = Depends(api_require_auth)):
    ok, _ = _tri_systemctl("is-active")
    return {"name": TRI_LOADER_NAME, "status": "active" if ok else "inactive"}


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
