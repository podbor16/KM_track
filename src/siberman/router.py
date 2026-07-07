import os
import pickle
import logging
import tempfile
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.siberman.parser import parse_excel
from src.siberman.service import build_preview, apply_to_db
from src.siberman.db import get_siberman_connection, get_results_for_year

BASE_DIR = Path(__file__).resolve().parent.parent.parent
router = APIRouter(tags=["Siberman"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

log = logging.getLogger(__name__)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# Путь к временным файлам (общий для всех воркеров gunicorn)
_PENDING_DIR = Path(tempfile.gettempdir()) / "siberman_pending"
_PENDING_DIR.mkdir(exist_ok=True)


def _pending_path(race_year: int) -> Path:
    return _PENDING_DIR / f"pending_{race_year}.pkl"


def _save_pending(race_year: int, parsed) -> None:
    with open(_pending_path(race_year), "wb") as f:
        pickle.dump(parsed, f)


def _load_pending(race_year: int):
    p = _pending_path(race_year)
    if not p.exists():
        return None
    with open(p, "rb") as f:
        return pickle.load(f)


def _clear_pending(race_year: int) -> None:
    _pending_path(race_year).unlink(missing_ok=True)


def _is_authed(request: Request) -> bool:
    if not ADMIN_TOKEN:
        return True
    return request.headers.get("X-Admin-Token", "") == ADMIN_TOKEN


@router.get("/siberman/results", response_class=HTMLResponse)
async def results_page(request: Request):
    return templates.TemplateResponse(
        "siberman/results.html", {"request": request}
    )


@router.get("/api/siberman/results")
async def api_results(year: int = 2025):
    conn = get_siberman_connection()
    if conn is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    try:
        data = get_results_for_year(conn, year)
    finally:
        conn.close()
    # Конвертируем Decimal → float для JSON-сериализации
    import decimal
    def _clean(v):
        return float(v) if isinstance(v, decimal.Decimal) else v
    def _clean_row(row):
        return {k: _clean(v) for k, v in row.items()}
    data["individual"] = [_clean_row(r) for r in data["individual"]]
    for team in data["relay"]:
        team["members"] = [_clean_row(m) for m in team["members"]]
    return JSONResponse(data)


@router.get("/siberman/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(
        "siberman/admin.html", {"request": request}
    )


@router.post("/api/siberman/admin/upload")
async def upload_excel(request: Request, file: UploadFile = File(...),
                        race_year: int = 2025):
    if not _is_authed(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = await file.read()
    try:
        parsed = parse_excel(data, race_year)
    except Exception as e:
        log.error(f"Parse error: {e}")
        raise HTTPException(status_code=422, detail=f"Ошибка парсинга: {e}")
    preview = build_preview(parsed)
    _save_pending(race_year, parsed)
    return JSONResponse(preview)


@router.post("/api/siberman/admin/apply")
async def apply_data(request: Request, race_year: int = 2025):
    if not _is_authed(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    parsed = _load_pending(race_year)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Нет загруженных данных. Сначала загрузите файл.")
    summary = apply_to_db(parsed)
    if not summary.get("ok"):
        raise HTTPException(status_code=500, detail=summary.get("error", "Ошибка БД"))
    _clear_pending(race_year)
    return JSONResponse(summary)
