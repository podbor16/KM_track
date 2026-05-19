import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

HOST = VPS_HOST
USER = "root"
PASSWORD = VPS_PASSWORD

def run(client, cmd, timeout=30):
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode().strip()
    if out: print(out)
    return out

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

run(client, "ls /etc/nginx/sites-enabled/")
run(client, "cat /etc/nginx/sites-enabled/default | head -30")

# Deploy our nginx config (with SSL paths certbot already created)
run(client, "cp /opt/km_track/deploy/nginx.conf /etc/nginx/sites-available/km_track")
run(client, "ln -sf /etc/nginx/sites-available/km_track /etc/nginx/sites-enabled/km_track")
run(client, "rm -f /etc/nginx/sites-enabled/default")
run(client, "nginx -t")
run(client, "systemctl reload nginx")

# Verify
run(client, "curl -s http://127.0.0.1:80/ | head -5")

client.close()
print("\n=== Nginx исправлен ===")
