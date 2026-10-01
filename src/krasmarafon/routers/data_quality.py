"""
/admin → «Качество данных»: находки проверок привязки к карточкам и действия по ним.

Находки считаются на лету (src/analytics/data_quality.py) в пуле потоков — проверка всей
базы ~3 с. Решённые («разные люди», «оставить») хранятся в dq_decisions и не показываются.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from src.analytics import data_quality as dq
from src.analytics.db_connection_optimized import get_pooled_connection
from src.core.auth import api_require_auth

router = APIRouter(tags=["Admin: качество данных"])

ORDER = {"high": 0, "medium": 1, "low": 2}


class MergeBody(BaseModel):
    client_ids: list[int]
    surname: str
    name: str
    birthday: str
    key: str = ""


class DeleteResultBody(BaseModel):
    result_id: int
    key: str = ""


class DismissBody(BaseModel):
    key: str
    decision: Literal["different_people", "keep"]
    note: str = ""


def _with_conn(fn, *args):
    conn = get_pooled_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Нет соединения с БД")
    try:
        return fn(conn, *args)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


def _list(conn, event_id):
    findings, data = dq.pending_findings(conn, {event_id} if event_id else None)
    findings.sort(key=lambda f: (ORDER[f.severity], f.code, f.message))
    return {"findings": [dq.finding_view(f, data) for f in findings]}


@router.get("/api/admin/data-quality")
async def list_findings(event_id: Optional[int] = None, user: str = Depends(api_require_auth)) -> dict:
    return await run_in_threadpool(_with_conn, _list, event_id)


@router.post("/api/admin/data-quality/merge")
async def merge(body: MergeBody, user: str = Depends(api_require_auth)) -> dict:
    surv = await run_in_threadpool(_with_conn, dq.merge_cards, body.client_ids, body.surname, body.name,
                                   body.birthday, user, body.key)
    return {"ok": True, "client_id": surv}


@router.post("/api/admin/data-quality/delete-result")
async def delete_result(body: DeleteResultBody, user: str = Depends(api_require_auth)) -> dict:
    await run_in_threadpool(_with_conn, dq.delete_result, body.result_id, user, body.key)
    return {"ok": True}


@router.post("/api/admin/data-quality/dismiss")
async def dismiss(body: DismissBody, user: str = Depends(api_require_auth)) -> dict:
    await run_in_threadpool(_with_conn, dq.dismiss, body.key, body.decision, body.note, user)
    return {"ok": True}


@router.post("/api/admin/data-quality/apply-auto")
async def apply_auto(user: str = Depends(api_require_auth)) -> dict:
    return await run_in_threadpool(_with_conn, dq.apply_auto, user)
