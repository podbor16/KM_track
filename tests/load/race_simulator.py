"""
Симулятор хода забега для нагрузочного теста.
Каждые 30с "финишируют" 10 тест-бегунов → results_updated SSE событие.
Каждые 60с регистрируется новый участник → startlist_updated SSE событие.

Запуск:
    python tests/load/race_simulator.py --duration 480
"""

import argparse
import sys
import time
import paramiko

VPS_HOST = "89.108.88.104"
VPS_USER = "root"
VPS_PASSWORD = "shsfzw5fHiQY8v6g"

SIMULATOR_SCRIPT = r'''
import mysql.connector
import time
import sys

duration = int(sys.argv[1]) if len(sys.argv) > 1 else 480

conn = mysql.connector.connect(
    host="127.0.0.1", user="km_analytic",
    password="CneZbvlOS2H-BLsQ", database="krasmarafon"
)
cur = conn.cursor()

start = time.time()
tick = 0
print(f"Simulator started, duration={duration}s", flush=True)

UPDATE_SQL = (
    "UPDATE results "
    "SET race_status='Finished', time_gun_finish='00:25:00', time_clear_finish='00:25:00' "
    "WHERE event_id=104 AND start_number BETWEEN 90001 AND 93000 "
    "AND race_status='Not started' AND time_clear_kt1 IS NOT NULL LIMIT 10"
)
INSERT_SQL = (
    "INSERT INTO leads (surname, name, sex, city, birthday, event_name, event_distance, "
    "event_year, client_id, event_id, email, phone, products, status, is_new, is_new_event) "
    "VALUES ('TEST_Sim', 'Runner', 'мужской', 'Красноярск', '1990-01-01', "
    "'Ночной забег', '5 км', 2026, %s, 104, "
    "'test@test.ru', '+7-000-000-0000', '5 km Night run', 0, 0, 0)"
)

while time.time() - start < duration:
    cur.execute(UPDATE_SQL)
    conn.commit()
    finishes = cur.rowcount

    new_lead = 0
    if tick % 2 == 0:
        client_id = 999900000 + tick
        cur.execute(INSERT_SQL, (client_id,))
        conn.commit()
        new_lead = 1

    elapsed = time.time() - start
    print(f"  [{elapsed:.0f}s] +{finishes} finishes, +{new_lead} lead", flush=True)
    tick += 1
    time.sleep(30)

cur.close()
conn.close()
print("Simulator stopped", flush=True)
'''


def _ssh_connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
    client.get_transport().set_keepalive(30)
    return client


def run_simulator(duration: int) -> bool:
    print(f"\nСтарт симулятора забега (duration={duration}s)...")
    client = _ssh_connect()
    sftp = client.open_sftp()
    with sftp.open("/tmp/race_simulator.py", "w") as f:
        f.write(SIMULATOR_SCRIPT)
    sftp.close()
    python = "/opt/km_track/venv/bin/python3"
    stdin, stdout, stderr = client.exec_command(
        f"{python} /tmp/race_simulator.py {duration}", timeout=duration + 30
    )
    stdout.channel.settimeout(None)
    for line in iter(lambda: stdout.readline(), ""):
        print(f"  [sim] {line}", end="", flush=True)
    exit_code = stdout.channel.recv_exit_status()
    client.close()
    return exit_code == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=480)
    args = parser.parse_args()
    ok = run_simulator(args.duration)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
