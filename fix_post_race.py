#!/usr/bin/env python3
"""
Одноразовый постгоночный фикс для Первомайского полумарафона 2026.

Что делает:
  1. Вычисляет time_clear_finish = time_gun_finish - time_gun_start (волновая задержка)
  2. Пересчитывает finish_pace_avg_clean
  3. Пересчитывает места по чистому времени (rank_absolute/sex/category_clean)
  4. Пересчитывает ранги всех сегментов (sg_rank_*)

Запуск:
  conda run -n base python fix_post_race.py
"""

import sys
import os
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    print("❌ Установите python-dotenv")
    sys.exit(1)

import mysql.connector

# === Event IDs ===
EVENT_IDS = {
    142: 5.0,    # 5 км
    143: 21.1,   # 21.1 км
}


def connect():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        charset="utf8mb4",
        connection_timeout=15,
    )


def td_to_seconds(val):
    """timedelta или строка 'HH:MM:SS' → секунды. None если нет данных."""
    if val is None:
        return None
    if hasattr(val, 'total_seconds'):
        s = int(val.total_seconds())
        return s if s > 0 else None
    parts = str(val).split(':')
    if len(parts) != 3:
        return None
    try:
        h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
        total = h * 3600 + m * 60 + sec
        return total if total > 0 else None
    except (ValueError, TypeError):
        return None


def seconds_to_hms(s):
    if s is None or s <= 0:
        return None
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def seconds_to_pace(s, dist_km):
    """секунды + дистанция → '00:MM:SS' (MySQL TIME формат темпа)."""
    if not s or not dist_km:
        return None
    pace_sec = s / dist_km
    m = int(pace_sec) // 60
    sec = int(pace_sec) % 60
    return f"00:{m:02d}:{sec:02d}"


def assign_ranks(runners, time_key):
    """Назначает места по возрастанию времени."""
    valid = [(r['id'], r[time_key]) for r in runners if r.get(time_key) is not None]
    valid.sort(key=lambda x: x[1])
    ranks = {}
    for i, (rid, t) in enumerate(valid):
        if i == 0 or t != valid[i - 1][1]:
            ranks[rid] = i + 1
        else:
            ranks[rid] = ranks[valid[i - 1][0]]
    return ranks


def fix_times(cur, conn, event_id, dist_km):
    cur.execute(
        "SELECT id, time_gun_finish, time_gun_start FROM results WHERE event_id = %s",
        (event_id,)
    )
    rows = cur.fetchall()

    batch = []
    for r in rows:
        gun_sec = td_to_seconds(r['time_gun_finish'])
        if gun_sec is None:
            continue
        start_sec = td_to_seconds(r['time_gun_start'])
        if start_sec and start_sec > 0:
            net_sec = gun_sec - start_sec
            if net_sec <= 0:
                net_sec = gun_sec
        else:
            net_sec = gun_sec

        batch.append((
            seconds_to_hms(net_sec),
            seconds_to_pace(net_sec, dist_km),
            r['id'],
        ))

    if batch:
        cur.executemany(
            "UPDATE results SET time_clear_finish = %s, finish_pace_avg_clean = %s WHERE id = %s",
            batch,
        )
        conn.commit()
    print(f"  time_clear_finish обновлён: {len(batch)} записей")


def fix_finish_ranks(cur, conn, event_id):
    cur.execute(
        """SELECT id, sex, category, time_gun_finish, time_clear_finish
           FROM results
           WHERE event_id = %s AND race_status = 'Finished' AND time_gun_finish IS NOT NULL""",
        (event_id,)
    )
    finished = cur.fetchall()
    if not finished:
        print("  Нет финишировавших — пропуск рангов")
        return

    abs_gun = assign_ranks(finished, 'time_gun_finish')
    sex_gun, cat_gun = {}, {}
    for sv in set(r['sex'] for r in finished if r.get('sex')):
        sex_gun[sv] = assign_ranks([r for r in finished if r.get('sex') == sv], 'time_gun_finish')
    for cv in set(r['category'] for r in finished if r.get('category')):
        cat_gun[cv] = assign_ranks([r for r in finished if r.get('category') == cv], 'time_gun_finish')

    with_clean = [r for r in finished if r.get('time_clear_finish')]
    abs_clean = assign_ranks(with_clean, 'time_clear_finish')
    sex_clean, cat_clean = {}, {}
    for sv in set(r['sex'] for r in with_clean if r.get('sex')):
        sex_clean[sv] = assign_ranks([r for r in with_clean if r.get('sex') == sv], 'time_clear_finish')
    for cv in set(r['category'] for r in with_clean if r.get('category')):
        cat_clean[cv] = assign_ranks([r for r in with_clean if r.get('category') == cv], 'time_clear_finish')

    batch = []
    for r in finished:
        rid = r['id']
        sv = r.get('sex', '')
        cv = r.get('category', '')
        batch.append((
            abs_gun.get(rid), sex_gun.get(sv, {}).get(rid), cat_gun.get(cv, {}).get(rid),
            abs_clean.get(rid), sex_clean.get(sv, {}).get(rid), cat_clean.get(cv, {}).get(rid),
            rid,
        ))

    cur.executemany(
        """UPDATE results SET
               rank_absolute = %s, rank_sex = %s, rank_category = %s,
               rank_absolute_clean = %s, rank_sex_clean = %s, rank_category_clean = %s
           WHERE id = %s""",
        batch,
    )
    conn.commit()
    print(f"  Финишные ранги: {len(batch)} участников (чистые: {len(with_clean)})")


def fix_segment_ranks(cur, conn, event_id):
    cur.execute(
        """SELECT rs.id AS seg_id, rs.result_id AS id, rs.segment_code,
                  rs.sg_time_clear, rs.sg_time_gun,
                  r.sex, r.category
           FROM result_segments rs
           JOIN results r ON rs.result_id = r.id
           WHERE rs.event_id = %s AND rs.sg_time_clear IS NOT NULL""",
        (event_id,)
    )
    rows = cur.fetchall()

    by_code: dict = {}
    for row in rows:
        by_code.setdefault(row['segment_code'], []).append(dict(row))

    batch = []
    for code, segs in by_code.items():
        abs_r = assign_ranks(segs, 'sg_time_clear')
        sex_r, cat_r = {}, {}
        for sv in set(s['sex'] for s in segs if s.get('sex')):
            sex_r[sv] = assign_ranks([s for s in segs if s.get('sex') == sv], 'sg_time_clear')
        for cv in set(s['category'] for s in segs if s.get('category')):
            cat_r[cv] = assign_ranks([s for s in segs if s.get('category') == cv], 'sg_time_clear')

        with_gun = [s for s in segs if s.get('sg_time_gun')]
        abs_rg = assign_ranks(with_gun, 'sg_time_gun')
        sex_rg, cat_rg = {}, {}
        for sv in set(s['sex'] for s in with_gun if s.get('sex')):
            sex_rg[sv] = assign_ranks([s for s in with_gun if s.get('sex') == sv], 'sg_time_gun')
        for cv in set(s['category'] for s in with_gun if s.get('category')):
            cat_rg[cv] = assign_ranks([s for s in with_gun if s.get('category') == cv], 'sg_time_gun')

        for s in segs:
            rid = s['id']
            sv = s.get('sex', '')
            cv = s.get('category', '')
            batch.append((
                abs_r.get(rid), sex_r.get(sv, {}).get(rid), cat_r.get(cv, {}).get(rid),
                abs_rg.get(rid), sex_rg.get(sv, {}).get(rid), cat_rg.get(cv, {}).get(rid),
                s['seg_id'],
            ))

    if batch:
        cur.executemany(
            """UPDATE result_segments
               SET sg_rank_absolute = %s, sg_rank_sex = %s, sg_rank_category = %s,
                   sg_rank_absolute_gun = %s, sg_rank_sex_gun = %s, sg_rank_category_gun = %s
               WHERE id = %s""",
            batch,
        )
        conn.commit()
    print(f"  Ранги сегментов: {len(batch)} записей ({len(by_code)} кодов)")


def main():
    print("🔌 Подключение к БД...")
    conn = connect()
    cur = conn.cursor(dictionary=True)
    print("✅ Подключено")

    for event_id, dist_km in EVENT_IDS.items():
        print(f"\n=== Event {event_id} ({dist_km} км) ===")
        fix_times(cur, conn, event_id, dist_km)
        fix_finish_ranks(cur, conn, event_id)
        fix_segment_ranks(cur, conn, event_id)

    cur.close()
    conn.close()
    print("\n✅ Готово! Обновите страницу в браузере.")


if __name__ == '__main__':
    main()
