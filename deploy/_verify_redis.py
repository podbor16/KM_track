"""Верификация Redis leader election и pub/sub по логам VPS."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)

def run(cmd):
    _, out, _ = client.exec_command(cmd)
    return out.read().decode("utf-8", errors="replace").strip()

print("=== Redis статус ===")
print(run("systemctl is-active redis-server && redis-cli ping"))

print("\n=== Workers подключились к Redis ===")
connected = run("journalctl -u km_track --since '10 minutes ago' --no-pager | grep 'Redis.*Connected'")
print(connected or "  (нет строк — перезапусти сервис)")
count = len([l for l in connected.splitlines() if l.strip()])
print(f"  Найдено строк Connected: {count} (ожидается 3 для workers=3)")

print("\n=== Leader election ===")
leader = run("journalctl -u km_track --since '10 minutes ago' --no-pager | grep 'Leader acquired'")
print(leader or "  (нет строк — лидер ещё не выбран или лог устарел)")
count_l = len([l for l in leader.splitlines() if l.strip()])
print(f"  Найдено строк Leader acquired: {count_l} (ожидается 1)")

print("\n=== Текущий лидер в Redis ===")
print(run("redis-cli get tracker:leader"))

print("\n=== RAM ===")
print(run("free -m | awk 'NR==2{printf \"%d/%d MB (%.1f%%)\", $3,$2,$3*100/$2}'"))

client.close()
print("\nВерификация завершена.")
