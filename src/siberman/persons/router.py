"""
Админка реестра людей Siberman: страница /admin/people и API /api/siberman/admin/people/*.
API — обычные def: блокирующий mysql-connector уходит в пул потоков. Статичные пути объявлены
раньше /{person_id}, иначе FastAPI сопоставит 'search' с параметром.
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from src.core.auth import api_require_auth, require_auth_for
from src.siberman.persons import service
from src.siberman.persons.service import PersonsError, PersonsUnavailable
from src.siberman.router import templates

router = APIRouter(tags=["Siberman persons"])
_page_auth = require_auth_for("/login")
NO_STORE = {"Cache-Control": "no-store"}
MAX_CSV_BYTES = 10 * 1024 * 1024
API = "/api/siberman/admin/people"


class MergeIn(BaseModel):
    source_id: int
    target_id: int
    review_id: Optional[int] = None      # решение по записи «проверить» — в той же транзакции


class ReassignIn(BaseModel):
    keys: list[tuple[int, str, str]]
    target_id: Optional[int] = None
    review_id: Optional[int] = None


class BirthdateIn(BaseModel):
    birthdate: Optional[datetime.date] = None
    review_id: Optional[int] = None


class CityIn(BaseModel):
    city: str = ""


class ReviewStatusIn(BaseModel):
    status: str


def _json(data, status: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(data), status_code=status, headers=NO_STORE)


def _run(fn, *args, **kwargs) -> JSONResponse:
    try:
        return _json(fn(*args, **kwargs))
    except PersonsError as e:
        return _json({"detail": str(e)}, 503 if isinstance(e, PersonsUnavailable) else 409)


@router.get("/admin/people", response_class=HTMLResponse)
async def people_admin_page(request: Request, user=Depends(_page_auth)):
    if isinstance(user, RedirectResponse):
        return user
    if getattr(request.state, "domain", "") != "siberman":
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("siberman/people_admin.html", {"request": request})


@router.get(f"{API}/reviews")
def api_reviews(status: str = "open", user: str = Depends(api_require_auth)):
    return _run(service.reviews, status)


@router.post(f"{API}/reviews/{{review_id}}")
def api_review_status(review_id: int, body: ReviewStatusIn, user: str = Depends(api_require_auth)):
    return _run(service.set_review_status, review_id, body.status, user)


@router.post(f"{API}/reviews/{{review_id}}/keep")
def api_keep_link(review_id: int, user: str = Depends(api_require_auth)):
    return _run(service.keep_link, review_id, user)


@router.get(f"{API}/search")
def api_search(q: str = "", user: str = Depends(api_require_auth)):
    return _run(service.search, q)


@router.get(f"{API}/journal")
def api_journal(user: str = Depends(api_require_auth)):
    return _run(service.journal)


@router.post(f"{API}/merge")
def api_merge(body: MergeIn, user: str = Depends(api_require_auth)):
    return _run(service.merge, body.source_id, body.target_id, user, body.review_id)


@router.post(f"{API}/reassign")
def api_reassign(body: ReassignIn, user: str = Depends(api_require_auth)):
    return _run(service.reassign, [list(k) for k in body.keys], body.target_id, user, body.review_id)


@router.post(f"{API}/undo/{{audit_id}}")
def api_undo(audit_id: int, user: str = Depends(api_require_auth)):
    return _run(service.undo, audit_id, user)


@router.post(f"{API}/sync")
def api_sync(user: str = Depends(api_require_auth)):
    return _run(service.sync_now)


@router.post(f"{API}/applicants")
def api_applicants(file: UploadFile = File(...), user: str = Depends(api_require_auth)):
    data = file.file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        return _json({"detail": "Файл больше 10 МБ"}, 413)
    return _run(service.import_applicants, data)


@router.get(f"{API}/no-city")
def api_no_city(user: str = Depends(api_require_auth)):
    return _run(service.no_city)


@router.get(f"{API}/{{person_id}}")
def api_person(person_id: int, user: str = Depends(api_require_auth)):
    return _run(service.person_card, person_id)


@router.post(f"{API}/{{person_id}}/birthdate")
def api_birthdate(person_id: int, body: BirthdateIn, user: str = Depends(api_require_auth)):
    return _run(service.set_birthdate, person_id, body.birthdate, user, body.review_id)


@router.post(f"{API}/{{person_id}}/city")
def api_city(person_id: int, body: CityIn, user: str = Depends(api_require_auth)):
    return _run(service.set_city, person_id, body.city, user)
