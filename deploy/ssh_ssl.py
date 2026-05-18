import paramiko
import time

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"

def run(client, cmd, timeout=120):
    print(f"\n>>> {cmd[:100]}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = []
    for line in iter(stdout.readline, ""):
        print(line, end="")
        out.append(line)
    return "".join(out)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
print("Подключился")

# Check DNS resolves to this server
run(client, "dig +short analytics.krasmarafon.ru || nslookup analytics.krasmarafon.ru | grep Address | tail -1")

# Check nginx status
run(client, "systemctl status nginx --no-pager | head -5")

# Get SSL cert
run(client, "certbot --nginx -d analytics.krasmarafon.ru --non-interactive --agree-tos -m admin@krasmarafon.ru", timeout=120)

# Reload nginx
run(client, "systemctl reload nginx")

# Final check
run(client, "curl -s http://127.0.0.1:8000/health")

client.close()
print("\n=== SSL ГОТОВ ===")
