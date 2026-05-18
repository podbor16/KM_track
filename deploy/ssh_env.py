import paramiko
import time

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"
LOCAL_ENV = r"c:\Users\podbo\Работа\КРАСМАРАФОН\KM_track\.env"
REMOTE_ENV = "/opt/km_track/.env"

def run(client, cmd, timeout=60):
    print(f">>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode().strip()
    if out:
        print(out)
    return out

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
print("Подключился")

# Upload .env via SFTP
sftp = client.open_sftp()
sftp.put(LOCAL_ENV, REMOTE_ENV)
sftp.chmod(REMOTE_ENV, 0o600)
sftp.close()
print(f".env скопирован на сервер")

# Restart service
run(client, "systemctl restart km_track")
time.sleep(5)
run(client, "systemctl status km_track --no-pager | head -5")
run(client, "curl -s http://127.0.0.1:8000/health")

client.close()
print("\n=== ГОТОВО ===")
