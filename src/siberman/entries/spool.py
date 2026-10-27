"""
Спул вебхука заявок Siberman (как у Красмарафона, src/krasmarafon/routers/webhook.py): разобранное тело
пишется на диск до записи в БД; сбой БД — файл остаётся, лидер-воркер повторяет его каждые 5 минут
(app.py, _webhook_spool_replayer). Тело, которое не превращается в заявку, — в failed/ (разбор вручную).
"""
import datetime
import json
import logging
import os
import time
import uuid
from pathlib import Path

from src.siberman.entries.parser import BadEntry

_log = logging.getLogger(__name__)
SPOOL_DIR = Path(os.environ.get("SIBERMAN_SPOOL_DIR") or
                 Path(__file__).resolve().parents[3] / "var" / "webhook_spool" / "siberman")
REPLAY_MIN_AGE_S = 120


def save(body: dict, year: int, received_at: datetime.datetime) -> Path:
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    path = SPOOL_DIR / f"{received_at:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"year": year, "received_at": received_at.isoformat(), "body": body},
                              ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def done(path: Path) -> None:
    path.unlink(missing_ok=True)


def fail(path: Path) -> None:
    failed = SPOOL_DIR / "failed"
    failed.mkdir(parents=True, exist_ok=True)
    path.replace(failed / path.name)


def replay(process, min_age_s: int = REPLAY_MIN_AGE_S) -> dict:
    """process(year, body, received_at) — service.ingest."""
    out = {"replayed": 0, "failed": 0, "bad": 0, "oldest_failed_age_s": 0}
    if not SPOOL_DIR.exists():
        return out
    now = time.time()
    for path in sorted(SPOOL_DIR.glob("*.json")):
        try:
            age = now - path.stat().st_mtime
            if age < min_age_s:
                continue
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
                args = (rec["year"], rec["body"], datetime.datetime.fromisoformat(rec["received_at"]))
            except (ValueError, KeyError, TypeError) as e:
                raise BadEntry(f"битый файл спула: {type(e).__name__}: {e}") from e
            process(*args)
            done(path)
            out["replayed"] += 1
        except FileNotFoundError:
            continue
        except BadEntry as e:
            out["bad"] += 1
            _log.error(f"siberman entries: {path.name} не заявка — в failed/: {e}")
            try:
                fail(path)
            except Exception as e2:
                _log.error(f"siberman entries: не удалось перенести {path.name} в failed/: {e2}")
        except Exception as e:
            out["failed"] += 1
            out["oldest_failed_age_s"] = max(out["oldest_failed_age_s"], int(age))
            _log.error(f"siberman entries: повтор {path.name} не удался: {e}")
    return out
