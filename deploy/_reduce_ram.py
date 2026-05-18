import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('89.108.88.104', username='root', password='shsfzw5fHiQY8v6g', timeout=15)

def run(cmd, timeout=20):
    transport = c.get_transport()
    ch = transport.open_session()
    ch.settimeout(None)
    ch.exec_command(cmd)
    out = []
    deadline = time.time() + timeout
    while True:
        if ch.recv_ready():
            chunk = ch.recv(4096).decode(errors="replace")
            out.append(chunk)
            for line in chunk.splitlines():
                if line.strip(): print(line)
            deadline = time.time() + timeout
        if ch.recv_stderr_ready(): ch.recv_stderr(4096); deadline = time.time() + timeout
        if ch.exit_status_ready(): break
        if time.time() > deadline: break
        time.sleep(0.2)
    ch.close()
    return "".join(out).strip()

print("=== RAM до изменений ===")
run("free -m | head -2")

print("\n=== Уменьшаем innodb_buffer_pool_size 128M → 64M ===")
config = """[mysqld]
innodb_buffer_pool_size = 64M
max_connections = 20
bind-address = 0.0.0.0

ssl-ca   = /etc/mysql/ssl/ca.pem
ssl-cert = /etc/mysql/ssl/server-cert.pem
ssl-key  = /etc/mysql/ssl/server-key.pem
"""
run(f"cat > /etc/mysql/mysql.conf.d/km_track.cnf << 'EOF'\n{config}\nEOF")
run("systemctl restart mysql")
time.sleep(3)
run("systemctl is-active mysql")

print("\n=== Уменьшаем uvicorn: 2 workers → 1 ===")
run("sed -i 's/--workers 2/--workers 1/' /etc/systemd/system/km_track.service")
run("systemctl daemon-reload")
run("systemctl restart km_track")
time.sleep(3)
run("systemctl is-active km_track")

print("\n=== RAM после изменений ===")
run("free -m")
run("curl -s http://127.0.0.1:8000/health")

print("\n✅ Готово. MySQL занимает меньше RAM, запросы должны ускориться.")
c.close()
