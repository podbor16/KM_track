"""
Генератор тестовых данных для нагрузочного теста.
Вставляет 3000 тест-бегунов в event_id=104 (bibs 90001-93000) и удаляет их после теста.
Использует mysql CLI на VPS от root — обходит ограничения km_analytic на тригеры.

Использование:
    python tests/load/setup_race_data.py --setup
    python tests/load/setup_race_data.py --teardown
"""

import argparse
import io
import random
import sys
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

N_RUNNERS = 3000
EVENT_ID = 104
START_BIB = 90001


def _build_setup_sql() -> str:
    random.seed(42)

    surnames = ["Иванов", "Петров", "Сидоров", "Козлов", "Новиков",
                "Морозов", "Попов", "Лебедев", "Соколов", "Федоров"]
    names_m = ["Александр", "Дмитрий", "Сергей", "Андрей", "Максим", "Алексей", "Иван"]
    names_f = ["Анна", "Мария", "Елена", "Ольга", "Наталья", "Татьяна", "Ирина"]

    lines = [
        "SET NAMES utf8mb4;",
        f"DELETE FROM results WHERE event_id={EVENT_ID} "
        f"AND start_number BETWEEN {START_BIB} AND {START_BIB + N_RUNNERS - 1};",
    ]

    for i in range(N_RUNNERS):
        bib = START_BIB + i
        client_id = 999000001 + i
        is_male = (i % 10) < 7
        sex = "мужской" if is_male else "женский"
        name = random.choice(names_m if is_male else names_f)
        surname = "ТЕСТ_" + random.choice(surnames)
        category = "мужчины до 49 лет" if is_male else "женщины до 49 лет"

        stage = i % 100
        kt1 = "NULL"
        gun_finish = "NULL"
        clear_finish = "NULL"
        race_status = "Not started"

        if stage >= 40 and stage < 75:
            pace_sec = random.randint(270, 480)
            s = int(2.5 * pace_sec)
            kt1 = f"'{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}'"
        elif stage >= 75:
            pace_sec = random.randint(270, 420)
            s1 = int(2.5 * pace_sec)
            s2 = int(5.0 * pace_sec)
            kt1 = f"'{s1 // 3600:02d}:{(s1 % 3600) // 60:02d}:{s1 % 60:02d}'"
            clear_finish = f"'{s2 // 3600:02d}:{(s2 % 3600) // 60:02d}:{s2 % 60:02d}'"
            gun_sec = s2 + random.randint(0, 10)
            gun_finish = f"'{gun_sec // 3600:02d}:{(gun_sec % 3600) // 60:02d}:{gun_sec % 60:02d}'"
            race_status = "Finished"

        def q(s):
            return s.replace("'", "\\'")

        lines.append(
            f"INSERT INTO results "
            f"(surname,name,birthday,client_id,event_id,sex,start_number,category,race_status,"
            f"time_gun_start,time_clear_start,time_gun_finish,time_clear_finish,time_clear_kt1,time_clear_kt2) "
            f"VALUES ('{q(surname)}','{q(name)}','1990-01-01',{client_id},{EVENT_ID},"
            f"'{sex}',{bib},'{category}','{race_status}',"
            f"'00:00:00','00:00:00',{gun_finish},{clear_finish},{kt1},NULL);"
        )

    lines.append(f"SELECT COUNT(*) AS inserted FROM results "
                 f"WHERE event_id={EVENT_ID} AND start_number BETWEEN {START_BIB} AND {START_BIB + N_RUNNERS - 1};")
    return "\n".join(lines)


def _build_teardown_sql() -> str:
    return (
        f"DELETE FROM results WHERE event_id={EVENT_ID} "
        f"AND start_number BETWEEN {START_BIB} AND {START_BIB + N_RUNNERS - 1};\n"
        f"DELETE FROM leads WHERE event_id={EVENT_ID} AND client_id >= 999900000;\n"
        f"SELECT ROW_COUNT() AS affected;\n"
    )


def _ssh_connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
    return client


def _run_sql(sql: str, description: str) -> bool:
    print(f"\n{description}...")
    client = _ssh_connect()
    sftp = client.open_sftp()
    sql_bytes = sql.encode("utf-8")
    with sftp.open("/tmp/race_op.sql", "wb") as f:
        f.write(sql_bytes)
    sftp.close()

    cmd = "mysql -u root krasmarafon < /tmp/race_op.sql"
    _, out, err = client.exec_command(cmd, timeout=120)
    out_text = out.read().decode("utf-8", errors="replace").strip()
    err_text = err.read().decode("utf-8", errors="replace").strip()
    exit_code = out.channel.recv_exit_status()
    client.close()

    if out_text:
        print(f"  {out_text}")
    if err_text:
        print(f"  STDERR: {err_text}")
    return exit_code == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="Вставить 3000 тест-бегунов")
    parser.add_argument("--teardown", action="store_true", help="Удалить тест-данные")
    args = parser.parse_args()

    if args.setup:
        sql = _build_setup_sql()
        ok = _run_sql(sql, f"Вставка {N_RUNNERS} тест-бегунов в event_id={EVENT_ID}")
        if ok:
            print(f"  OK: bibs {START_BIB}–{START_BIB + N_RUNNERS - 1}")
    elif args.teardown:
        sql = _build_teardown_sql()
        ok = _run_sql(sql, "Очистка тест-данных")
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
