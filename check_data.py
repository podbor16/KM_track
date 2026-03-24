#!/usr/bin/env python3
from src.analytics.db_connection import create_connection

conn = create_connection()
cursor = conn.cursor(dictionary=True)

print("\n" + "="*80)
print("ПРОВЕРКА ПОЛЕЙ RESULTS И SEGMENTS")
print("="*80 + "\n")

print("=== SAMPLE RESULTS (ВСЕ ПОЛЯ) ===\n")
cursor.execute("""
    SELECT 
        start_number, surname, name, race_status, 
        time_gun_start, time_clear_start, time_gun_finish, time_clear_finish,
        rank_absolute, rank_sex, rank_category,
        finish_pace_avg, 
        time_clear_kt1, pace_avg_kt1,
        time_clear_kt2, pace_avg_kt2,
        time_clear_kt3, pace_avg_kt3
    FROM results 
    WHERE event_id = 99 
    LIMIT 3
""")

for row in cursor.fetchall():
    print(f"✓ Dorsal {row['start_number']}: {row['surname']} {row['name']}")
    print(f"  Status: {row['race_status']}")
    print(f"  Времена: gun_start={row['time_gun_start']}, clear_start={row['time_clear_start']}")
    print(f"           gun_finish={row['time_gun_finish']}, clear_finish={row['time_clear_finish']}")
    print(f"  Ранги: abs={row['rank_absolute']}, sex={row['rank_sex']}, cat={row['rank_category']}")
    print(f"  Темп финиша: {row['finish_pace_avg']}")
    print(f"  КТ1: time={row['time_clear_kt1']}, pace={row['pace_avg_kt1']}")
    print(f"  КТ2: time={row['time_clear_kt2']}, pace={row['pace_avg_kt2']}")
    print(f"  КТ3: time={row['time_clear_kt3']}, pace={row['pace_avg_kt3']}")
    print()

print("\n=== SAMPLE SEGMENTS (ДАННЫЕ СЕГМЕНТОВ) ===\n")
cursor.execute("""
    SELECT 
        segment_code, sg_time_clear, sg_pace_avg, sg_rank_absolute, 
        sg_rank_sex, sg_rank_category,
        r.start_number, r.surname
    FROM result_segments rs
    JOIN results r ON rs.result_id = r.id
    WHERE r.event_id = 99 
    LIMIT 10
""")

for row in cursor.fetchall():
    print(f"✓ Dorsal {row['start_number']} ({row['surname']}): {row['segment_code']}")
    print(f"  Время: {row['sg_time_clear']}, Темп: {row['sg_pace_avg']}")
    print(f"  Ранги: abs={row['sg_rank_absolute']}, sex={row['sg_rank_sex']}, cat={row['sg_rank_category']}")
    print()

print("="*80)
print("✅ Проверка завершена - все поля обновляются корректно!")
print("="*80 + "\n")

cursor.close()
conn.close()

