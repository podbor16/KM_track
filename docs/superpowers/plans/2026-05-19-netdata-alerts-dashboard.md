# Netdata Alerts + Race Day Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure Netdata to send ntfy push notifications for 4 critical alerts and create a focused 6-chart "Race Day" dashboard — all without Netdata Cloud.

**Architecture:** Three config files are deployed to VPS via paramiko SFTP (`deploy/ssh_nd_alerts.py`). Alert routing: Netdata health rule triggers → `alarm-notify.sh` → custom shell script → POST to ntfy.sh. Dashboard is created manually via Netdata UI after alerts are working.

**Tech Stack:** paramiko (SSH/SFTP), Netdata health config DSL, bash, curl, ntfy.sh

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `deploy/ssh_nd_alerts.py` | Create | Deploy all 3 Netdata config files to VPS via SSH/SFTP |
| `/etc/netdata/custom-notify.sh` | Create on VPS | Shell script that POSTs to ntfy.sh when Netdata fires an alert |
| `/etc/netdata/health_alarm_notify.conf` | Modify on VPS | Enable custom sender, disable other senders |
| `/etc/netdata/health.d/km_track.conf` | Create on VPS | 4 custom health alert rules |

---

### Task 1: Deploy script — custom-notify.sh + health_alarm_notify.conf

**Files:**
- Create: `deploy/ssh_nd_alerts.py`

- [ ] **Step 1: Create deploy/ssh_nd_alerts.py with custom-notify.sh content and upload logic**

```python
"""
Deploy Netdata alerts to VPS:
  - /etc/netdata/custom-notify.sh      (POST to ntfy.sh)
  - /etc/netdata/health_alarm_notify.conf (enable custom sender)
  - /etc/netdata/health.d/km_track.conf   (4 alert rules)
"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import paramiko
import time
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

HOST = VPS_HOST

CUSTOM_NOTIFY_SH = r"""#!/bin/bash
# Called by Netdata alarm-notify.sh for CUSTOM notifications
NTFY_URL="https://ntfy.sh/km-analytics-monitoring-2026"
PRIORITY="default"
[ "$status" = "CRITICAL" ] && PRIORITY="urgent"
[ "$status" = "WARNING" ]  && PRIORITY="high"

curl -s -X POST "$NTFY_URL" \
  -H "Title: KM_track — $alarm on $host" \
  -H "Priority: $PRIORITY" \
  -H "Tags: warning,server" \
  -d "$status: $alarm
Chart: $chart
Value: $value $units
Info: $info"
"""

HEALTH_ALARM_NOTIFY_CONF = """
###############################################################################
# KM_track custom ntfy sender
###############################################################################
SEND_CUSTOM=YES
DEFAULT_RECIPIENT_CUSTOM="admin"
CUSTOM_SENDER_ENABLED=YES

# Disable unused senders to reduce noise
SEND_EMAIL=NO
SEND_SLACK=NO
SEND_TELEGRAM=NO
SEND_PD=NO
SEND_TWILIO=NO
"""

KM_TRACK_HEALTH_CONF = """
# KM_track custom health rules

# CPU > 80% sustained 3 min -> WARNING
alarm: km_track_cpu_high
    on: system.cpu
lookup: average -3m unaligned of user,system
 units: %
 every: 1m
  warn: $this > 80
  crit: $this > 95
  info: CPU utilization high — check for runaway process
    to: admin
  delay: up 0 down 3m multiplier 1.5 max 1h

# RAM used > 75% -> WARNING
alarm: km_track_ram_high
    on: mem.ram
lookup: average -1m unaligned of used
 units: %
 every: 1m
  warn: $this > 75
  crit: $this > 90
  info: RAM usage high
    to: admin
  delay: up 0 down 5m multiplier 1.5 max 1h

# km_track service not active -> CRITICAL
alarm: km_track_service_down
    on: systemd_service_units.service_unit_state
 filter: *km_track*
lookup: average -30s unaligned of active
 units: state
 every: 30s
  crit: $this != 1
  info: km_track.service is not active — application may be down
    to: admin
  delay: up 0 down 0 multiplier 1 max 1h

# Redis: no data for 30s -> CRITICAL
alarm: redis_down
    on: redis.operations
lookup: average -30s unaligned of operations
 units: operations/s
 every: 30s
  crit: $this == nan
  info: Redis is not responding — no data for 30 seconds
    to: admin
  delay: up 0 down 0 multiplier 1 max 1h
"""


def run(client, cmd, timeout=60):
    print(f">>> {cmd[:120]}")
    _, sout, serr = client.exec_command(cmd, timeout=timeout)
    out = sout.read().decode("utf-8", errors="replace").strip()
    err = serr.read().decode("utf-8", errors="replace").strip()
    if out:
        print(out[:600])
    if err and not any(x in err.lower() for x in ["warning", "deprecated", "notice"]):
        print(f"[err] {err[:300]}")
    return out


def upload_text(client, content, remote_path):
    sftp = client.open_sftp()
    with sftp.open(remote_path, "w") as f:
        f.write(content)
    sftp.close()
    print(f"Uploaded: {remote_path}")


client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
print(f"Connected to {HOST}\n")

# 1. custom-notify.sh
upload_text(client, CUSTOM_NOTIFY_SH, "/etc/netdata/custom-notify.sh")
run(client, "chmod +x /etc/netdata/custom-notify.sh")
run(client, "chown netdata:netdata /etc/netdata/custom-notify.sh")
print("custom-notify.sh: OK")

# 2. health_alarm_notify.conf — append our block (preserve existing file)
run(client, "cp /etc/netdata/health_alarm_notify.conf /etc/netdata/health_alarm_notify.conf.bak")
existing = run(client, "grep -c 'SEND_CUSTOM=YES' /etc/netdata/health_alarm_notify.conf 2>/dev/null || echo 0")
if existing.strip() == "0":
    run(client, f"cat >> /etc/netdata/health_alarm_notify.conf << 'EOF'\n{HEALTH_ALARM_NOTIFY_CONF}\nEOF")
    print("health_alarm_notify.conf: appended")
else:
    print("health_alarm_notify.conf: SEND_CUSTOM=YES already present, skipping")

# 3. km_track.conf health rules
upload_text(client, KM_TRACK_HEALTH_CONF, "/etc/netdata/health.d/km_track.conf")
run(client, "chown netdata:netdata /etc/netdata/health.d/km_track.conf")
print("health.d/km_track.conf: OK")

# 4. Reload health rules
out = run(client, "netdatacli reload-health 2>&1 || echo 'reload failed'")
time.sleep(2)
if "failed" in out.lower():
    print("ERROR: netdatacli reload-health failed — check config syntax")
else:
    print("Health rules reloaded: OK")

# 5. Verify custom-notify.sh is accessible by netdata
run(client, "ls -la /etc/netdata/custom-notify.sh")
run(client, "ls -la /etc/netdata/health.d/km_track.conf")

# 6. Show active alert count
run(client, "netdatacli active-alarms 2>/dev/null | head -20 || echo '(netdatacli not available)'")

print("""
=== DEPLOYED ===
Next step: run smoke test
  python deploy/ssh_nd_alerts.py --test
Or test manually on VPS:
  netdatacli send-test-alarm
Then subscribe to ntfy topic in app:
  https://ntfy.sh/km-analytics-monitoring-2026
""")

client.close()
```

- [ ] **Step 2: Run the deploy script**

```
python deploy/ssh_nd_alerts.py
```

Expected output:
```
Connected to <host>
Uploaded: /etc/netdata/custom-notify.sh
custom-notify.sh: OK
health_alarm_notify.conf: appended
Uploaded: /etc/netdata/health.d/km_track.conf
health.d/km_track.conf: OK
Health rules reloaded: OK
```

If you see `reload failed` — SSH to VPS and run `journalctl -u netdata -n 30` to see the parse error in the health rule config.

- [ ] **Step 3: Commit deploy script**

```bash
git add deploy/ssh_nd_alerts.py
git commit -m "feat: deploy Netdata ntfy alerts — 4 rules + custom-notify.sh"
```

---

### Task 2: Smoke test — verify ntfy receives notification

**Files:**
- Modify: `deploy/ssh_nd_alerts.py` (add `--test` flag)

- [ ] **Step 1: Add test mode to ssh_nd_alerts.py**

At the end of the file, before `client.close()`, add:

```python
import sys
if "--test" in sys.argv:
    print("\n=== SMOKE TEST: sending test alarm ===")
    # Send test notification via custom-notify.sh directly
    test_cmd = (
        'status=WARNING alarm=test_alarm host=$(hostname) chart=system.cpu '
        'value=85 units="%" info="Smoke test from deploy script" '
        '/etc/netdata/custom-notify.sh'
    )
    out = run(client, test_cmd)
    print(f"ntfy POST result: {out or '(no output — check ntfy subscription)'}")
    print("Open https://ntfy.sh/km-analytics-monitoring-2026 in browser to verify")
```

- [ ] **Step 2: Run smoke test**

```
python deploy/ssh_nd_alerts.py --test
```

Expected: ntfy app or browser shows notification "KM_track — test_alarm on <hostname>" with Priority: High.

If no notification arrives:
1. Check ntfy URL: `curl -s https://ntfy.sh/km-analytics-monitoring-2026/json | head -5` — should show recent messages
2. Check script executable: `ssh root@<host> "bash -x /etc/netdata/custom-notify.sh"` with env vars set
3. Check curl is installed on VPS: `ssh root@<host> "which curl"`

- [ ] **Step 3: Test via Netdata native alarm**

SSH to VPS and run:
```bash
netdatacli send-test-alarm
```

Check ntfy — should receive a test notification. If not, check `/var/log/netdata/error.log`:
```bash
tail -50 /var/log/netdata/error.log | grep -i custom
```

- [ ] **Step 4: Commit smoke test addition**

```bash
git add deploy/ssh_nd_alerts.py
git commit -m "feat: add --test flag to ssh_nd_alerts.py for ntfy smoke test"
```

---

### Task 3: Create "Race Day" dashboard in Netdata UI

This task is **manual** — Netdata dashboard creation is done in the browser. No code to deploy.

- [ ] **Step 1: Open Netdata UI**

Navigate to: `https://analytics.krasmarafon.ru/netdata/`

Login: `admin / km2026monitor`

- [ ] **Step 2: Create new dashboard**

Click **Dashboards** tab (top nav) → **+ New Dashboard** → name it `Race Day` → Save.

- [ ] **Step 3: Add 6 charts in this order**

For each chart: click **+ Add Chart** → search by chart ID → drag to desired size.

| # | Chart ID to search | Title |
|---|-------------------|-------|
| 1 | `system.cpu` | CPU utilization |
| 2 | `mem.ram` | RAM used |
| 3 | `systemd_km_track.mem` or `cgroup_km_track.mem_usage` | km_track RAM |
| 4 | `ip.sockstat_sockets` | TCP sockets (SSE connections) |
| 5 | `web_log_nginx.requests_total` | nginx requests/s |
| 6 | `redis_local.operations` | Redis ops/s |

> **Note for chart 3:** The exact chart ID depends on Netdata version. Search for `km_track` in the chart picker to find the correct ID. It may appear as `cgroup_km_track.mem_usage` or `systemd_service_units`.

> **Note for chart 4:** `ip.sockstat_sockets` shows kernel-level TCP connection counts — this is the correct metric for SSE connections. It's NOT the same as nginx active connections (which may be 0 for long-lived SSE).

- [ ] **Step 4: Verify TCP sockets chart shows non-zero ESTABLISHED connections**

Open the tracker at `https://analytics.krasmarafon.ru/tracker` in another browser tab, keep it open 30 seconds, then check `ip.sockstat_sockets` chart — should show at least 1 ESTABLISHED connection (your SSE connection).

- [ ] **Step 5: Document dashboard name for the team**

Dashboard is saved in Netdata local storage — it persists across Netdata restarts. No commit needed. Just note:

```
Race Day dashboard: https://analytics.krasmarafon.ru/netdata/ → Dashboards → Race Day
```

---

## Verification Checklist

After all tasks complete:

- [ ] `netdatacli reload-health` — no parse errors
- [ ] `python deploy/ssh_nd_alerts.py --test` → ntfy notification arrives
- [ ] Dashboard "Race Day" visible at Netdata UI with all 6 charts
- [ ] `ip.sockstat_sockets` chart shows non-zero when tracker is open
- [ ] `redis_local.operations` chart shows non-zero (Redis is running)
- [ ] `web_log_nginx.requests_total` chart shows traffic

## Self-Review

**Spec coverage:**
- ✅ 4 alert rules (CPU, RAM, service down, Redis down) — Task 1
- ✅ custom-notify.sh with ntfy POST — Task 1
- ✅ health_alarm_notify.conf SEND_CUSTOM=YES — Task 1
- ✅ Smoke test via custom-notify.sh directly — Task 2
- ✅ Smoke test via netdatacli — Task 2
- ✅ 6-chart dashboard — Task 3
- ✅ TCP sockets = kernel-level SSE count — documented in Task 3

**Placeholders:** None — all steps have exact commands or exact config content.

**Type consistency:** No types involved (shell config + bash).

**Scope:** Focused — 3 config files + 1 deploy script + 1 manual dashboard step. No architecture changes.
