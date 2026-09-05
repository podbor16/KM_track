"""Загрузчик результатов Дуатлона 222 из Copernico API.

Три уровня данных: (1) финиш каждого из 3 этапов — кумулятивное время (сек
от общего массового старта) прямо в строке participants (run1_s/bike_s/
run2_s); (2) круги ВНУТРИ каждого этапа — таблица checkpoints
(participant_id, stage, lap_number, cumulative_s), нужна для «последней
пройденной отметки» и прогноза финиша текущего этапа; (3) транзитные зоны
Т1/Т2 (t1_s/t2_s) — ДЛИТЕЛЬНОСТЬ (не кумулятивная отметка), считаются в
общем времени гонки, но вычитаются из времени соседних этапов. Само
вычитание/сборка — в src/duathlon222/service.py, не здесь.
"""
import argparse
import gzip
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
TRANSITION_COLUMNS = ("t1_s", "t2_s", "bike_start_s", "run2_start_s")

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
        raw = resp.read()
        # CDN перед Copernico иногда отдаёт тело gzip-сжатым даже без нашего
        # запроса на это (Content-Encoding не был запрошен) — сырые байты
        # тогда начинаются с magic-number \x1f\x8b, и .decode("utf-8") падает
        # с "invalid start byte" (найдено в проде 2026-09-05, реальная гонка).
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8"))
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


def _process_stages_and_transitions(
    cursor, participant_id: int, runner: dict, stage_fields: dict, transition_fields: dict,
) -> int:
    """Обновляет run1_s/bike_s/run2_s (финиш этапа целиком, кумулятивные мс
    Copernico -> целые секунды) И t1_s/t2_s/bike_start_s/run2_start_s. В
    отличие от run1_s/bike_s/run2_s, Т1/Т2 Copernico не отдаёт готовой
    ДЛИТЕЛЬНОСТЬЮ — только кумулятивные отметки старта транзита
    (transition_fields), поэтому длительность считается здесь же: старт
    транзита минус финиш ПРЕДЫДУЩЕГО этапа (тот же raw-словарь runner, оба
    поля читаются один раз за вызов). Поле пишется NULL, если Copernico
    сейчас его не отдаёт (не просто пропускается) — иначе ранее ошибочно
    записанное и потом самой Copernico отозванное значение осталось бы в БД
    навсегда (тот же класс бага, что уже чинили для промежуточных кругов в
    _process_stage_laps — найдено пользователем 2026-09-05, Мерзликин Роман
    ошибочно продолжал считаться финишировавшим Вело)."""
    stage_ms = {code: runner.get(field) for code, field in stage_fields.items()}

    updates = {}
    for stage_code, val_ms in stage_ms.items():
        col = f"{stage_code}_s"
        if col in STAGE_COLUMNS:
            updates[col] = int(val_ms // 1000) if (val_ms is not None and val_ms != 0) else None

    t1_start_ms = runner.get(transition_fields.get("t1_start", ""))
    updates["t1_s"] = (
        int((t1_start_ms - stage_ms["run1"]) // 1000) if (t1_start_ms and stage_ms.get("run1")) else None
    )
    # Сырое значение (bike0) отдельной колонкой — точный момент входа на
    # Вело, НЕ реконструкция run1_s+t1_s (та теряет до 1-2с из-за
    # раздельного округления каждого до целых секунд, см. миграцию 004).
    updates["bike_start_s"] = int(t1_start_ms // 1000) if t1_start_ms else None

    t2_start_ms = runner.get(transition_fields.get("t2_start", ""))
    updates["t2_s"] = (
        int((t2_start_ms - stage_ms["bike"]) // 1000) if (t2_start_ms and stage_ms.get("bike")) else None
    )
    updates["run2_start_s"] = int(t2_start_ms // 1000) if t2_start_ms else None

    set_clause = ", ".join(f"{col}=%s" for col in updates)
    cursor.execute(
        f"UPDATE participants SET {set_clause} WHERE id=%s",
        (*updates.values(), participant_id),
    )
    return 1 if cursor.rowcount else 0


def _prune_removed_participants(cursor, event_id: int, touched_pids: set) -> int:
    """Удаляет участников события, которых не было в последнем ответе
    Copernico (touched_pids) — иначе снятый/удалённый в Copernico участник
    остаётся в БД навсегда: и --init, и --resync, и обычный цикл раньше
    только вставляли/обновляли строки из ответа, но никогда не убирали те,
    что из ответа пропали (см. _get_or_create_participant). checkpoints
    участника удалятся каскадно (FK ON DELETE CASCADE, 002_checkpoints.sql).
    Пустой touched_pids ничего не удаляет — пустой/сломанный ответ Copernico
    не должен стирать весь список участников."""
    if not touched_pids:
        return 0
    placeholders = ",".join(["%s"] * len(touched_pids))
    cursor.execute(
        f"DELETE FROM participants WHERE event_id=%s AND id NOT IN ({placeholders})",
        (event_id, *touched_pids),
    )
    return cursor.rowcount


def _process_stage_laps(cursor, participant_id: int, runner: dict, stage_lap_fields: dict) -> int:
    """Обновляет таблицу checkpoints (круги внутри каждого этапа) из
    кумулятивных мс Copernico (-> целые секунды, от общего старта гонки).
    stage_lap_fields[stage] — ТОЧНЫЙ список имён полей по порядку (не
    шаблон "{n}" — реальные отметки Copernico не равномерны, см.
    config/copernico/duathlon_222_2026.yaml). Пропускает (не прерывает
    цикл на) отсутствующий круг — антенна на конкретной отметке может не
    считать чип (реальный случай на гонке 05.09.2026: отметка "1.25 km"
    пуста, а "2.5 km" уже есть у того же участника), это не значит, что
    участник не бежит и не значит, что дальнейшие отметки тоже пусты.
    Если поле пустое, но у НАС уже есть значение для этого круга — Copernico
    отозвал ранее ошибочно записанную отметку (реальный случай той же гонки:
    аномальный скачок скорости на Вело у двух участников — старое кривое
    значение осталось в БД навсегда, хотя Copernico сам его уже обнулил) —
    такие круги удаляются одним запросом на этап (не по одному на каждый
    пустой круг — большинство из них никогда не существовали)."""
    changed = 0
    for stage_code, field_names in stage_lap_fields.items():
        null_laps = []
        for n, field_name in enumerate(field_names, start=1):
            val_ms = runner.get(field_name)
            if val_ms is None or val_ms == 0:
                null_laps.append(n)
                continue
            cumulative_s = int(val_ms // 1000)
            cursor.execute(
                """INSERT INTO checkpoints (participant_id, stage, lap_number, cumulative_s)
                   VALUES (%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE cumulative_s=VALUES(cumulative_s)""",
                (participant_id, stage_code, n, cumulative_s),
            )
            if cursor.rowcount:
                changed += 1
        if null_laps:
            placeholders = ",".join(["%s"] * len(null_laps))
            cursor.execute(
                f"DELETE FROM checkpoints WHERE participant_id=%s AND stage=%s AND lap_number IN ({placeholders})",
                (participant_id, stage_code, *null_laps),
            )
            changed += cursor.rowcount
    return changed


PRESET_CONFIG_PATH = "config/copernico/duathlon_222_2026.yaml"


def _load_preset() -> tuple[dict, dict, dict, dict]:
    """Наш локальный конфиг field-маппинга — ИМЯ ФАЙЛА фиксировано и не
    связано с тем, как называется сам пресет в Copernico UI (cop['preset'] —
    отдельный идентификатор для URL API, не имя файла; для Дуатлона 222 это
    "222_2026", а локальный файл — "duathlon_222_2026.yaml")."""
    with open(PRESET_CONFIG_PATH, encoding="utf-8") as f:
        preset_cfg = yaml.safe_load(f)
    return (
        preset_cfg.get("fields", {}),
        preset_cfg.get("stage_fields", {}),
        preset_cfg.get("stage_lap_fields", {}),
        preset_cfg.get("transition_fields", {}),
    )


def _run_once(config_path: str) -> int:
    dist_cfg = _load_config(config_path)
    event_id = dist_cfg["db_event_id"]
    cop = dist_cfg["copernico"]
    field_map, stage_fields, stage_lap_fields, transition_fields = _load_preset()

    runners = _fetch_copernico(cop["race_id"], cop["login"], cop["preset"], cop["event"])
    logger.info(f"✅ Получено {len(runners)} участников")

    conn = _connect()
    cursor = conn.cursor()
    touched = 0
    changed = 0
    laps_changed = 0
    touched_pids = set()
    for runner in runners:
        pid = _get_or_create_participant(cursor, event_id, runner, field_map)
        if pid is None:
            continue
        touched += 1
        touched_pids.add(pid)
        changed += _process_stages_and_transitions(cursor, pid, runner, stage_fields, transition_fields)
        laps_changed += _process_stage_laps(cursor, pid, runner, stage_lap_fields)
    removed = _prune_removed_participants(cursor, event_id, touched_pids)
    conn.commit()
    cursor.close()
    conn.close()
    logger.info(
        f"Участников: {touched}, обновлений этапов: {changed}, "
        f"обновлений кругов: {laps_changed}, удалено: {removed}"
    )
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
    """Сбрасывает run1_s/bike_s/run2_s, t1_s/t2_s и все круги события, заново
    заполняет из Copernico — исправляет накопленные ошибки хронометража."""
    dist_cfg = _load_config(config_path)
    event_id = dist_cfg["db_event_id"]

    conn = _connect()
    cursor = conn.cursor()
    reset_columns = STAGE_COLUMNS + TRANSITION_COLUMNS
    cursor.execute(
        f"UPDATE participants SET {', '.join(f'{c}=NULL' for c in reset_columns)} WHERE event_id=%s",
        (event_id,),
    )
    logger.info(f"🗑 Сброшено этапов у {cursor.rowcount} участников")
    cursor.execute(
        "DELETE c FROM checkpoints c JOIN participants p ON p.id=c.participant_id WHERE p.event_id=%s",
        (event_id,),
    )
    logger.info(f"🗑 Удалено кругов: {cursor.rowcount}")
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
