import paramiko
import time
import sys
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

HOST = VPS_HOST
USER = "root"
PASSWORD = VPS_PASSWORD
REPO_URL = "https://github.com/podbor16/KM_track.git"

SSH_PUB_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJn4bGA7Ljr3u7iRD73mXlZtRIQtPt6Cs7QlzJzjfIt0 claude-deploy"

def run(client, cmd, timeout=300):
    print(f"\n>>> {cmd[:80]}...")
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

# Add SSH key
run(client, f'mkdir -p ~/.ssh && echo "{SSH_PUB_KEY}" > ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys')
print("SSH ключ добавлен")

# Run setup
run(client, "curl -s -o /root/setup.sh https://raw.githubusercontent.com/podbor16/KM_track/Map/deploy/setup.sh", timeout=30)
run(client, f"echo 'y' | DEBIAN_FRONTEND=noninteractive bash /root/setup.sh {REPO_URL}", timeout=600)

client.close()
print("\n=== ГОТОВО ===")
