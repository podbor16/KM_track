import paramiko, sys

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

# All logs including access, errors
stdin, stdout, stderr = client.exec_command(
    'journalctl -u km_track --since "5 minutes ago" --no-pager 2>&1 | grep -i "500\\|error\\|ERROR\\|traceback\\|exception\\|business\\|login\\|WARNING" | head -60',
    timeout=30
)
out = stdout.read().decode("utf-8", errors="replace")
client.close()

sys.stdout.buffer.write(out.encode("utf-8"))
