import os
import logging
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.siberman.parser import parse_excel
from src.siberman.service import build_preview, apply_to_db

BASE_DIR = Path(__file__).resolve().parent.parent.parent
router = APIRouter(tags=["Siberman"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

log = logging.getLogger(__name__)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


def _is_authed(request: Request) -> bool:
    """Проверить токен из заголовка X-Admin-Token."""
    if not ADMIN_TOKEN:
        return True  # токен не задан → открыто (для dev)
    return request.headers.get("X-Admin-Token", "") == ADMIN_TOKEN


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
    _pending[race_year] = parsed
    return JSONResponse(preview)


@router.post("/api/siberman/admin/apply")
async def apply_data(request: Request, race_year: int = 2025):
    if not _is_authed(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    parsed = _pending.get(race_year)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Нет загруженных данных. Сначала загрузите файл.")
    summary = apply_to_db(parsed)
    if not summary.get("ok"):
        raise HTTPException(status_code=500, detail=summary.get("error", "Ошибка БД"))
    del _pending[race_year]
    return JSONResponse(summary)


# in-process кэш превью (подходит для одного судьи)
_pending: dict[int, object] = {}
