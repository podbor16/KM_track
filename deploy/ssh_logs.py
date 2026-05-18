import paramiko, sys

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

stdin, stdout, stderr = client.exec_command(
    "journalctl -u km_track -n 80 --no-pager 2>&1", timeout=30
)
out = stdout.read().decode("utf-8", errors="replace")
client.close()

sys.stdout.buffer.write(out.encode("utf-8"))
