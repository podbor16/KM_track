"""
Рейтинг и рекорды Siberman: блоки для iframe в Тильде (/hall/rating, /hall/records) и их API.
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
PUBLIC_CACHE = {"Cache-Control": "public, max-age=60"}


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
    return JSONResponse(jsonable_encoder(data), headers=PUBLIC_CACHE)


@router.get("/hall/rating", response_class=HTMLResponse)
async def hall_rating_page(request: Request):
    return _page(request, "siberman/hall_rating.html")


@router.get("/hall/records", response_class=HTMLResponse)
async def hall_records_page(request: Request):
    return _page(request, "siberman/hall_records.html")


@router.get("/api/siberman/hall/rating")
def api_hall_rating():
    return _json(service.rating)


@router.get("/api/siberman/hall/records")
def api_hall_records():
    return _json(service.records)


@router.get("/api/siberman/hall/records/history")
def api_hall_record_history(cell: str = ""):
    return _json(service.record_history, cell)
