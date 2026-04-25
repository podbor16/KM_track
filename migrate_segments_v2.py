"""Миграция: добавить sg_rank_*_gun в result_segments."""
import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST', '79.174.89.159'),
    port=int(os.getenv('DB_PORT', '16171')),
    database=os.getenv('DB_NAME', 'krasmarafon'),
    user=os.getenv('DB_USER', 'km_analytic'),
    password=os.getenv('DB_PASSWORD'),
)
cur = conn.cursor()

cur.execute("SHOW COLUMNS FROM result_segments")
cols = [r[0] for r in cur.fetchall()]
print("Текущие колонки:", cols)

for col, definition, after in [
    ('sg_rank_absolute_gun', 'INT NULL', 'sg_rank_absolute'),
    ('sg_rank_sex_gun',      'INT NULL', 'sg_rank_sex'),
    ('sg_rank_category_gun', 'INT NULL', 'sg_rank_category'),
]:
    if col not in cols:
        cur.execute(f"ALTER TABLE result_segments ADD COLUMN {col} {definition} AFTER {after}")
        print(f"✅ Добавлена {col}")
    else:
        print(f"ℹ️  {col} уже есть")

conn.commit()
cur.execute("SHOW COLUMNS FROM result_segments")
print("Новые колонки:", [r[0] for r in cur.fetchall()])
cur.close()
conn.close()
