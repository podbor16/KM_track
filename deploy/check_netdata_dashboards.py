"""
SSH into VPS and find where Netdata v2.10.3 stores custom dashboards.
Reports ALL output of discovery commands.
"""
import sys
import io
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = VPS_HOST

def run(client, cmd, timeout=60):
    """Run command and return full output"""
    print(f"\n>>> {cmd}")
    print("=" * 80)
    _, sout, serr = client.exec_command(cmd, timeout=timeout, get_pty=False)
    out = sout.read().decode("utf-8", errors="replace")
    err = serr.read().decode("utf-8", errors="replace")
    exit_code = sout.channel.recv_exit_status()

    if out:
        print(out)
    if err:
        print(f"[STDERR]\n{err}")
    print(f"[exit code: {exit_code}]")
    return out, err, exit_code


# Connect
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
print(f"Connected to {HOST}\n")

# 1. Find dashboard-related files
print("\n" + "=" * 80)
print("1. FIND DASHBOARD-RELATED FILES")
print("=" * 80)
run(client,
    'find /var/lib/netdata /etc/netdata /opt/netdata /usr/share/netdata '
    '-name "*.json" -o -name "*dashboard*" -o -name "*custom*" 2>/dev/null | grep -v ".pyc" | head -40')

# 2. Check netdata var lib
print("\n" + "=" * 80)
print("2. CHECK /var/lib/netdata/ DIRECTORY")
print("=" * 80)
run(client, 'ls -la /var/lib/netdata/ 2>/dev/null')

# 3. Check if there's a dashboards directory
print("\n" + "=" * 80)
print("3. SEARCH FOR 'dashboards' DIRECTORY SYSTEM-WIDE")
print("=" * 80)
run(client,
    'find / -path /proc -prune -o -path /sys -prune -o -name "dashboards" -print 2>/dev/null | head -10')

# 4. Check Netdata API for dashboard endpoints
print("\n" + "=" * 80)
print("4. CHECK NETDATA API /api/v1/info")
print("=" * 80)
run(client,
    'curl -s http://127.0.0.1:19999/api/v1/info | python3 -c "import sys,json; d=json.load(sys.stdin); print([k for k in d.keys()])" 2>/dev/null')

# 5. Check Netdata config directory
print("\n" + "=" * 80)
print("5. CHECK /etc/netdata/ DIRECTORY")
print("=" * 80)
run(client, 'ls -la /etc/netdata/')

# 6a. Check v2 dashboards API
print("\n" + "=" * 80)
print("6a. CHECK NETDATA API /api/v2/dashboards")
print("=" * 80)
run(client, 'curl -s "http://127.0.0.1:19999/api/v2/dashboards" 2>/dev/null | head -300')

# 6b. Check v1 dashboards API
print("\n" + "=" * 80)
print("6b. CHECK NETDATA API /api/v1/dashboards")
print("=" * 80)
run(client, 'curl -s "http://127.0.0.1:19999/api/v1/dashboards" 2>/dev/null | head -300')

# 7. Recent files modified in netdata dirs
print("\n" + "=" * 80)
print("7. RECENT FILES MODIFIED IN NETDATA DIRS")
print("=" * 80)
run(client,
    'find /var/lib/netdata /etc/netdata -newer /etc/netdata/netdata.conf -type f 2>/dev/null | head -20')

# 8. Check for web root and dashboard files
print("\n" + "=" * 80)
print("8. CHECK NETDATA WEB ROOT")
print("=" * 80)
run(client, 'find /usr/share/netdata -name "*.html" -o -name "*.json" 2>/dev/null | grep -i dashboard | head -20')

# 9. Check netdata.conf for web config
print("\n" + "=" * 80)
print("9. CHECK netdata.conf FOR WEB/DASHBOARD CONFIG")
print("=" * 80)
run(client, r'grep -A 5 "^\[web\]" /etc/netdata/netdata.conf 2>/dev/null')

# 10. Check if Netdata stores cloud synced dashboards
print("\n" + "=" * 80)
print("10. CHECK FOR CLOUD/SYNC DIRECTORIES")
print("=" * 80)
run(client, 'find /var/lib/netdata -type d | head -30')

client.close()
print("\n" + "=" * 80)
print("DONE — Check output above for dashboard storage locations")
print("=" * 80)
