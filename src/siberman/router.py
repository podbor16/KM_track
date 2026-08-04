import pickle
import logging
import tempfile
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.siberman.parser import parse_excel
from src.siberman.service import (
    build_preview, apply_to_db, convert_bike_times_to_elapsed, build_bike_day2_starts,
)
from src.siberman.db import (
    get_siberman_connection, get_results_for_year, set_race_start, get_latest_race_year,
    set_stage_starts,
)
from src.core.auth import api_require_auth

BASE_DIR = Path(__file__).resolve().parent.parent.parent
router = APIRouter(tags=["Siberman"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _get_deploy_version() -> str:
    """Git short hash текущего коммита — меняется с каждым деплоем, используется
    как ?v= у статики, чтобы браузер не держал 7-дневный кэш старой версии."""
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


templates.env.globals["v"] = _get_deploy_version()

log = logging.getLogger(__name__)

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


def _parse_race_start(raw: str) -> datetime.datetime:
    """'YYYY-MM-DDTHH:MM' или 'YYYY-MM-DDTHH:MM:SS' (input type=datetime-local) →
    datetime. Гонка многодневная, поэтому нужна не только время-суток, но и
    дата — иначе нельзя построить абсолютный якорь для live-секундомера
    этапов (bike_day2/run стартуют на следующий календарный день)."""
    try:
        return datetime.datetime.fromisoformat(raw.strip())
    except ValueError:
        raise ValueError(f"Неверный формат времени старта: {raw!r}")


@router.get("/participant/{bib}", response_class=HTMLResponse)
async def participant_page(request: Request, bib: str, year: int = 2025):
    """Данные подгружаются на клиенте из уже существующего
    /api/siberman/results (тот же пул данных, что и у результатов), bib
    ищется среди individual/relay в JS."""
    return templates.TemplateResponse(
        "siberman/participant.html", {"request": request, "bib": bib, "year": year}
    )


@router.get("/api/siberman/results")
async def api_results(year: Optional[int] = None):
    # year не передан — публичная страница больше не даёт выбор года руками
    # (year-select убран, 2026-08-04): используем последний год с данными
    # (задаётся тем, что реально загружено в админке).
    conn = get_siberman_connection()
    if conn is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    try:
        if year is None:
            year = get_latest_race_year(conn)
            if year is None:
                raise HTTPException(status_code=404, detail="Нет загруженных данных ни за один год")
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
    for key in ("race_start", "bike2_start", "run_start"):
        if data.get(key) is not None:
            data[key] = data[key].isoformat()
    return JSONResponse(data)


@router.post("/api/siberman/admin/stage-starts")
async def set_stage_starts_endpoint(race_year: int = 2025, bike2_start: str = "", run_start: str = "",
                                     user: str = Depends(api_require_auth)):
    """Расписание Вело Дня 2 / Бега — независимо от race_start (Дня 1),
    задаётся отдельно и в любой момент (не обязательно при загрузке файла).
    Пустая строка — снять время (расписание ещё не решено)."""
    try:
        b2 = _parse_race_start(bike2_start) if bike2_start else None
        rn = _parse_race_start(run_start) if run_start else None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    conn = get_siberman_connection()
    if conn is None:
        raise HTTPException(status_code=503, detail="DB unavailable")
    try:
        set_stage_starts(conn, race_year, b2, rn)
    finally:
        conn.close()
    return {"ok": True}


@router.post("/api/siberman/admin/upload")
async def upload_excel(file: UploadFile = File(...),
                        race_year: int = 2025, race_start: str = "",
                        user: str = Depends(api_require_auth)):
    if not race_start:
        raise HTTPException(status_code=422, detail="Укажите время старта гонки (день 1)")
    try:
        race_start_dt = _parse_race_start(race_start)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    race_start_s = race_start_dt.hour * 3600 + race_start_dt.minute * 60 + race_start_dt.second

    data = await file.read()
    try:
        parsed = parse_excel(data, race_year)
    except Exception as e:
        log.error(f"Parse error: {e}")
        raise HTTPException(status_code=422, detail=f"Ошибка парсинга: {e}")

    bike_day2_starts = convert_bike_times_to_elapsed(parsed, race_start_s)
    parsed.handicaps = bike_day2_starts  # {rider_key: start_day2_s} → apply_to_db пишет в bike_day2_handicap_s
    parsed.race_start = race_start_dt

    preview = build_preview(parsed)
    preview["bike_day2_starts"] = build_bike_day2_starts(parsed, bike_day2_starts)
    _save_pending(race_year, parsed)
    return JSONResponse(preview)


@router.post("/api/siberman/admin/apply")
async def apply_data(race_year: int = 2025, user: str = Depends(api_require_auth)):
    parsed = _load_pending(race_year)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Нет загруженных данных. Сначала загрузите файл.")
    summary = apply_to_db(parsed)
    if not summary.get("ok"):
        raise HTTPException(status_code=500, detail=summary.get("error", "Ошибка БД"))
    if parsed.race_start is not None:
        conn = get_siberman_connection()
        if conn is not None:
            try:
                set_race_start(conn, race_year, parsed.race_start)
            finally:
                conn.close()
    _clear_pending(race_year)
    return JSONResponse(summary)
