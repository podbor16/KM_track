import paramiko
import time

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"
REPO_URL = "https://github.com/podbor16/KM_track.git"

def run(client, cmd, timeout=300):
    print(f"\n>>> {cmd[:100]}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = []
    for line in iter(stdout.readline, ""):
        print(line, end="")
        out.append(line)
    return "".join(out)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print(f"Подключаюсь к {HOST}...")
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
print("Подключился!\n")

# Remove old partial clone and re-clone correct branch
run(client, "rm -rf /opt/km_track")
run(client, f"git clone -b Map {REPO_URL} /opt/km_track", timeout=120)
run(client, "ls /opt/km_track/ | head -20")
run(client, "ls /opt/km_track/requirements.txt && echo OK")

# Create virtualenv and install dependencies
run(client, "python3.12 -m venv /opt/km_track/venv", timeout=60)
run(client, "cd /opt/km_track && venv/bin/pip install --upgrade pip -q", timeout=60)
run(client, "cd /opt/km_track && venv/bin/pip install -r requirements.txt", timeout=300)

# Copy systemd service and enable
run(client, "cp /opt/km_track/deploy/km_track.service /etc/systemd/system/")
run(client, "systemctl daemon-reload && systemctl enable km_track")
run(client, "chown -R km:km /opt/km_track")

# Start service
run(client, "systemctl start km_track")
time.sleep(5)
run(client, "systemctl status km_track --no-pager")
run(client, "curl -s http://127.0.0.1:8000/health || echo 'health check failed'")

client.close()
print("\n=== ГОТОВО ===")
