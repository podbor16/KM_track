"""
Webhook endpoint для приёма регистраций из Tilda.
POST /webhook/tilda/{token}
"""

import json
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from src.config import settings
from src.analytics.db_connection_optimized import get_pooled_connection
from src.tracker.services.tilda_webhook import transform_tilda_payload

router = APIRouter(prefix="/webhook", tags=["webhook"])
_log = logging.getLogger("km_track.webhook")


@router.post("/tilda/{token}")
async def tilda_webhook(token: str, request: Request):
    if not settings.TILDA_WEBHOOK_SECRET or token != settings.TILDA_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid token")

    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            body = await request.json()
        elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            body = dict(form)
        else:
            # попробуем JSON, потом form
            raw = await request.body()
            try:
                body = json.loads(raw)
            except Exception:
                from urllib.parse import parse_qs
                parsed = parse_qs(raw.decode("utf-8", errors="replace"))
                body = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
    except Exception:
        _log.warning("tilda_webhook: не удалось распарсить тело запроса")
        return JSONResponse({"ok": False, "error": "bad body"})

    _log.info(f"tilda_webhook: body keys={list(body.keys())}, payment_len={len(str(body.get('payment',''))[:100])}")

    try:
        data = transform_tilda_payload(body)
    except Exception as e:
        _log.error(f"tilda_webhook: ошибка трансформации: {e}", exc_info=True)
        return JSONResponse({"ok": False, "error": "transform failed"})

    _log.info(f"tilda_webhook: data event_year={data.get('event_year')!r} event_name={data.get('event_name')!r}")

    try:
        _insert_lead(data)
        _log.info(
            f"tilda_webhook: lead вставлен — {data.get('surname')} {data.get('name')}, "
            f"event={data.get('event_name')} {data.get('event_year')}"
        )
    except Exception as e:
        _log.error(f"tilda_webhook: ошибка INSERT: {e}", exc_info=True)
        return JSONResponse({"ok": False, "error": "db error"})

    return JSONResponse({"ok": True})


def _insert_lead(data: dict):
    conn = get_pooled_connection()
    if not conn:
        raise RuntimeError("No DB connection available")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO leads (
                surname, name, sex, city, birthday,
                email, phone,
                event_name, event_distance, event_year,
                products, payment_system, transaction_id, order_id,
                promocode, discount, amount,
                is_name_suspicious, client_id, event_id,
                is_duplicate, status, is_new, is_new_event
            ) VALUES (
                %(surname)s, %(name)s, %(sex)s, %(city)s, %(birthday)s,
                %(email)s, %(phone)s,
                %(event_name)s, %(event_distance)s, %(event_year)s,
                %(products)s, %(payment_system)s, %(transaction_id)s, %(order_id)s,
                %(promocode)s, %(discount)s, %(amount)s,
                %(is_name_suspicious)s, %(client_id)s, %(event_id)s,
                %(is_duplicate)s, %(status)s, %(is_new)s, %(is_new_event)s
            )
            """,
            data,
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
