"""Загрузчик результатов Дуатлона 222 из Copernico API.

В отличие от load_tri_results.py (одинаковые круги), здесь три РАЗНЫЕ
дисциплины — храним не круги, а кумулятивное время (сек от общего массового
старта) на финише каждого этапа прямо в строке participants
(run1_s/bike_s/run2_s). Время самого этапа = вычитание соседних отметок,
считается в src/duathlon222/service.py, не здесь.
"""
import argparse
import logging
import os
import time
from typing import Optional

import mysql.connector
import urllib.request
import urllib.parse
import json
import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DuathlonLoader")

STAGE_COLUMNS = ("run1_s", "bike_s", "run2_s")

_STATUS_MAP = {
    "notstarted": "active",
    "started": "active",
    "active": "active",
    "finished": "finished",
    "dnf": "dnf",
    "dns": "dnf",
    "retired": "dnf",
    "withdrawn": "dnf",
    "abandoned": "dnf",
    "disqualified": "dsq",
    "dsq": "dsq",
}
_GENDER_MAP = {"male": "M", "female": "F", "m": "M", "f": "F"}


def _normalize_status(raw: Optional[str]) -> str:
    return _STATUS_MAP.get((raw or "").strip().lower(), "active")


def _normalize_gender(raw: Optional[str]) -> str:
    return _GENDER_MAP.get((raw or "").strip().lower(), "M")


def _connect() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        database="duathlon_222",
        user=os.getenv("DB_USER", "km_analytic"),
        password=os.getenv("DB_PASSWORD"),
        charset="utf8mb4",
        autocommit=False,
    )


def _fetch_copernico(race_id: str, login: str, preset: str, event: str) -> list:
    encoded_preset = urllib.parse.quote(preset)
    encoded_event = urllib.parse.quote(event)
    url = f"https://public-api.copernico.cloud/api/races/{race_id}/preset/{login}:::{encoded_preset}/{encoded_event}"
    logger.info(f"📡 Copernico: {url}")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, list):
        return data
    return data.get("results", data.get("data", []))


def _load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    distances = cfg.get("distances", [])
    if not distances:
        raise ValueError(f"В {config_path} нет ни одной дистанции")
    return distances[0]


def _get_or_create_participant(cursor, event_id: int, p: dict, field_map: dict) -> Optional[int]:
    start_number = p.get(field_map.get("start_number", "dorsal"))
    if start_number is None:
        return None
    cursor.execute(
        "SELECT id FROM participants WHERE event_id=%s AND start_number=%s",
        (event_id, start_number),
    )
    row = cursor.fetchone()
    status = _normalize_status(p.get(field_map.get("status", "status")))
    if row:
        pid = row[0]
        cursor.execute("UPDATE participants SET status=%s WHERE id=%s", (status, pid))
        return pid
    gender = _normalize_gender(p.get(field_map.get("gender", "gender")))
    cursor.execute(
        """INSERT INTO participants (event_id, start_number, surname, name, gender, status)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (
            event_id,
            start_number,
            p.get(field_map.get("surname", "surname"), ""),
            p.get(field_map.get("name", "name"), ""),
            gender,
            status,
        ),
    )
    return cursor.lastrowid


def _process_stages(cursor, participant_id: int, runner: dict, stage_fields: dict) -> int:
    """Обновляет run1_s/bike_s/run2_s из кумулятивных мс Copernico (-> целые секунды)."""
    updates = {}
    for stage_code, field_name in stage_fields.items():
        col = f"{stage_code}_s"
        if col not in STAGE_COLUMNS:
            continue
        val_ms = runner.get(field_name)
        if val_ms is not None and val_ms != 0:
            updates[col] = int(val_ms // 1000)
    if not updates:
        return 0
    set_clause = ", ".join(f"{col}=%s" for col in updates)
    cursor.execute(
        f"UPDATE participants SET {set_clause} WHERE id=%s",
        (*updates.values(), participant_id),
    )
    return 1


def _load_preset(preset_name: str) -> tuple[dict, dict]:
    with open(f"config/copernico/{preset_name}.yaml", encoding="utf-8") as f:
        preset_cfg = yaml.safe_load(f)
    return preset_cfg.get("fields", {}), preset_cfg.get("stage_fields", {})


def _run_once(config_path: str) -> int:
    dist_cfg = _load_config(config_path)
    event_id = dist_cfg["db_event_id"]
    cop = dist_cfg["copernico"]
    field_map, stage_fields = _load_preset(cop["preset"])

    runners = _fetch_copernico(cop["race_id"], cop["login"], cop["preset"], cop["event"])
    logger.info(f"✅ Получено {len(runners)} участников")

    conn = _connect()
    cursor = conn.cursor()
    touched = 0
    changed = 0
    for runner in runners:
        pid = _get_or_create_participant(cursor, event_id, runner, field_map)
        if pid is None:
            continue
        touched += 1
        changed += _process_stages(cursor, pid, runner, stage_fields)
    conn.commit()
    cursor.close()
    conn.close()
    logger.info(f"Участников: {touched}, обновлений этапов: {changed}")
    return touched


def run(config_path: str, interval: int):
    dist_cfg = _load_config(config_path)
    event_id = dist_cfg["db_event_id"]
    logger.info(f"▶ Старт загрузчика: event_id={event_id}, interval={interval}s")
    while True:
        try:
            _run_once(config_path)
        except Exception as e:
            logger.error(f"❌ Ошибка цикла: {e}")
        time.sleep(interval)


def resync(config_path: str) -> int:
    """Сбрасывает run1_s/bike_s/run2_s всех участников события и заново
    заполняет их из Copernico — исправляет накопленные ошибки хронометража."""
    dist_cfg = _load_config(config_path)
    event_id = dist_cfg["db_event_id"]

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE participants SET {', '.join(f'{c}=NULL' for c in STAGE_COLUMNS)} WHERE event_id=%s",
        (event_id,),
    )
    logger.info(f"🗑 Сброшено этапов у {cursor.rowcount} участников")
    conn.commit()
    cursor.close()
    conn.close()

    return _run_once(config_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--init", action="store_true", help="Однократная загрузка участников и выход")
    parser.add_argument("--resync", action="store_true", help="Сбросить этапы и перезагрузить из Copernico")
    args = parser.parse_args()
    if args.resync:
        resync(args.config)
    elif args.init:
        _run_once(args.config)
    else:
        run(args.config, args.interval)
