#!/usr/bin/env python3
"""
Универсальный предстартовый чеклист.

Использование:
  python scripts/prerace_check.py --config config/events/vesna.yaml --distance "5 км"
  python scripts/prerace_check.py --config config/events/vesna.yaml --distance "5 км" --server http://localhost:8000
"""

import sys
import os
import argparse
import urllib.parse
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import yaml
import json
import xml.etree.ElementTree as ET
import mysql.connector
import urllib.request
import urllib.error


def connect_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        charset="utf8mb4",
        connection_timeout=10,
    )


def load_config(config_path: Path, distance: str):
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    distances = cfg.get("distances", [])
    dist_cfg = next((d for d in distances if d.get("distance") == distance), None)
    if dist_cfg is None:
        raise ValueError(f"Дистанция '{distance}' не найдена в {config_path}")
    return cfg, dist_cfg


STATUS = {"ok": 0, "warn": 0, "skip": 0, "fail": 0}
LABEL_W = 22

def _row(block, label, icon, msg):
    tag = f"[{block}] {label}"
    print(f"  {tag:<{LABEL_W}} {icon}  {msg}")
    key = icon.strip().lower()
    if key == "ok":
        STATUS["ok"] += 1
    elif key == "warn":
        STATUS["warn"] += 1
    elif key == "skip":
        STATUS["skip"] += 1
    elif key == "fail":
        STATUS["fail"] += 1


def ok(block, label, msg):   _row(block, label, "OK  ", msg)
def warn(block, label, msg): _row(block, label, "WARN", msg)
def skip(block, label, msg): _row(block, label, "SKIP", msg)
def fail(block, label, msg): _row(block, label, "FAIL", msg)


# ── Блок A: Конфиг ─────────────────────────────────────────────────────────

def check_config(cfg, dist_cfg):
    errors = []
    warnings = []

    required_top = ["start_lat", "start_lon"]
    for field in required_top:
        if cfg.get(field) is None:
            errors.append(f"нет {field}")

    required_dist = ["db_event_id", "event_date", "gpx_file", "checkpoint_distances"]
    for field in required_dist:
        if dist_cfg.get(field) is None:
            errors.append(f"нет {field}")

    cps = dist_cfg.get("checkpoints") or []
    if len(cps) < 2:
        errors.append("checkpoints: нужно >= 2 точек")

    race_id = (dist_cfg.get("copernico") or {}).get("race_id")
    if race_id is None:
        warnings.append("copernico.race_id не задан (норм до регистрации в Copernico)")

    if errors:
        fail("A", "Конфиг", "; ".join(errors))
    else:
        ok("A", "Конфиг", "OK")
    for w in warnings:
        warn("A", "Конфиг", w)


# ── Блок B: Файлы ───────────────────────────────────────────────────────────

def check_files(dist_cfg):
    gpx_rel = dist_cfg.get("gpx_file")
    if not gpx_rel:
        fail("B", "Файлы", "gpx_file не задан")
        return

    gpx_path = project_root / gpx_rel
    if not gpx_path.exists():
        fail("B", "Файлы", f"GPX не найден: {gpx_path}")
        return

    try:
        ET.parse(gpx_path)
        ok("B", "Файлы", f"GPX валиден ({gpx_path.name})")
    except ET.ParseError as e:
        fail("B", "Файлы", f"GPX не парсится: {e}")


# ── Блок C: База данных ─────────────────────────────────────────────────────

def check_db(cfg, dist_cfg):
    db_event_id = dist_cfg.get("db_event_id")
    if db_event_id is None:
        fail("C", "БД", "db_event_id не задан, пропуск")
        return

    try:
        conn = connect_db()
    except Exception as e:
        fail("C", "БД", f"Подключение: {e}")
        return

    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT id, event_name, event_distance, checkpoint_distances FROM events WHERE id=%s", (db_event_id,))
    row = cur.fetchone()
    if row is None:
        fail("C", "БД", f"events.id={db_event_id} не найден")
        cur.close(); conn.close()
        return

    # checkpoint_distances
    cfg_cp = dist_cfg.get("checkpoint_distances") or []
    db_cp_raw = row.get("checkpoint_distances") or "[]"
    if isinstance(db_cp_raw, str):
        try:
            db_cp = json.loads(db_cp_raw)
        except Exception:
            db_cp = []
    else:
        db_cp = db_cp_raw

    cp_match = sorted(str(x) for x in cfg_cp) == sorted(str(x) for x in db_cp)
    cp_str = "/".join(str(x) for x in sorted(cfg_cp))
    if cp_match:
        ok("C", "БД", f"id={db_event_id}, КТ {cp_str} совпадают")
    else:
        db_str = "/".join(str(x) for x in sorted(db_cp))
        warn("C", "БД", f"КТ в конфиге [{cp_str}] != БД [{db_str}]")

    cur.close()
    conn.close()


# ── Блок D: Участники ───────────────────────────────────────────────────────

def check_participants(dist_cfg):
    db_event_id = dist_cfg.get("db_event_id")
    if db_event_id is None:
        skip("D", "Участники", "db_event_id не задан")
        return

    try:
        conn = connect_db()
    except Exception as e:
        fail("D", "Участники", f"Подключение: {e}")
        return

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM results WHERE event_id=%s", (db_event_id,))
    count = cur.fetchone()[0]
    cur.close(); conn.close()

    if count == 0:
        warn("D", "Участники", f"0 записей — запустите: python load_race_results.py --config ... --init")
    else:
        ok("D", "Участники", f"{count} участников")


# ── Блок E: API ─────────────────────────────────────────────────────────────

def check_api(cfg, dist_cfg, server_url):
    if not server_url:
        skip("E", "API", "--server не указан")
        return

    event_name = cfg.get("display_name") or cfg.get("name") or ""
    db_event_id = dist_cfg.get("db_event_id")
    base = server_url.rstrip("/")

    def get(path):
        try:
            with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.URLError:
            return None, None

    # /api/current-event
    status, body = get("/api/current-event")
    if status is None:
        skip("E", "API", f"Сервер недоступен ({base})")
        return
    if status == 200 and event_name and event_name in body:
        ok("E", "API /current-event", f"{status} OK, содержит '{event_name}'")
    elif status == 200:
        warn("E", "API /current-event", f"200 OK, но '{event_name}' не найден в ответе")
    else:
        fail("E", "API /current-event", f"HTTP {status}")

    # /api/event-results
    status, _ = get(f"/api/event-results?event_id={db_event_id}")
    if status == 200:
        ok("E", "API /event-results", f"200 OK")
    else:
        fail("E", "API /event-results", f"HTTP {status}")

    # /api/event-info
    status, _ = get(f"/api/event-info?event_id={db_event_id}")
    if status == 200:
        ok("E", "API /event-info", f"200 OK")
    else:
        fail("E", "API /event-info", f"HTTP {status}")


# ── Блок F: Copernico ───────────────────────────────────────────────────────

def check_copernico(dist_cfg):
    cop = dist_cfg.get("copernico") or {}
    race_id = cop.get("race_id")
    if race_id is None:
        skip("F", "Copernico", "race_id не задан (норм до регистрации)")
        return

    cop_url = f"https://www.copernico.it/api/races/{race_id}/results"
    try:
        req = urllib.request.Request(cop_url, headers={"User-Agent": "KM_track/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            ok("F", "Copernico", f"race_id={race_id}, HTTP {r.status}")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            ok("F", "Copernico", f"race_id={race_id}, HTTP {e.code} (требует auth — норм)")
        else:
            warn("F", "Copernico", f"race_id={race_id}, HTTP {e.code}")
    except urllib.error.URLError as e:
        fail("F", "Copernico", f"Недоступен: {e.reason}")


# ── Блок G: Поля пресета ────────────────────────────────────────────────────

def check_preset_fields(dist_cfg):
    cop = dist_cfg.get("copernico") or {}
    race_id = cop.get("race_id")
    preset_name = cop.get("preset")

    if not preset_name:
        skip("G", "Пресет", "copernico.preset не задан")
        return

    # 1. Проверить что файл пресета существует
    preset_path = project_root / "config" / "copernico" / f"{preset_name}.yaml"
    if not preset_path.exists():
        fail("G", "Пресет", f"config/copernico/{preset_name}.yaml не найден")
        return
    ok("G", "Пресет", f"config/copernico/{preset_name}.yaml найден")

    if race_id is None:
        skip("G", "Поля API", "race_id не задан — проверку полей пропускаем")
        return

    # 2. Загрузить preset-конфиг
    try:
        preset_cfg = yaml.safe_load(preset_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        fail("G", "Пресет YAML", f"Ошибка парсинга: {e}")
        return

    # 3. Собрать ожидаемые поля
    time_fields_cfg = preset_cfg.get("time_fields", {})
    expected = set()
    for v in time_fields_cfg.values():
        if v:
            expected.add(v)
    cp_fields = preset_cfg.get("checkpoint_fields") or {}
    for v in cp_fields.values():
        if v:
            expected.add(v)

    # 4. Fetch одного участника из Copernico
    login = cop.get("login", "podbor250718@gmail.com")
    event_param = cop.get("event", "")
    encoded_preset = urllib.parse.quote(preset_name)
    encoded_event  = urllib.parse.quote(event_param)
    url = f"https://public-api.copernico.cloud/api/races/{race_id}/preset/{login}:::{encoded_preset}/{encoded_event}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KM_track/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        fail("G", "Поля API", f"HTTP {e.code} при fetch из Copernico")
        return
    except urllib.error.URLError as e:
        fail("G", "Поля API", f"Copernico недоступен: {e.reason}")
        return
    except Exception as e:
        fail("G", "Поля API", f"Ошибка: {e}")
        return

    runners = body.get("data", body) if isinstance(body, dict) else body
    if not runners:
        warn("G", "Поля API", "Copernico вернул пустой список")
        return

    received_keys = set(runners[0].keys())

    # 5. Сравнить
    missing = expected - received_keys
    extra = [k for k in received_keys if k.startswith("times.") and k not in expected]

    if missing:
        fail("G", "Поля API", f"Отсутствуют в ответе: {sorted(missing)}")
    else:
        ok("G", "Поля API", f"Все ожидаемые поля присутствуют: {sorted(expected) or '(нет)'}")

    if extra:
        _row("G", "Поля доп.", "INFO", f"Лишние times-поля (не в конфиге): {sorted(extra)[:5]}")


# ── Инспектор пресета ───────────────────────────────────────────────────────

def inspect_preset(dist_cfg):
    """Fetch из Copernico и вывести все поля первого участника — для составления preset YAML."""
    cop = dist_cfg.get("copernico") or {}
    race_id = cop.get("race_id")
    preset_name = cop.get("preset")
    login = cop.get("login", "podbor250718@gmail.com")
    event_param = cop.get("event", "")

    if not race_id:
        print("\nFAIL: race_id не задан в конфиге. Добавьте его перед инспекцией.")
        sys.exit(1)

    encoded_preset = urllib.parse.quote(preset_name or "")
    encoded_event  = urllib.parse.quote(event_param)
    url = f"https://public-api.copernico.cloud/api/races/{race_id}/preset/{login}:::{encoded_preset}/{encoded_event}"
    print(f"\nFetch: {url}\n")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KM_track/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"FAIL: HTTP {e.code}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"FAIL: {e.reason}")
        sys.exit(1)

    runners = body.get("data", body) if isinstance(body, dict) else body
    if not runners:
        print("Copernico вернул пустой список участников.")
        sys.exit(0)

    runner = runners[0]
    times_keys = sorted(k for k in runner if k.startswith("times."))
    meta_keys  = sorted(k for k in runner if not k.startswith("times."))
    gun_time   = body.get("gunTime") if isinstance(body, dict) else runner.get("gunTime")

    print(f"=== Поля пресета '{preset_name}' (первый участник из {len(runners)}) ===\n")

    print("--- Мета-поля ---")
    for k in meta_keys:
        print(f"  {k}: {runner[k]!r}")

    print(f"\n--- Временны́е поля (times.*) ---")
    for k in times_keys:
        v = runner[k]
        tag = " <-- ЕСТЬ ДАННЫЕ" if v is not None else ""
        print(f"  {k!r}: {v}{tag}")

    if gun_time:
        print(f"\n  gunTime (top-level): {gun_time!r}")

    print(f"\n--- Итого ---")
    filled = [k for k in times_keys if runner[k] is not None]
    empty  = [k for k in times_keys if runner[k] is None]
    print(f"  times.* с данными: {filled}")
    print(f"  times.* null:      {empty}")
    print(f"\n  Используйте эти имена в config/copernico/{preset_name}.yaml")


# ── main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pre-race check")
    parser.add_argument("--config", required=True, help="Путь к YAML конфигу события")
    parser.add_argument("--distance", required=True, help='Дистанция, напр. "5 км"')
    parser.add_argument("--server", default=None, help="URL сервера, напр. http://localhost:8000")
    parser.add_argument("--inspect", action="store_true",
                        help="Показать все поля из Copernico для данного пресета (для заполнения preset YAML)")
    args = parser.parse_args()

    config_path = project_root / args.config
    try:
        cfg, dist_cfg = load_config(config_path, args.distance)
    except (FileNotFoundError, ValueError) as e:
        print(f"FAIL  Конфиг: {e}")
        sys.exit(1)

    if args.inspect:
        inspect_preset(dist_cfg)
        sys.exit(0)

    event_name = cfg.get("display_name") or cfg.get("name") or config_path.stem
    event_year = cfg.get("year") or ""
    print(f"\n=== Pre-race check: {event_name} {event_year} ({args.distance}) ===\n")

    check_config(cfg, dist_cfg)
    check_files(dist_cfg)
    check_db(cfg, dist_cfg)
    check_participants(dist_cfg)
    check_api(cfg, dist_cfg, args.server)
    check_copernico(dist_cfg)
    check_preset_fields(dist_cfg)

    total_ok   = STATUS["ok"]
    total_warn = STATUS["warn"]
    total_skip = STATUS["skip"]
    total_fail = STATUS["fail"]

    print()
    print("─" * 45)
    print(f"  Результат: {total_ok} OK  {total_warn} WARN  {total_skip} SKIP  {total_fail} FAIL")
    print()

    if total_fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
