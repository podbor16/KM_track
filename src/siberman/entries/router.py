"""
Заявки Siberman: вебхук Тильды (POST /webhook/siberman/{секрет}/{год}), API вкладки «Заявки» админки
(/api/siberman/admin/entries/{год}/…) и публичный список для iframe (/entries/{год}, /api/siberman/entries/{год}).
"""
import hmac
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from src.common import ntfy
from src.config import settings
from src.core.auth import api_require_auth
from src.krasmarafon.routers.webhook import parse_body
from src.siberman.entries import service, spool
from src.siberman.entries.parser import BadEntry, is_test_ping
from src.siberman.entries.service import EntriesUnavailable, EntryError
from src.siberman.router import templates

router = APIRouter(tags=["Siberman entries"])
_log = logging.getLogger(__name__)
YEARS = range(2020, 2101)
NO_STORE = {"Cache-Control": "no-store"}
MAX_CSV_BYTES = 5 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class StatusIn(BaseModel):
    status: str


class CommentIn(BaseModel):
    comment: str = ""


def _check_year(year: int) -> None:
    if year not in YEARS:
        raise HTTPException(status_code=404)


def _run(fn, *args) -> JSONResponse:
    try:
        return JSONResponse(jsonable_encoder(fn(*args)), headers=NO_STORE)
    except EntryError as e:
        return JSONResponse({"detail": str(e)}, status_code=503 if isinstance(e, EntriesUnavailable) else 409,
                            headers=NO_STORE)


# ── Вебхук ──────────────────────────────────────────────────────────────────

@router.post("/webhook/siberman/{token}/{year}")
async def entries_webhook(token: str, year: int, request: Request):
    secret = settings.SIBERMAN_WEBHOOK_SECRET
    if not secret or not hmac.compare_digest(token.encode(), secret.encode()):
        raise HTTPException(status_code=403)
    _check_year(year)
    ct = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in ct:
            body = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
        else:
            body = parse_body(await request.body(), ct)
    except Exception as e:
        _log.error(f"siberman entries webhook: тело не разобрано: {e}")
        await run_in_threadpool(ntfy.send, "Siberman: заявка из Тильды не разобрана",
                                ["Тело запроса не читается — см. лог сервера"], priority="high")
        return PlainTextResponse("ok")
    if is_test_ping(body):
        return PlainTextResponse("ok")
    received_at = service.now_krs()
    try:
        path = spool.save(body, year, received_at)
    except Exception:
        _log.error("siberman entries webhook: спул недоступен, пишем напрямую в БД", exc_info=True)
        path = None
    try:
        await run_in_threadpool(service.ingest, year, body, received_at)
        if path:
            spool.done(path)
    except BadEntry as e:
        if path:
            spool.fail(path)
        _log.error(f"siberman entries webhook: не заявка ({e}) — {path.name if path else 'без спула'}")
        await run_in_threadpool(ntfy.send, "Siberman: заявка из Тильды не разобрана",
                                [str(e), f"Файл: failed/{path.name}" if path else "Спул недоступен"],
                                priority="high")
    except Exception as e:
        if path:
            _log.error(f"siberman entries webhook: запись не удалась, повтор из спула: {e}")
        else:
            _log.error(f"siberman entries webhook: заявка потеряна — спул и БД недоступны: {e}")
            await run_in_threadpool(ntfy.send, "Siberman: заявка из Тильды потеряна — спул и БД недоступны",
                                    ["Тильда получила 500 и может повторить запрос"], priority="high")
            return PlainTextResponse("error", status_code=500)
    return PlainTextResponse("ok")


# ── Админка ─────────────────────────────────────────────────────────────────

ADMIN = "/api/siberman/admin/entries/{year}"


@router.get(ADMIN)
def entries_admin_list(year: int, user: str = Depends(api_require_auth)):
    _check_year(year)
    return _run(service.admin_list, year)


@router.get(ADMIN + "/export.xlsx")
def entries_export(year: int, user: str = Depends(api_require_auth)):
    _check_year(year)
    try:
        data = service.export_xlsx(year)
    except EntryError as e:
        return JSONResponse({"detail": str(e)}, status_code=503, headers=NO_STORE)
    name = f"siberman_{year}_zayavki_{service.now_krs():%Y%m%d_%H%M}.xlsx"
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"', **NO_STORE})


@router.post(ADMIN + "/import")
def entries_import(year: int, file: UploadFile = File(...), user: str = Depends(api_require_auth)):
    _check_year(year)
    data = file.file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        return JSONResponse({"detail": "файл слишком большой"}, status_code=409, headers=NO_STORE)
    return _run(service.import_csv, year, data)


@router.get(ADMIN + "/{entry_id}")
def entries_card(year: int, entry_id: int, user: str = Depends(api_require_auth)):
    _check_year(year)
    return _run(service.entry_card, year, entry_id)


@router.post(ADMIN + "/{entry_id}/status")
def entries_status(year: int, entry_id: int, body: StatusIn, user: str = Depends(api_require_auth)):
    _check_year(year)
    return _run(service.set_status, year, entry_id, body.status, user)


@router.post(ADMIN + "/{entry_id}/comment")
def entries_comment(year: int, entry_id: int, body: CommentIn, user: str = Depends(api_require_auth)):
    _check_year(year)
    return _run(service.set_comment, year, entry_id, body.comment, user)


# ── Публичный список ────────────────────────────────────────────────────────

@router.get("/entries/{year}", response_class=HTMLResponse)
async def entries_public_page(request: Request, year: int):
    _check_year(year)
    if getattr(request.state, "domain", "") != "siberman":
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("siberman/entries_public.html", {"request": request, "year": year})


@router.get("/api/siberman/entries/{year}")
def entries_public_api(year: int):
    _check_year(year)
    return _run(service.public_list, year)
