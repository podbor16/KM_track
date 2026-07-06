import paramiko

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

def run(cmd, timeout=30):
    print(f">>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out)
    if err: print("ERR:", err)

run("cp /opt/km_track/deploy/nginx.conf /etc/nginx/nginx.conf")
run("nginx -t")
run("systemctl reload nginx")
run("curl -sI http://localhost/static/css/navigation.css | grep -i content-type")

client.close()
print("=== nginx обновлён ===")
