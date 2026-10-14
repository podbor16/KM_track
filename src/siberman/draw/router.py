"""
Жеребьёвка Siberman: админка оператора (/admin/draw), публичные блоки для iframe в Тильде
(/draw/{год}/aquarium|results), API и фиды для vMix (/api/siberman/draw/{год}/feed/*.json|csv).
API — обычные def: блокирующий mysql-connector уходит в пул потоков, не держит event loop.
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from src.core.auth import api_require_auth, require_auth_for
from src.siberman.draw import service
from src.siberman.draw.service import DrawError
from src.siberman.router import templates

router = APIRouter(tags=["Siberman draw"])
_page_auth = require_auth_for("/login")
NO_STORE = {"Cache-Control": "no-store"}
YEARS = range(2020, 2101)


class PickIn(BaseModel):
    applicant_id: int


class RoundIn(BaseModel):
    round: int


class PaymentIn(BaseModel):
    applicant_id: int
    status: str
    comment: str = ""


class ConfigIn(BaseModel):
    capacity_men: Optional[int] = None
    capacity_women: Optional[int] = None
    capacity_relay: Optional[int] = None
    quota_repeat_men: Optional[int] = None
    quota_repeat_women: Optional[int] = None
    quota_novice_men: Optional[int] = None
    quota_novice_women: Optional[int] = None
    auto_invite_until: Optional[datetime.date] = None


class ResetIn(BaseModel):
    confirm: str


def _json(data, status: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(data), status_code=status, headers=NO_STORE)


def _run(fn, *args, **kwargs) -> JSONResponse:
    try:
        return _json(fn(*args, **kwargs))
    except DrawError as e:
        return _json({"detail": str(e)}, 409)


def _check_year(year: int) -> None:
    if year not in YEARS:
        raise HTTPException(status_code=404)


def _siberman_page(request: Request, template: str, year: int):
    _check_year(year)
    if getattr(request.state, "domain", "") != "siberman":
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(template, {"request": request, "year": year})


# ── Страницы ────────────────────────────────────────────────────────────────

@router.get("/admin/draw", response_class=HTMLResponse)
async def draw_admin_page(request: Request, year: int = 2028, user=Depends(_page_auth)):
    if isinstance(user, RedirectResponse):
        return user
    return _siberman_page(request, "siberman/draw_admin.html", year)


@router.get("/draw/{year}/aquarium", response_class=HTMLResponse)
async def draw_aquarium_page(request: Request, year: int):
    return _siberman_page(request, "siberman/draw_aquarium.html", year)


@router.get("/draw/{year}/results", response_class=HTMLResponse)
async def draw_results_page(request: Request, year: int):
    return _siberman_page(request, "siberman/draw_results.html", year)


# ── Публичное API и фиды vMix ───────────────────────────────────────────────

@router.get("/api/siberman/draw/{year}/state")
def draw_public_state(year: int):
    _check_year(year)
    return _run(service.public_state, year)


@router.get("/api/siberman/draw/{year}/feed/{filename}")
def draw_feed(year: int, filename: str):
    _check_year(year)
    name, _, fmt = filename.partition(".")
    if fmt not in ("json", "csv") or name not in service.FEEDS:
        raise HTTPException(status_code=404)
    try:
        rows = service.feed_rows(year, name)
    except DrawError as e:
        return _json({"detail": str(e)}, 409)
    if fmt == "json":
        return _json(rows)
    return Response(service.to_csv(rows, service.FEED_COLUMNS[name]),
                    media_type="text/csv; charset=utf-8", headers=NO_STORE)


# ── Админка ─────────────────────────────────────────────────────────────────

ADMIN = "/api/siberman/admin/draw/{year}"


@router.get(ADMIN + "/state")
def draw_admin_state(year: int, user: str = Depends(api_require_auth)):
    _check_year(year)
    return _run(service.admin_state, year)


@router.get(ADMIN + "/applicant/{applicant_id}")
def draw_applicant(year: int, applicant_id: int, user: str = Depends(api_require_auth)):
    return _run(service.applicant_summary, year, applicant_id)


@router.post(ADMIN + "/round")
def draw_set_round(year: int, body: RoundIn, user: str = Depends(api_require_auth)):
    return _run(service.set_round, year, body.round, user)


@router.post(ADMIN + "/pick")
def draw_pick(year: int, body: PickIn, user: str = Depends(api_require_auth)):
    return _run(service.pick, year, body.applicant_id, user)


@router.post(ADMIN + "/picks/{pick_id}/cancel")
def draw_cancel(year: int, pick_id: int, user: str = Depends(api_require_auth)):
    return _run(service.cancel, year, pick_id, user)


@router.post(ADMIN + "/picks/{pick_id}/replace")
def draw_replace(year: int, pick_id: int, body: PickIn, user: str = Depends(api_require_auth)):
    return _run(service.replace, year, pick_id, body.applicant_id, user)


@router.post(ADMIN + "/payment")
def draw_payment(year: int, body: PaymentIn, user: str = Depends(api_require_auth)):
    return _run(service.set_payment, year, body.applicant_id, body.status, body.comment, user)


@router.post(ADMIN + "/config")
def draw_config(year: int, body: ConfigIn, user: str = Depends(api_require_auth)):
    return _run(service.save_config, year, body.model_dump(), user)


@router.post(ADMIN + "/import")
def draw_import(year: int, file: UploadFile = File(...), dry_run: bool = Form(True),
                user: str = Depends(api_require_auth)):
    return _run(service.import_applicants, year, file.file.read(), dry_run, user)


@router.post(ADMIN + "/reset")
def draw_reset(year: int, body: ResetIn, user: str = Depends(api_require_auth)):
    return _run(service.reset, year, body.confirm, user)
