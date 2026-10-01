"""
Webhook endpoint для приёма регистраций из Tilda.
POST /webhook/tilda/{token}

Тело запроса сначала пишется в спул на диск (var/webhook_spool), потом
обрабатывается; при успехе файл удаляется. Если обработка упала (27.09.2026
пул соединений был исчерпан — три заявки ушли в «db error» с HTTP 200 и
потерялись), файл остаётся, и лидер-воркер повторяет его каждые 5 минут
(replay_spool, app.py). Tilda видит 200: заявка принята и не потеряется.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from src.config import settings
from src.analytics.db_connection_optimized import get_pooled_connection
from src.analytics.db_results import recompute_duplicate_flag
from src.krasmarafon.services.tilda_webhook import transform_tilda_payload

router = APIRouter(prefix="/webhook", tags=["webhook"])
_log = logging.getLogger(__name__)

KRS = ZoneInfo("Asia/Krasnoyarsk")
SPOOL_DIR = Path(os.environ.get("WEBHOOK_SPOOL_DIR") or Path(__file__).resolve().parents[3] / "var" / "webhook_spool")
REPLAY_MIN_AGE_S = 120          # свежий файл может ещё обрабатываться живым запросом


@router.post("/tilda/{token}")
async def tilda_webhook(token: str, request: Request):
    if not settings.TILDA_WEBHOOK_SECRET or token != settings.TILDA_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid token")

    content_type = request.headers.get("content-type", "")
    raw = await request.body()
    received_at = datetime.now(KRS).replace(tzinfo=None)
    try:
        spool_file = spool_save(raw, content_type, received_at)
    except Exception as e:
        _log.error(f"tilda_webhook: не удалось сохранить в спул: {e}", exc_info=True)
        spool_file = None

    try:
        if "multipart/form-data" in content_type:
            body = dict(await request.form())
        else:
            body = parse_body(raw, content_type)
    except Exception:
        _log.warning("tilda_webhook: не удалось распарсить тело запроса")
        return JSONResponse({"ok": False, "error": "bad body"})
    if spool_file:
        _spool_add_body(spool_file, body)

    if body.get("test"):                    # проверочный запрос Tilda при подключении вебхука
        if spool_file:
            spool_file.unlink(missing_ok=True)
        return JSONResponse({"ok": True})

    try:
        data = process_tilda_body(body, received_at)
    except BadPayload as e:
        _log.error(f"tilda_webhook: ошибка трансформации: {e}", exc_info=True)
        if spool_file:
            _spool_fail(spool_file)
        return JSONResponse({"ok": False, "error": "transform failed"})
    except Exception as e:
        where = "в спуле, повторим" if spool_file else "спула нет"
        _log.error(f"tilda_webhook: ошибка обработки ({where}): {e}", exc_info=True)
        if spool_file:
            return JSONResponse({"ok": False, "error": "queued for retry"})
        return JSONResponse({"ok": False, "error": "db error"}, status_code=500)
    if spool_file:
        spool_file.unlink(missing_ok=True)
    _log.info(f"tilda_webhook: lead вставлен — {data.get('surname')} {data.get('name')}, "
              f"event={data.get('event_name')} {data.get('event_year')}")
    return JSONResponse({"ok": True})


def parse_body(raw: bytes, content_type: str) -> dict:
    """JSON или application/x-www-form-urlencoded; неизвестный тип — сначала JSON."""
    if "application/x-www-form-urlencoded" not in content_type:
        try:
            return json.loads(raw)
        except Exception:
            if "application/json" in content_type:
                raise
    parsed = parse_qs(raw.decode("utf-8", errors="replace"))
    return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}


class BadPayload(Exception):
    """Тело не превращается в заявку — повтор не поможет (в отличие от ошибок БД)."""


def process_tilda_body(body: dict, received_at: datetime) -> dict:
    """Заявка из тела вебхука -> leads. Повтор безопасен: уже записанную заявку
    (тот же transaction_id/order_id и ФИ на том же событии) не дублирует."""
    try:
        data = transform_tilda_payload(body, first_race_date, received_at.date())
    except Exception as e:
        raise BadPayload(str(e)) from e
    data["created_at"] = received_at
    if not _lead_exists(data):
        _insert_lead(data)
    return data


# ---------------------------------------------------------------- спул

def spool_save(raw: bytes, content_type: str, received_at: datetime) -> Path:
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    path = SPOOL_DIR / f"{received_at:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"received_at": received_at.isoformat(), "content_type": content_type,
                               "raw": raw.decode("utf-8", errors="replace")}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)                       # атомарно: повтор не увидит полузаписанный файл
    return path


def _spool_add_body(path: Path, body: dict) -> None:
    """Разобранное тело — для повтора multipart (сырой multipart без Starlette не разобрать)."""
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["body"] = {k: v for k, v in body.items() if isinstance(v, (str, int, float, list))}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        _log.warning(f"tilda_webhook: не удалось дописать тело в спул {path.name}: {e}")


def _spool_fail(path: Path) -> None:
    """Неразбираемое тело — в failed/ (разбор вручную), чтобы не повторять каждые 5 минут."""
    failed = SPOOL_DIR / "failed"
    failed.mkdir(parents=True, exist_ok=True)
    path.replace(failed / path.name)


def replay_spool(min_age_s: int = REPLAY_MIN_AGE_S) -> dict:
    """Повторить необработанные заявки из спула (лидер-воркер, каждые 5 минут)."""
    done = {"replayed": 0, "failed": 0, "oldest_failed_age_s": 0}
    if not SPOOL_DIR.exists():
        return done
    now = time.time()
    for path in sorted(SPOOL_DIR.glob("*.json")):
        age = now - path.stat().st_mtime
        if age < min_age_s:
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
            body = rec.get("body") or parse_body(rec["raw"].encode("utf-8"), rec.get("content_type", ""))
            data = process_tilda_body(body, datetime.fromisoformat(rec["received_at"]))
            path.unlink(missing_ok=True)
            done["replayed"] += 1
            _log.info(f"tilda_webhook: повтор из спула {path.name} — {data.get('surname')} {data.get('name')}, "
                      f"event={data.get('event_name')} {data.get('event_year')}")
        except BadPayload as e:
            _spool_fail(path)
            done["bad"] = done.get("bad", 0) + 1
            _log.error(f"tilda_webhook: {path.name} не превращается в заявку — в failed/: {e}")
        except Exception as e:
            done["failed"] += 1
            done["oldest_failed_age_s"] = max(done["oldest_failed_age_s"], int(age))
            _log.error(f"tilda_webhook: повтор {path.name} не удался: {e}")
    return done


def _lead_exists(data: dict) -> bool:
    """Та же заявка уже в БД: тот же transaction_id или order_id и те же ФИ на том же событии."""
    tid, oid = data.get("transaction_id") or "", data.get("order_id")
    if not tid and oid is None:
        return False
    conn = get_pooled_connection()
    if not conn:
        raise RuntimeError("No DB connection available")
    try:
        cur = conn.cursor()
        cur.execute("""SELECT 1 FROM leads WHERE surname = %s AND name = %s AND event_name = %s AND event_year = %s
                       AND ((%s <> '' AND transaction_id = %s) OR (%s IS NOT NULL AND order_id = %s)) LIMIT 1""",
                    (data["surname"], data["name"], data["event_name"], data["event_year"], tid, tid, oid, oid))
        found = cur.fetchone() is not None
        cur.close()
        return found
    finally:
        conn.close()


def first_race_date(event_name: str, event_year: int):
    """Дата первого дня старта (MIN event_date по дистанциям) или None."""
    conn = get_pooled_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT MIN(event_date) FROM events WHERE event_name = %s AND event_year = %s",
                    (event_name, int(event_year)))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    finally:
        conn.close()


def _insert_lead(data: dict):
    data = {**data, "created_at": data.get("created_at") or datetime.now(KRS).replace(tzinfo=None)}
    conn = get_pooled_connection()
    if not conn:
        raise RuntimeError("No DB connection available")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO leads (
                surname, name, sex, city, club, birthday,
                email, phone,
                event_name, event_distance, event_year,
                products, payment_system, transaction_id, order_id,
                promocode, discount, amount,
                is_name_suspicious, client_id, event_id,
                is_duplicate, status, is_new, is_new_event, created_at
            ) VALUES (
                %(surname)s, %(name)s, %(sex)s, %(city)s, %(club)s, %(birthday)s,
                %(email)s, %(phone)s,
                %(event_name)s, %(event_distance)s, %(event_year)s,
                %(products)s, %(payment_system)s, %(transaction_id)s, %(order_id)s,
                %(promocode)s, %(discount)s, %(amount)s,
                %(is_name_suspicious)s, %(client_id)s, %(event_id)s,
                %(is_duplicate)s, %(status)s, %(is_new)s, %(is_new_event)s, %(created_at)s
            )
            """,
            data,
        )
        conn.commit()
        new_id = cur.lastrowid

        # client_id/event_id резолвлены триггером trg_leads_before_insert на
        # BEFORE INSERT — читаем их обратно уже закоммиченными и пересчитываем
        # is_duplicate для всей группы (включая саму первую заявку, если она
        # уже существовала).
        cur.execute("SELECT client_id, event_id FROM leads WHERE id = %s", (new_id,))
        row = cur.fetchone()
        cur.close()
        if row:
            recompute_duplicate_flag(client_id=row[0], event_id=row[1])
    finally:
        conn.close()
