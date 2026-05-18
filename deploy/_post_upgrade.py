"""Настройка VPS после апгрейда до 2 CPU / 2 GB RAM."""
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

print("=== Новые характеристики сервера ===")
run("nproc && free -m | head -2 && df -h / | tail -1")

print("\n=== Восстанавливаем innodb_buffer_pool_size = 128M ===")
config = """[mysqld]
innodb_buffer_pool_size = 128M
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

print("\n=== Восстанавливаем uvicorn: 2 workers ===")
run("sed -i 's/--workers 1/--workers 2/' /etc/systemd/system/km_track.service")
run("systemctl daemon-reload && systemctl restart km_track")
time.sleep(4)
run("systemctl is-active km_track")

print("\n=== Итоговый RAM ===")
run("free -m")
run("swapon --show")

print("\n=== Health check ===")
run("curl -s http://127.0.0.1:8000/health")

print("\n✅ Сервер настроен для 2 CPU / 2 GB RAM.")
c.close()
