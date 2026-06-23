from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.triatleta.service import get_standings, get_all_laps

TRI_EVENT_ID = 1

router = APIRouter(tags=["Triatleta"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


@router.get("/tri", response_class=HTMLResponse)
@router.get("/tri/", response_class=HTMLResponse)
async def tri_home(request: Request):
    return templates.TemplateResponse("tri_results.html", {
        "request": request,
        "event_id": TRI_EVENT_ID,
    })


@router.get("/api/tri/standings")
async def tri_standings(category: str = None):
    rows = get_standings(TRI_EVENT_ID, category or None)
    return {"standings": rows}


@router.get("/api/tri/laps")
async def tri_laps():
    return {"laps": get_all_laps(TRI_EVENT_ID)}
