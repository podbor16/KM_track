"""
Апдейт result_segments для event_id=71 (Весна 2025):
- Заполняет sg_time_gun, sg_pace_avg_gun
- Пересчитывает net и gun ранги
- Checkpoint distances: [0, 2.5, 5] км → 2 сегмента по 2.5 км
"""
import os
import datetime
from typing import Optional, Dict, List
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

EVENT_ID = 71
# checkpoint_distances из events.checkpoint_distances для event_id=71
CHECKPOINT_KM = [0.0, 2.5, 5.0]
SEGMENT_DISTANCES = {
    'start-kt1':    2.5,   # 0 → 2.5
    'kt1-finish':   2.5,   # 2.5 → 5.0
    'start-finish': 5.0,   # 0 → 5.0 (если есть)
}


def td_to_seconds(td) -> Optional[float]:
    """datetime.timedelta → секунды"""
    if td is None:
        return None
    if isinstance(td, datetime.timedelta):
        return td.total_seconds()
    return None


def seconds_to_hhmmss(secs: float) -> str:
    secs = int(round(secs))
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f'{h:02d}:{m:02d}:{s:02d}'


def format_pace(total_seconds: float, dist_km: float) -> Optional[str]:
    if dist_km <= 0 or total_seconds <= 0:
        return None
    pace_sec_per_km = total_seconds / dist_km
    m = int(pace_sec_per_km // 60)
    s = int(pace_sec_per_km % 60)
    return f'00:{m:02d}:{s:02d}'


def assign_ranks(entries: List[Dict], time_key: str) -> Dict[int, int]:
    """entries: list of {'id': result_id, time_key: timedelta/seconds}"""
    valid = [(e['id'], e[time_key]) for e in entries if e.get(time_key) is not None]
    valid.sort(key=lambda x: x[1])
    ranks: Dict[int, int] = {}
    for i, (rid, t) in enumerate(valid):
        if i == 0 or t != valid[i - 1][1]:
            ranks[rid] = i + 1
        else:
            ranks[rid] = ranks[valid[i - 1][0]]
    return ranks


conn = mysql.connector.connect(
    host=os.getenv('DB_HOST', '79.174.89.159'),
    port=int(os.getenv('DB_PORT', '16171')),
    database=os.getenv('DB_NAME', 'krasmarafon'),
    user=os.getenv('DB_USER', 'km_analytic'),
    password=os.getenv('DB_PASSWORD'),
    autocommit=False,
)
cur = conn.cursor(dictionary=True, buffered=True)
# Увеличиваем таймаут ожидания блокировки для сессии
cur.execute("SET SESSION innodb_lock_wait_timeout = 120")
cur.execute("SET SESSION lock_wait_timeout = 120")

# --- 1. Загружаем все сегменты event_id=71 с данными из results ---
print(f'Загрузка сегментов event_id={EVENT_ID}...')
cur.execute("""
    SELECT rs.id AS seg_id, rs.result_id, rs.segment_code,
           rs.sg_time_clear,
           r.sex, r.category,
           r.time_clear_finish, r.time_gun_finish
    FROM result_segments rs
    JOIN results r ON rs.result_id = r.id
    WHERE rs.event_id = %s AND rs.sg_time_clear IS NOT NULL
""", (EVENT_ID,))
rows = cur.fetchall()
print(f'Найдено {len(rows)} записей')

# --- 2. Вычисляем sg_time_gun и sg_pace_avg_gun ---
update_batch = []
for row in rows:
    clear_td = row['sg_time_clear']
    clear_sec = td_to_seconds(clear_td)
    if clear_sec is None:
        continue

    seg_code = row['segment_code']
    dist_km = SEGMENT_DISTANCES.get(seg_code)
    if dist_km is None:
        print(f'  Неизвестный сегмент: {seg_code}, пропускаем')
        continue

    # gun_offset = time_gun_finish - time_clear_finish (волновая задержка)
    finish_gun_sec = td_to_seconds(row['time_gun_finish'])
    finish_clear_sec = td_to_seconds(row['time_clear_finish'])

    if seg_code.startswith('start-') and finish_gun_sec and finish_clear_sec:
        gun_offset_sec = finish_gun_sec - finish_clear_sec
        if gun_offset_sec < 0:
            gun_offset_sec = 0
        gun_sec = clear_sec + gun_offset_sec
    else:
        # Для внутренних сегментов: gun == net
        gun_sec = clear_sec

    sg_time_gun = seconds_to_hhmmss(gun_sec)
    sg_pace_avg_gun = format_pace(gun_sec, dist_km)

    update_batch.append((sg_time_gun, sg_pace_avg_gun, row['seg_id']))

print(f'Обновляем {len(update_batch)} записей (sg_time_gun, sg_pace_avg_gun)...')
BATCH = 100
for i in range(0, len(update_batch), BATCH):
    chunk = update_batch[i:i + BATCH]
    cur.executemany(
        """UPDATE result_segments
           SET sg_time_gun = %s, sg_pace_avg_gun = %s
           WHERE id = %s""",
        chunk,
    )
    conn.commit()
print(f'✅ sg_time_gun и sg_pace_avg_gun обновлены')

# --- 3. Пересчёт net и gun рангов ---
print('Пересчёт рангов...')
cur.execute("""
    SELECT rs.id AS seg_id, rs.result_id, rs.segment_code,
           rs.sg_time_clear, rs.sg_time_gun,
           r.sex, r.category
    FROM result_segments rs
    JOIN results r ON rs.result_id = r.id
    WHERE rs.event_id = %s AND rs.sg_time_clear IS NOT NULL
""", (EVENT_ID,))
seg_rows = cur.fetchall()

from collections import defaultdict
by_code: Dict[str, list] = defaultdict(list)
for row in seg_rows:
    clear_sec = td_to_seconds(row['sg_time_clear'])
    gun_td = row['sg_time_gun']
    # sg_time_gun теперь строка после UPDATE; перечитаем как timedelta через TIME_FORMAT — нет,
    # MySQL возвращает TIME как timedelta. После нашего UPDATE через строку "00:MM:SS",
    # при следующем SELECT оно придёт как timedelta.
    # Чтобы не делать второй SELECT — вычислим gun_sec прямо здесь.
    gun_sec = td_to_seconds(gun_td)
    if gun_sec is None:
        # Перевычислим из batch
        for b in update_batch:
            if b[2] == row['seg_id']:
                # b = (sg_time_gun_str, sg_pace_avg_gun_str, seg_id)
                t = b[0]  # "HH:MM:SS"
                parts = t.split(':')
                gun_sec = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                break
        if gun_sec is None:
            gun_sec = clear_sec

    by_code[row['segment_code']].append({
        'id':       row['result_id'],
        'seg_id':   row['seg_id'],
        'net_sec':  clear_sec,
        'gun_sec':  gun_sec,
        'sex':      row['sex'],
        'category': row['category'],
    })

rank_batch = []
for seg_code, segs in by_code.items():
    abs_net  = assign_ranks(segs, 'net_sec')
    abs_gun  = assign_ranks(segs, 'gun_sec')

    sex_net: Dict[str, Dict[int, int]] = {}
    sex_gun: Dict[str, Dict[int, int]] = {}
    for sex_val in set(s['sex'] for s in segs if s.get('sex')):
        grp = [s for s in segs if s.get('sex') == sex_val]
        sex_net[sex_val] = assign_ranks(grp, 'net_sec')
        sex_gun[sex_val] = assign_ranks(grp, 'gun_sec')

    cat_net: Dict[str, Dict[int, int]] = {}
    cat_gun: Dict[str, Dict[int, int]] = {}
    for cat_val in set(s['category'] for s in segs if s.get('category')):
        grp = [s for s in segs if s.get('category') == cat_val]
        cat_net[cat_val] = assign_ranks(grp, 'net_sec')
        cat_gun[cat_val] = assign_ranks(grp, 'gun_sec')

    for seg in segs:
        rid = seg['id']
        sv = seg.get('sex', '')
        cv = seg.get('category', '')
        rank_batch.append((
            abs_net.get(rid),  sex_net.get(sv, {}).get(rid),  cat_net.get(cv, {}).get(rid),
            abs_gun.get(rid),  sex_gun.get(sv, {}).get(rid),  cat_gun.get(cv, {}).get(rid),
            seg['seg_id'],
        ))

print(f'Обновляем {len(rank_batch)} записей рангов...')
for i in range(0, len(rank_batch), BATCH):
    chunk = rank_batch[i:i + BATCH]
    cur.executemany(
        """UPDATE result_segments
           SET sg_rank_absolute = %s, sg_rank_sex = %s, sg_rank_category = %s,
               sg_rank_absolute_gun = %s, sg_rank_sex_gun = %s, sg_rank_category_gun = %s
           WHERE id = %s""",
        chunk,
    )
    conn.commit()
print('✅ Ранги пересчитаны')

# --- 4. Проверка ---
cur.execute("""
    SELECT segment_code,
           COUNT(*) as total,
           SUM(sg_time_gun IS NOT NULL) as has_gun_time,
           SUM(sg_pace_avg_gun IS NOT NULL) as has_gun_pace,
           SUM(sg_rank_absolute_gun IS NOT NULL) as has_gun_rank
    FROM result_segments
    WHERE event_id = %s
    GROUP BY segment_code
""", (EVENT_ID,))
for row in cur.fetchall():
    print(f"  {row['segment_code']}: {row['total']} записей, "
          f"gun_time={row['has_gun_time']}, gun_pace={row['has_gun_pace']}, gun_rank={row['has_gun_rank']}")

cur.close()
conn.close()
print('✅ Готово')
