"""
Рейтинг, рекорды, статистика и география Siberman: блоки для iframe в Тильде (/hall/rating, /hall/records,
/hall/stats, /hall/geo), страница спортсмена /athlete/{id} (отдельная, не iframe) и их API.
API — обычные def: блокирующий mysql-connector уходит в пул потоков. Страницы — только на домене
Siberman.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

from src.siberman.hall import service
from src.siberman.hall.service import HallUnavailable
from src.siberman.router import templates

router = APIRouter(tags=["Siberman hall"])


def _page(request: Request, template: str):
    if getattr(request.state, "domain", "") != "siberman":
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(template, {"request": request})


def _json(fn, *args) -> JSONResponse:
    try:
        data = fn(*args)
    except HallUnavailable as e:
        return JSONResponse({"detail": str(e)}, status_code=503, headers={"Cache-Control": "no-store"})
    if data is None:
        raise HTTPException(status_code=404)
    return JSONResponse(jsonable_encoder(data))


@router.get("/hall/rating", response_class=HTMLResponse)
async def hall_rating_page(request: Request):
    return _page(request, "siberman/hall_rating.html")


@router.get("/hall/records", response_class=HTMLResponse)
async def hall_records_page(request: Request):
    return _page(request, "siberman/hall_records.html")


@router.get("/hall/stats", response_class=HTMLResponse)
async def hall_stats_page(request: Request):
    return _page(request, "siberman/hall_stats.html")


@router.get("/hall/geo", response_class=HTMLResponse)
async def hall_geo_page(request: Request):
    return _page(request, "siberman/hall_geo.html")


@router.get("/athlete/{person_id}", response_class=HTMLResponse)
def athlete_page(request: Request, person_id: str):
    """Страница спортсмена (не iframe). Нет такого человека или id не число — 404-страница Siberman;
    БД недоступна — страница, которая сама покажет «временно недоступны»."""
    if getattr(request.state, "domain", "") != "siberman":
        raise HTTPException(status_code=404)
    pid = int(person_id) if person_id.isdigit() else None
    try:
        found = pid is not None and service.athlete(pid) is not None
    except HallUnavailable:
        found = True
    return templates.TemplateResponse("siberman/athlete.html", {"request": request, "person_id": pid, "found": found},
                                      status_code=200 if found else 404)


@router.get("/api/siberman/hall/rating")
def api_hall_rating():
    return _json(service.rating)


@router.get("/api/siberman/hall/records")
def api_hall_records():
    return _json(service.records)


@router.get("/api/siberman/hall/records/history")
def api_hall_record_history(cell: str = ""):
    return _json(service.record_history, cell)


@router.get("/api/siberman/hall/stats")
def api_hall_stats():
    return _json(service.stats)


@router.get("/api/siberman/hall/geo")
def api_hall_geo():
    return _json(service.geography)


@router.get("/api/siberman/athlete/{person_id}")
def api_athlete(person_id: int):
    return _json(service.athlete, person_id)
