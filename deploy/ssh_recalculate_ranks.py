"""
Пересчитать места (rank_absolute/sex/category + КТ) для одного event_id на
VPS — переиспользует RaceLoader._recalculate_ranks() из load_race_results.py,
без запуска живого опроса Copernico. Нужно после точечной правки данных
results (напр. удаление тестовой/дублирующей строки), когда числа мест
должны схлопнуться без разрывов.

Usage: python deploy/ssh_recalculate_ranks.py <event_id>
"""
import sys
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

EVENT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else None
if not EVENT_ID:
    print("Usage: python deploy/ssh_recalculate_ranks.py <event_id>")
    sys.exit(1)


def run(client, cmd, timeout=120):
    transport = client.get_transport()
    channel = transport.open_session()
    channel.exec_command(cmd)
    out = b""
    while not channel.exit_status_ready():
        if channel.recv_ready():
            out += channel.recv(4096)
    out += channel.recv(4096)
    exit_code = channel.recv_exit_status()
    decoded = out.decode(errors="replace").strip()
    if decoded:
        print(decoded)
    if exit_code != 0:
        raise RuntimeError(f"Command failed (exit {exit_code}): {cmd[:100]}")
    return decoded


def main():
    print(f"=== Пересчёт мест для event_id={EVENT_ID} ===")

    remote_script = f"""
import sys
sys.path.insert(0, '/opt/km_track')
from load_race_results import RaceLoader, setup_logging

logger = setup_logging({EVENT_ID})
loader = RaceLoader(event_id={EVENT_ID}, logger=logger)
if not loader.connect():
    print('ERROR: connect() failed')
    sys.exit(1)

loader._recalculate_ranks()
loader.cursor.execute(
    "SELECT MIN(rank_absolute) AS min_r, MAX(rank_absolute) AS max_r, COUNT(*) AS cnt "
    "FROM results WHERE event_id=%s AND race_status='Finished'",
    ({EVENT_ID},)
)
row = loader.cursor.fetchone()
print(f"OK: min={{row['min_r']}} max={{row['max_r']}} finishers={{row['cnt']}}")
loader.cursor.close()
loader.connection.close()
"""

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)

    sftp = client.open_sftp()
    with sftp.open("/tmp/recalc_ranks.py", "w") as f:
        f.write(remote_script)
    sftp.close()

    run(client, "cd /opt/km_track && /opt/km_track/venv/bin/python /tmp/recalc_ranks.py", timeout=120)
    run(client, "rm -f /tmp/recalc_ranks.py")

    client.close()
    print("=== Done ===")


if __name__ == "__main__":
    main()
