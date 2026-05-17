"""
Тест производительности: _bulk_upsert и _bulk_update_join vs executemany на реальной БД.

Использует event_id=106 (Весна 2026), номера 9000-9999 (не пересекаются с реальными).
Данные удаляются после теста.

Запуск:
  python tests/perf_bulk_upsert.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analytics.db_connection_optimized import get_pooled_connection

EVENT_ID = 106
DORSAL_BASE = 9000
BATCH_SIZES = [100, 500, 895]


def make_test_rows(n: int) -> list:
    return [
        (EVENT_ID, str(DORSAL_BASE + i), f"Тест{i}", "Перфоманс",
         "2000-01-01", "M", "M18-29", "Not started")
        for i in range(n)
    ]


def insert_test_data(cursor, rows: list) -> list:
    cursor.executemany(
        "INSERT INTO results (event_id, start_number, surname, name, birthday, sex, category, race_status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    cursor.execute(
        f"SELECT id FROM results WHERE event_id = {EVENT_ID} AND CAST(start_number AS UNSIGNED) >= {DORSAL_BASE} ORDER BY id"
    )
    return [row['id'] for row in cursor.fetchall()]


def cleanup(cursor):
    cursor.execute(
        f"DELETE FROM results WHERE event_id = {EVENT_ID} AND CAST(start_number AS UNSIGNED) >= {DORSAL_BASE}"
    )


def bench_executemany_update(cursor, ids: list) -> float:
    """Старый подход: N отдельных UPDATE через executemany."""
    batch = [(f"Тест{i}_upd", id_) for i, id_ in enumerate(ids)]
    t0 = time.perf_counter()
    cursor.executemany("UPDATE results SET surname = %s WHERE id = %s", batch)
    return time.perf_counter() - t0


def bench_bulk_upsert(cursor, ids: list) -> float:
    """_bulk_upsert: один INSERT...ON DUPLICATE KEY UPDATE (все колонки)."""
    batch = [
        (id_, EVENT_ID, str(DORSAL_BASE + i), f"Тест{i}_upsert", "Перфоманс",
         "2000-01-01", "M", "M18-29", "Finished",
         None, None, None, None, None, None,
         None, None, None, None, None, None, None,
         None, None, None, None, None, None, None)
        for i, id_ in enumerate(ids)
    ]
    col_names = [
        'id', 'event_id', 'start_number', 'surname', 'name', 'birthday', 'sex', 'category', 'race_status',
        'time_gun_start', 'time_clear_start', 'time_gun_finish', 'time_clear_finish',
        'finish_pace_avg_gun', 'finish_pace_avg_clean',
        'time_clear_kt1', 'time_clear_kt2', 'time_clear_kt3', 'time_clear_kt4',
        'time_clear_kt5', 'time_clear_kt6', 'time_clear_kt7',
        'pace_avg_kt1', 'pace_avg_kt2', 'pace_avg_kt3', 'pace_avg_kt4',
        'pace_avg_kt5', 'pace_avg_kt6', 'pace_avg_kt7',
    ]
    update_cols = ['surname', 'name', 'race_status']
    row_ph = "(" + ",".join(["%s"] * len(col_names)) + ")"
    all_rows = ",".join([row_ph] * len(batch))
    upd = ",".join(f"`{c}`=VALUES(`{c}`)" for c in update_cols)
    cols = ",".join(f"`{c}`" for c in col_names)
    sql = f"INSERT INTO `results` ({cols}) VALUES {all_rows} ON DUPLICATE KEY UPDATE {upd}"
    flat = [v for row in batch for v in row]
    t0 = time.perf_counter()
    cursor.execute(sql, flat)
    return time.perf_counter() - t0


def bench_bulk_update_join(cursor, ids: list) -> float:
    """_bulk_update_join: один UPDATE JOIN для частичного обновления (rank-style)."""
    batch = [(id_, i + 1, (i % 50) + 1, (i % 20) + 1) for i, id_ in enumerate(ids)]
    join_cols = ['id']
    update_cols = ['rank_absolute', 'rank_sex', 'rank_category']
    all_cols = join_cols + update_cols
    col_aliases = ", ".join(f"%s AS `{c}`" for c in all_cols)
    union_row = f"SELECT {col_aliases}"
    union_sql = " UNION ALL ".join([union_row] * len(batch))
    join_cond = "`results`.`id` = v.`id`"
    set_clause = ", ".join(f"`results`.`{c}` = v.`{c}`" for c in update_cols)
    sql = f"UPDATE `results` INNER JOIN ({union_sql}) v ON {join_cond} SET {set_clause}"
    flat = [v for row in batch for v in row]
    t0 = time.perf_counter()
    cursor.execute(sql, flat)
    return time.perf_counter() - t0


def run():
    print("=" * 65)
    print("Тест производительности: bulk_upsert / bulk_update_join vs executemany")
    print(f"event_id={EVENT_ID}, тестовые номера {DORSAL_BASE}+, реальный WAN MySQL")
    print("=" * 65)

    conn = get_pooled_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        for n in BATCH_SIZES:
            print(f"\n--- {n} строк ---")

            cleanup(cursor)
            conn.commit()
            rows = make_test_rows(n)
            ids = insert_test_data(cursor, rows)
            conn.commit()
            print(f"  Вставлено {len(ids)} тестовых строк")

            # executemany (старый)
            t_many = bench_executemany_update(cursor, ids)
            conn.commit()
            print(f"  executemany (старый):       {t_many:.3f}s  ({t_many/n*1000:.1f} мс/строка)")

            # _bulk_upsert (новый, для _update_existing)
            t_upsert = bench_bulk_upsert(cursor, ids)
            conn.commit()
            print(f"  bulk_upsert (все колонки):  {t_upsert:.3f}s  ({t_upsert/n*1000:.1f} мс/строка)  "
                  f"ускорение: {t_many/t_upsert:.1f}x")

            # _bulk_update_join (новый, для rank-обновлений)
            t_join = bench_bulk_update_join(cursor, ids)
            conn.commit()
            print(f"  bulk_update_join (ранги):   {t_join:.3f}s  ({t_join/n*1000:.1f} мс/строка)  "
                  f"ускорение: {t_many/t_join:.1f}x")

    finally:
        print(f"\n--- Очистка ---")
        cleanup(cursor)
        conn.commit()
        cursor.close()
        conn.close()
        print("  Готово")

    print("=" * 65)


if __name__ == "__main__":
    run()
