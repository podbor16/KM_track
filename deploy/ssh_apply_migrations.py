"""
Apply pending SQL migrations to VPS database.
Usage: python deploy/ssh_apply_migrations.py [migration_file]
Default migration: migrations/add_missing_indexes.sql
"""
import sys
import paramiko
from pathlib import Path
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "migrations" / "add_missing_indexes.sql"


def run(client, cmd, timeout=120):
    transport = client.get_transport()
    channel = transport.open_session()
    channel.exec_command(cmd)
    out = b""
    while not channel.exit_status_ready():
        if channel.recv_ready():
            out += channel.recv(4096)
    out += channel.recv(4096)
    exit_code = channel.recv_exit_status()
    decoded = out.decode().strip()
    if decoded:
        print(decoded)
    if exit_code != 0:
        raise RuntimeError(f"Command failed (exit {exit_code}): {cmd[:100]}")
    return decoded


def main():
    print(f"=== Applying migration: {SQL_FILE.name} ===")

    with open(SQL_FILE, encoding="utf-8") as f:
        sql_content = f.read()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)

    # Upload SQL file
    remote_sql = f"/tmp/{SQL_FILE.name}"
    sftp = client.open_sftp()
    sftp.put(str(SQL_FILE), remote_sql)
    sftp.close()
    print(f"Uploaded {SQL_FILE.name} -> {remote_sql}")

    # Apply via Python + mysql.connector (reads credentials from .env on VPS)
    apply_script = f"""
import sys, os
sys.path.insert(0, '/opt/km_track')
from dotenv import load_dotenv
load_dotenv('/opt/km_track/.env')
import mysql.connector

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST', '127.0.0.1'),
    port=int(os.getenv('DB_PORT', 3306)),
    database=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
)
cur = conn.cursor()

with open('{remote_sql}') as f:
    sql = f.read()

for stmt in sql.split(';'):
    # Remove comment lines, keep only actual SQL
    lines = [l for l in stmt.split('\\n') if not l.strip().startswith('--')]
    stmt = '\\n'.join(lines).strip()
    if not stmt:
        continue
    try:
        cur.execute(stmt)
        print(f'OK: {{stmt[:80]}}')
    except Exception as e:
        if 'Duplicate key name' in str(e) or 'already exists' in str(e.args[0] if e.args else ''):
            print(f'SKIP (already exists): {{stmt[:60]}}')
        else:
            print(f'ERROR: {{e}}')

conn.commit()
cur.close()
conn.close()
print('=== Migration complete ===')
"""

    # Write and run the apply script
    sftp = client.open_sftp()
    with sftp.open("/tmp/apply_migration.py", "w") as f:
        f.write(apply_script)
    sftp.close()

    run(client, "/opt/km_track/venv/bin/python /tmp/apply_migration.py", timeout=120)

    # Verify: show indexes after migration
    print("\n=== Current indexes ===")
    verify_script = """
import sys, os
sys.path.insert(0, '/opt/km_track')
from dotenv import load_dotenv
load_dotenv('/opt/km_track/.env')
import mysql.connector

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST', '127.0.0.1'),
    port=int(os.getenv('DB_PORT', 3306)),
    database=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
)
cur = conn.cursor()
cur.execute("SELECT TABLE_NAME, INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS cols FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() GROUP BY TABLE_NAME, INDEX_NAME ORDER BY TABLE_NAME, INDEX_NAME")
for row in cur.fetchall():
    print(f'  {row[0]}.{row[1]}: ({row[2]})')
cur.close()
conn.close()
"""
    sftp = client.open_sftp()
    with sftp.open("/tmp/verify_indexes.py", "w") as f:
        f.write(verify_script)
    sftp.close()
    run(client, "/opt/km_track/venv/bin/python /tmp/verify_indexes.py")

    # Cleanup
    run(client, f"rm -f {remote_sql} /tmp/apply_migration.py /tmp/verify_indexes.py")

    client.close()
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
