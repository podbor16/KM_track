"""
/admin → «Стартовый список» → «Присвоить номера» (правила — src/analytics/bibs.py).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from src.analytics import bibs
from src.analytics.db_connection_optimized import get_pooled_connection
from src.core.auth import api_require_auth

router = APIRouter(tags=["Admin: стартовые номера"])


class RangeIn(BaseModel):
    distance: str
    key: str = ""
    start: Optional[int] = None
    end: Optional[int] = None


class BibsBody(BaseModel):
    event_name: str
    event_year: int
    ranges: list[RangeIn]


def _ranges(body: BibsBody) -> dict:
    return {(r.distance, r.key): (r.start, r.end) for r in body.ranges}


def _with_conn(fn, *args):
    conn = get_pooled_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Нет соединения с БД")
    try:
        return fn(conn, *args)
    finally:
        conn.close()


@router.get("/api/admin/bibs")
async def bibs_overview(event_name: str = Query(...), event_year: int = Query(...),
                        user: str = Depends(api_require_auth)) -> dict:
    return await run_in_threadpool(_with_conn, bibs.overview, event_name, event_year)


@router.post("/api/admin/bibs/preview")
async def bibs_preview(body: BibsBody, user: str = Depends(api_require_auth)) -> dict:
    return await run_in_threadpool(_with_conn, bibs.preview, body.event_name, body.event_year, _ranges(body))


@router.post("/api/admin/bibs/assign")
async def bibs_assign(body: BibsBody, user: str = Depends(api_require_auth)) -> dict:
    result = await run_in_threadpool(_with_conn, bibs.assign, body.event_name, body.event_year, _ranges(body), user)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail={"message": "Номера не присвоены — исправьте ошибки", **result})
    return result
