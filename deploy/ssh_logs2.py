import paramiko, sys
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

HOST = VPS_HOST
USER = "root"
PASSWORD = VPS_PASSWORD

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

# Get full logs including stderr
stdin, stdout, stderr = client.exec_command(
    "journalctl -u km_track --since '10 minutes ago' --no-pager -p warning 2>&1", timeout=30
)
out = stdout.read().decode("utf-8", errors="replace")
client.close()

sys.stdout.buffer.write(out.encode("utf-8"))
