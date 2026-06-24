"""Генерация тестовых кругов для реальных участников triatleta_24h.

Участники берутся из БД (не создаются заново).
Симулирует N часов гонки с реалистичным изменением темпа.

Использование:
    # SSH-туннель открыт на 3306:
    python seed_tri_test_laps.py

    # Симулировать 10 часов гонки:
    python seed_tri_test_laps.py --hours 10

    # Сбросить круги и пересоздать:
    python seed_tri_test_laps.py --reset --hours 15

    # Прямо на VPS (из /opt/km_track):
    python seed_tri_test_laps.py --host 127.0.0.1 --hours 15
"""
import argparse
import os
import random
import math
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

EVENT_ID = 1
LAP_KM = 4.040

# Профили участников: (start_number, base_lap_sec, fatigue_factor, pattern)
# base_lap_sec  — базовое время круга в секундах
# fatigue_factor — на сколько % замедляется к концу (0.0 = без усталости, 0.15 = +15%)
# pattern       — 'steady' | 'negative' (ускоряется) | 'fade' (резко устаёт после 60%)
PROFILES = [
    # bib   base_sec  fatigue  pattern
    (1001,  510,      0.05,    "steady"),    # Триатлета (relay) — лидер, ровный темп
    (1002,  530,      0.08,    "steady"),    # Суперспорт (relay)
    (1,     560,      0.10,    "negative"),  # Бурдин — разгоняется
    (3,     575,      0.12,    "steady"),    # Захаренков
    (9,     590,      0.14,    "fade"),      # Умнов — устаёт во второй половине
    (10,    605,      0.12,    "steady"),    # Подлесный
    (11,    620,      0.10,    "negative"),  # Ребенков
    (12,    645,      0.15,    "fade"),      # Кондратюк
    (13,    720,      0.10,    "steady"),    # Прокофьева (Ж)
    (1003,  680,      0.20,    "fade"),      # Полсуток (relay) — устаёт
]


def _connect(host: str, port: int) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=host,
        port=port,
        database="triatleta_24h",
        user=os.getenv("DB_USER", "km_analytic"),
        password=os.getenv("DB_PASSWORD"),
        charset="utf8mb4",
        autocommit=False,
    )


def _get_participant_map(cursor) -> dict[int, int]:
    """Возвращает mapping start_number → participant_id из БД."""
    cursor.execute(
        "SELECT start_number, id FROM participants WHERE event_id = %s", (EVENT_ID,)
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def _lap_time_ms(base_sec: float, lap_n: int, total_laps: int,
                 fatigue: float, pattern: str, rng: random.Random) -> int:
    """Вычисляет время круга в мс с учётом усталости и паттерна."""
    progress = lap_n / max(total_laps, 1)  # 0..1

    if pattern == "steady":
        trend = 1.0 + fatigue * progress
    elif pattern == "negative":
        # Разгоняется в первой трети, потом ровно
        if progress < 0.33:
            trend = 1.0 + fatigue * 0.3 * (1 - progress / 0.33)
        else:
            trend = 1.0
    elif pattern == "fade":
        # Ровно первые 60%, затем резкое замедление
        if progress < 0.6:
            trend = 1.0 + fatigue * 0.2 * progress
        else:
            trend = 1.0 + fatigue * (progress - 0.6) * 2.5
    else:
        trend = 1.0

    # Случайный разброс ±4%
    jitter = rng.uniform(-0.04, 0.04)
    lap_sec = base_sec * trend * (1 + jitter)
    return max(int(lap_sec * 1000), 300_000)  # минимум 5 мин


def _generate_laps(cursor, pid: int, base_sec: float, fatigue: float,
                   pattern: str, race_hours: float, rng: random.Random,
                   stop_early_h: float | None = None) -> int:
    race_ms = int(race_hours * 3600_000)
    stop_ms = int(stop_early_h * 3600_000) if stop_early_h is not None else race_ms
    cumulative_ms = 0
    lap_n = 0
    inserted = 0

    est_laps = int(race_ms / (base_sec * 1000))

    while True:
        lap_n += 1
        lap_ms = _lap_time_ms(base_sec, lap_n, est_laps, fatigue, pattern, rng)
        cumulative_ms += lap_ms
        if cumulative_ms > stop_ms:
            break

        cursor.execute(
            """INSERT IGNORE INTO laps
               (participant_id, event_id, lap_number, cumulative_ms, lap_ms)
               VALUES (%s, %s, %s, %s, %s)""",
            (pid, EVENT_ID, lap_n, cumulative_ms, lap_ms),
        )
        if cursor.rowcount > 0:
            inserted += 1

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Seed test laps for real participants")
    parser.add_argument("--host",  default=os.getenv("DB_HOST", "127.0.0.1"))
    parser.add_argument("--port",  type=int, default=int(os.getenv("DB_PORT", "3306")))
    parser.add_argument("--hours", type=float, default=15.0,
                        help="Сколько часов гонки симулировать (default: 15)")
    parser.add_argument("--reset", action="store_true",
                        help="Удалить все круги события перед генерацией")
    parser.add_argument("--pit-bib", type=int, default=None,
                        help="Номер участника, у которого обрываются круги за 2 avg-круга до конца (питстоп)")
    args = parser.parse_args()

    print(f"Connecting to {args.host}:{args.port} → triatleta_24h")
    conn = _connect(args.host, args.port)
    cursor = conn.cursor()

    bib_to_pid = _get_participant_map(cursor)
    print(f"Найдено участников в БД: {len(bib_to_pid)}")

    if args.reset:
        cursor.execute("DELETE FROM laps WHERE event_id = %s", (EVENT_ID,))
        print(f"  [reset] удалено {cursor.rowcount} кругов")
        conn.commit()

    print(f"\nГенерирую круги для {args.hours}ч гонки...\n")
    total = 0
    for bib, base_sec, fatigue, pattern in PROFILES:
        pid = bib_to_pid.get(bib)
        if pid is None:
            print(f"  #{bib:4d} — нет в БД, пропуск")
            continue

        rng = random.Random(bib * 31337)
        stop_early_h = None
        pit_note = ""
        if args.pit_bib and bib == args.pit_bib:
            # Обрываем круги за 2 avg-круга до конца → питстоп
            stop_early_h = args.hours - (base_sec * 2) / 3600
            pit_note = f"  ← PIT (стоп на {stop_early_h:.2f}ч)"
        inserted = _generate_laps(cursor, pid, base_sec, fatigue, pattern, args.hours, rng, stop_early_h)
        avg_kmh = LAP_KM / (base_sec / 3600)
        print(f"  #{bib:4d} (pid={pid}) — {inserted} кругов  ~{avg_kmh:.1f} км/ч  [{pattern}]{pit_note}")
        total += inserted

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\nГотово. Вставлено кругов: {total}")


if __name__ == "__main__":
    main()
