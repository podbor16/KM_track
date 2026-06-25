"""Загрузчик результатов суточной велогонки Triatleta из Copernico API."""
import argparse
import logging
import os
import time
from pathlib import Path
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
logger = logging.getLogger("TriLoader")

LAP_DISTANCE_KM = 4.040


def _connect() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        database="triatleta_24h",
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


def _load_config(config_path: str, distance: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for dist in cfg.get("distances", []):
        if dist.get("distance") == distance:
            return dist
    raise ValueError(f"Дистанция '{distance}' не найдена в {config_path}")


_GENDER_NORM = {"male": "Мужчина", "female": "Женщина", "m": "Мужчина", "f": "Женщина"}


def _get_or_create_participant(cursor, event_id: int, p: dict, field_map: dict) -> Optional[int]:
    start_number = p.get(field_map.get("start_number", "dorsal"))
    if start_number is None:
        return None
    cursor.execute(
        "SELECT id FROM participants WHERE event_id=%s AND start_number=%s",
        (event_id, start_number),
    )
    row = cursor.fetchone()
    if row:
        return row[0]
    raw_gender = p.get(field_map.get("gender", "gender"), "") or ""
    gender = _GENDER_NORM.get(raw_gender.lower(), raw_gender)
    team_name = (p.get(field_map.get("team_name", "team")) or
                 p.get("club") or "")
    cursor.execute(
        """INSERT INTO participants
           (event_id, start_number, surname, name, birthdate, gender, status, category, team_name)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            event_id,
            start_number,
            p.get(field_map.get("surname", "surname"), ""),
            p.get(field_map.get("name", "name"), ""),
            p.get(field_map.get("birthdate", "birthdate")),
            gender,
            p.get(field_map.get("status", "status"), ""),
            p.get(field_map.get("category", "category"), ""),
            team_name,
        ),
    )
    return cursor.lastrowid


def _process_laps(cursor, participant_id: int, event_id: int, runner: dict, lap_count: int, pattern: str) -> int:
    inserted = 0
    prev_ms = 0
    for n in range(1, lap_count + 1):
        field = pattern.replace("{n}", str(n))
        cumulative_ms = runner.get(field)
        if cumulative_ms is None:
            break
        lap_ms = cumulative_ms - prev_ms
        cursor.execute(
            """INSERT IGNORE INTO laps (participant_id, event_id, lap_number, cumulative_ms, lap_ms)
               VALUES (%s,%s,%s,%s,%s)""",
            (participant_id, event_id, n, cumulative_ms, lap_ms),
        )
        if cursor.rowcount > 0:
            inserted += 1
        prev_ms = cumulative_ms
    return inserted


def _run_once(config_path: str) -> int:
    dist_cfg = _load_config(config_path, "24h")
    event_id = dist_cfg["db_event_id"]
    cop = dist_cfg["copernico"]
    race_id = cop["race_id"]
    login = cop["login"]
    preset = cop["preset"]
    event = cop["event"]

    with open(f"config/copernico/{preset}.yaml", encoding="utf-8") as f:
        preset_cfg = yaml.safe_load(f)
    field_map = preset_cfg.get("fields", {})
    lap_fields = preset_cfg.get("lap_fields", {})
    lap_count = lap_fields.get("count", 150)
    lap_pattern = lap_fields.get("pattern", "times.official_{n}kr")

    runners = _fetch_copernico(race_id, login, preset, event)
    logger.info(f"✅ Получено {len(runners)} участников")

    conn = _connect()
    cursor = conn.cursor()
    inserted_participants = 0
    for runner in runners:
        pid = _get_or_create_participant(cursor, event_id, runner, field_map)
        if pid is not None:
            inserted_participants += 1
        if pid is None:
            continue
        _process_laps(cursor, pid, event_id, runner, lap_count, lap_pattern)
    conn.commit()
    cursor.close()
    conn.close()
    logger.info(f"Вставлено: {inserted_participants} участников")
    return inserted_participants


def run(config_path: str, interval: int):
    dist_cfg = _load_config(config_path, "24h")
    event_id = dist_cfg["db_event_id"]
    cop = dist_cfg["copernico"]
    race_id = cop["race_id"]
    login = cop["login"]
    preset = cop["preset"]
    event = cop["event"]

    with open(f"config/copernico/{preset}.yaml", encoding="utf-8") as f:
        preset_cfg = yaml.safe_load(f)
    field_map = preset_cfg.get("fields", {})
    lap_fields = preset_cfg.get("lap_fields", {})
    lap_count = lap_fields.get("count", 150)
    lap_pattern = lap_fields.get("pattern", "times.official_{n}kr")

    logger.info(f"▶ Старт загрузчика: event_id={event_id}, interval={interval}s")

    while True:
        try:
            runners = _fetch_copernico(race_id, login, preset, event)
            logger.info(f"✅ Получено {len(runners)} участников")

            conn = _connect()
            cursor = conn.cursor()
            total_inserted = 0
            for runner in runners:
                pid = _get_or_create_participant(cursor, event_id, runner, field_map)
                if pid is None:
                    continue
                total_inserted += _process_laps(cursor, pid, event_id, runner, lap_count, lap_pattern)
            conn.commit()
            cursor.close()
            conn.close()
            if total_inserted:
                logger.info(f"💾 Добавлено новых кругов: {total_inserted}")
            else:
                logger.debug("⏸ Новых кругов нет")
        except Exception as e:
            logger.error(f"❌ Ошибка цикла: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--init", action="store_true", help="Однократная загрузка участников и выход")
    args = parser.parse_args()
    if args.init:
        _run_once(args.config)
    else:
        run(args.config, args.interval)
