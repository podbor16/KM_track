"""Заполнение triatleta_24h тестовыми данными для разработки без Copernico API.

Использование:
    # Через SSH-туннель (рекомендуется):
    ssh -L 3306:127.0.0.1:3306 root@89.108.88.104 -N &
    python seed_tri_test_data.py

    # С явным хостом:
    python seed_tri_test_data.py --host 89.108.88.104 --port 3306

    # Сбросить и пересоздать данные:
    python seed_tri_test_data.py --reset
"""
import argparse
import os
import random

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

EVENT_ID = 1
LAP_DISTANCE_KM = 4.040

PARTICIPANTS = [
    # (start_number, surname, name, gender, category)
    (1,  "Иванов",     "Алексей",  "Мужчина", "individual"),
    (2,  "Петров",     "Дмитрий",  "Мужчина", "individual"),
    (3,  "Сидоров",    "Михаил",   "Мужчина", "individual"),
    (4,  "Кузнецов",   "Андрей",   "Мужчина", "individual"),
    (5,  "Новиков",    "Сергей",   "Мужчина", "individual"),
    (6,  "Фёдоров",    "Павел",    "Мужчина", "individual"),
    (7,  "Морозова",   "Елена",    "Женщина", "individual"),
    (8,  "Соколова",   "Анна",     "Женщина", "individual"),
    (9,  "Попова",     "Мария",    "Женщина", "individual"),
    (10, "Лебедев",    "Виктор",   "Мужчина", "individual"),
    (51, "Команда А",  "Эстафета", "M", "relay"),
    (52, "Команда Б",  "Эстафета", "M", "relay"),
    (53, "Команда В",  "Эстафета", "F", "relay"),
    (54, "Команда Г",  "Эстафета", "M", "relay"),
]

# Количество кругов для каждого участника (по порядку PARTICIPANTS).
# Реалистично для середины суточной гонки (~15 часов прошло).
LAPS_PER_PARTICIPANT = [98, 95, 92, 90, 88, 85, 72, 68, 65, 80, 100, 91, 78, 83]

# Средний темп круга (мс) для каждого — чуть разный
BASE_LAP_MS = [
    555_000,  # ~9.25 мин  1  лидер
    570_000,  # ~9.5  мин  2
    590_000,  # ~9.83 мин  3
    600_000,  # ~10   мин  4
    614_000,  # ~10.2 мин  5
    635_000,  # ~10.6 мин  6
    754_000,  # ~12.6 мин  7  (F)
    800_000,  # ~13.3 мин  8  (F)
    840_000,  # ~14   мин  9  (F)
    680_000,  # ~11.3 мин  10
    540_000,  # ~9    мин  51 relay A (лидер группы)
    594_000,  # ~9.9  мин  52 relay B
    697_000,  # ~11.6 мин  53 relay C
    649_000,  # ~10.8 мин  54 relay D
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


def _ensure_event(cursor) -> None:
    cursor.execute("SELECT id FROM events WHERE id = %s", (EVENT_ID,))
    if cursor.fetchone():
        return
    cursor.execute(
        """INSERT INTO events (id, code, name, gun_datetime, lap_distance_km, duration_hours)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (EVENT_ID, "tri_24h_2026", "Triatleta — Суточная велогонка 24ч",
         "2026-06-25 13:00:00", LAP_DISTANCE_KM, 24),
    )
    print(f"  [events] Создано событие id={EVENT_ID}")


def _seed_participants(cursor) -> dict[int, int]:
    """Вставляет участников, возвращает mapping start_number -> participant_id."""
    bib_to_pid: dict[int, int] = {}
    for (bib, surname, name, gender, category) in PARTICIPANTS:
        cursor.execute(
            "SELECT id FROM participants WHERE event_id=%s AND start_number=%s",
            (EVENT_ID, bib),
        )
        row = cursor.fetchone()
        if row:
            bib_to_pid[bib] = row[0]
            print(f"  [participants] #{bib} {surname} — уже есть (id={row[0]})")
        else:
            cursor.execute(
                """INSERT INTO participants
                   (event_id, start_number, surname, name, gender, category)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (EVENT_ID, bib, surname, name, gender, category),
            )
            bib_to_pid[bib] = cursor.lastrowid
            print(f"  [participants] #{bib} {surname} — вставлен (id={bib_to_pid[bib]})")
    return bib_to_pid


def _seed_laps(cursor, bib_to_pid: dict[int, int]) -> int:
    inserted = 0
    for idx, (bib, *_) in enumerate(PARTICIPANTS):
        pid = bib_to_pid[bib]
        n_laps = LAPS_PER_PARTICIPANT[idx]
        base_ms = BASE_LAP_MS[idx]
        rng = random.Random(bib * 7919)  # детерминированный seed

        cursor.execute(
            "SELECT MAX(lap_number) FROM laps WHERE participant_id=%s", (pid,)
        )
        already = cursor.fetchone()[0] or 0
        if already >= n_laps:
            print(f"  [laps] #{bib} — уже {already} кругов, пропуск")
            continue

        cumulative_ms = 0
        # Восстановить накопленное до already-го круга
        if already > 0:
            cursor.execute(
                "SELECT cumulative_ms FROM laps WHERE participant_id=%s AND lap_number=%s",
                (pid, already),
            )
            row = cursor.fetchone()
            cumulative_ms = row[0] if row else 0

        for lap_n in range(already + 1, n_laps + 1):
            # +/- 5% случайного разброса
            jitter = rng.randint(-base_ms // 20, base_ms // 20)
            lap_ms = base_ms + jitter
            cumulative_ms += lap_ms
            cursor.execute(
                """INSERT IGNORE INTO laps
                   (participant_id, event_id, lap_number, cumulative_ms, lap_ms)
                   VALUES (%s,%s,%s,%s,%s)""",
                (pid, EVENT_ID, lap_n, cumulative_ms, lap_ms),
            )
            if cursor.rowcount > 0:
                inserted += 1

        print(f"  [laps] #{bib} — добавлено {n_laps - already} кругов")
    return inserted


def _reset(cursor) -> None:
    cursor.execute("DELETE FROM laps WHERE event_id = %s", (EVENT_ID,))
    cursor.execute("DELETE FROM participants WHERE event_id = %s", (EVENT_ID,))
    cursor.execute("DELETE FROM events WHERE id = %s", (EVENT_ID,))
    print("  [reset] laps, participants, events удалены")


def main():
    parser = argparse.ArgumentParser(description="Seed triatleta_24h test data")
    parser.add_argument("--host", default=os.getenv("DB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    parser.add_argument("--reset", action="store_true", help="Удалить всё и пересоздать")
    args = parser.parse_args()

    print(f"Connecting to {args.host}:{args.port} → triatleta_24h")
    conn = _connect(args.host, args.port)
    cursor = conn.cursor()

    if args.reset:
        print("--- RESET ---")
        _reset(cursor)
        conn.commit()

    print("--- Событие ---")
    _ensure_event(cursor)

    print("--- Участники ---")
    bib_to_pid = _seed_participants(cursor)

    print("--- Круги ---")
    inserted = _seed_laps(cursor, bib_to_pid)

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\nГотово. Вставлено новых кругов: {inserted}")


if __name__ == "__main__":
    main()
