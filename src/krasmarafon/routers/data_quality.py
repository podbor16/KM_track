"""
/admin → «Качество данных»: находки проверок привязки к карточкам и действия по ним.

Находки считаются на лету (src/analytics/data_quality.py) в пуле потоков — проверка всей
базы ~3 с. Решённые («разные люди», «оставить») хранятся в dq_decisions и не показываются.
Каждое действие возвращает action_id — по нему его можно отменить (журнал dq_actions).
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from src.analytics import data_quality as dq
from src.analytics import dq_cases
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


class FixFioBody(BaseModel):
    result_id: int
    surname: str
    name: str
    key: str = ""


class EditBody(BaseModel):
    table: Literal["results", "leads", "clients"]
    id: int
    fields: dict[str, str]
    key: str = ""


class MoveBody(BaseModel):
    table: Literal["results", "leads"] = "results"
    row_id: int
    to_client_id: Optional[int] = None
    new_card: Optional[dict[str, str]] = None
    key: str = ""


class UndoBody(BaseModel):
    action_id: int


class DismissBody(BaseModel):
    key: str
    decision: Literal["different_people", "keep"]
    note: str = ""


class AnswerBody(BaseModel):
    question_id: str
    answer_id: str
    inputs: dict[str, str] = {}


class PostponeBody(BaseModel):
    reason: str = ""


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


@router.get("/api/admin/data-quality/cases")
async def list_cases(status: Literal["open", "postponed"] = "open", event_id: Optional[int] = None,
                     user: str = Depends(api_require_auth)) -> dict:
    return {"cases": await run_in_threadpool(_with_conn, dq_cases.list_cases, status, event_id)}


@router.get("/api/admin/data-quality/cases/{key}")
async def get_case(key: str, user: str = Depends(api_require_auth)) -> dict:
    case = await run_in_threadpool(_with_conn, dq_cases.get_case, key)
    if not case:
        raise HTTPException(status_code=404, detail="Дело закрыто или изменилось — обновите список")
    return case


@router.post("/api/admin/data-quality/cases/{key}/answer")
async def answer(key: str, body: AnswerBody, user: str = Depends(api_require_auth)) -> dict:
    try:
        return await run_in_threadpool(_with_conn, dq_cases.apply_answer, key, body.question_id, body.answer_id,
                                       body.inputs, user)
    except dq_cases.StaleQuestion as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/api/admin/data-quality/cases/{key}/postpone")
async def postpone(key: str, body: PostponeBody, user: str = Depends(api_require_auth)) -> dict:
    try:
        ids = await run_in_threadpool(_with_conn, dq_cases.postpone_case, key, body.reason, user)
    except dq_cases.StaleQuestion as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "action_ids": ids}


@router.get("/api/admin/data-quality/person/{client_id}")
async def person(client_id: int, user: str = Depends(api_require_auth)) -> dict:
    case = await run_in_threadpool(_with_conn, dq_cases.case_for_card, client_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Нет карточки #{client_id}")
    return case


@router.post("/api/admin/data-quality/merge")
async def merge(body: MergeBody, user: str = Depends(api_require_auth)) -> dict:
    surv, action_id = await run_in_threadpool(_with_conn, dq.merge_cards, body.client_ids, body.surname, body.name,
                                              body.birthday, user, body.key)
    return {"ok": True, "client_id": surv, "action_id": action_id}


@router.post("/api/admin/data-quality/delete-result")
async def delete_result(body: DeleteResultBody, user: str = Depends(api_require_auth)) -> dict:
    action_id = await run_in_threadpool(_with_conn, dq.delete_result, body.result_id, user, body.key)
    return {"ok": True, "action_id": action_id}


@router.post("/api/admin/data-quality/fix-fio")
async def fix_fio(body: FixFioBody, user: str = Depends(api_require_auth)) -> dict:
    cid, action_id = await run_in_threadpool(_with_conn, dq.fix_fio, body.result_id, body.surname, body.name,
                                             user, body.key)
    return {"ok": True, "client_id": cid, "action_id": action_id}


@router.post("/api/admin/data-quality/edit")
async def edit(body: EditBody, user: str = Depends(api_require_auth)) -> dict:
    cid, action_id = await run_in_threadpool(_with_conn, dq.edit_record, body.table, body.id, body.fields, user, body.key)
    return {"ok": True, "client_id": cid, "action_id": action_id}


@router.get("/api/admin/data-quality/cards")
async def cards(q: str = "", user: str = Depends(api_require_auth)) -> dict:
    return {"cards": await run_in_threadpool(_with_conn, dq.search_cards, q)}


@router.post("/api/admin/data-quality/move")
async def move(body: MoveBody, user: str = Depends(api_require_auth)) -> dict:
    if (body.to_client_id is None) == (body.new_card is None):
        raise HTTPException(status_code=422, detail="нужна либо карточка, либо данные новой карточки")
    cid, action_id = await run_in_threadpool(
        _with_conn, lambda conn: dq.move_row(conn, body.table, body.row_id, user, body.key, body.to_client_id, body.new_card))
    return {"ok": True, "client_id": cid, "action_id": action_id}


@router.post("/api/admin/data-quality/dismiss")
async def dismiss(body: DismissBody, user: str = Depends(api_require_auth)) -> dict:
    action_id = await run_in_threadpool(_with_conn, dq.dismiss, body.key, body.decision, body.note, user)
    return {"ok": True, "action_id": action_id}


@router.post("/api/admin/data-quality/apply-auto")
async def apply_auto(user: str = Depends(api_require_auth)) -> dict:
    return await run_in_threadpool(_with_conn, dq.apply_auto, user)


@router.get("/api/admin/data-quality/actions")
async def actions(limit: int = 50, user: str = Depends(api_require_auth)) -> dict:
    return {"actions": await run_in_threadpool(_with_conn, dq.recent_actions, min(max(limit, 1), 500))}


@router.post("/api/admin/data-quality/undo")
async def undo(body: UndoBody, user: str = Depends(api_require_auth)) -> dict:
    undo_id = await run_in_threadpool(_with_conn, dq.undo_action, body.action_id, user)
    return {"ok": True, "undo_id": undo_id}
