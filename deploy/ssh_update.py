import paramiko, time
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

HOST = VPS_HOST
USER = "root"
PASSWORD = VPS_PASSWORD

def run(client, cmd, timeout=60):
    print(f">>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode().strip()
    if out: print(out)
    return out

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

run(client, "git config --global --add safe.directory /opt/km_track")
run(client, "git -C /opt/km_track pull origin Map")
run(client, "systemctl restart km_track")
time.sleep(3)
run(client, "systemctl status km_track --no-pager | head -4")

client.close()
print("=== Обновлено ===")
