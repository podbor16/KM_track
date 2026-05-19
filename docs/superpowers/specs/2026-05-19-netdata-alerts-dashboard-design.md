# Netdata Alerts + Focused Dashboard — Design Spec

## Goal

Configure Netdata to send ntfy alerts for critical events and create a focused 6-chart dashboard for race day monitoring. No Netdata Cloud dependency.

## Stack Context

- Netdata v2.10.3, standalone (no cloud)
- VPS: 3 vCPU / 2.9 GB RAM, 2 uvicorn workers, Redis, MySQL, nginx
- ntfy topic: `https://ntfy.sh/km-analytics-monitoring-2026`
- Netdata already auto-collects: Redis (21 charts), nginx access log (10 charts), km_track systemd (5 charts), TCP sockets

## Part 1: Alerts via ntfy

### Mechanism

Netdata health rules trigger `alarm-notify.sh` → custom sender script → POST to ntfy.sh.

Config files:
- `/etc/netdata/health_alarm_notify.conf` — enable custom sender, set ntfy URL
- `/etc/netdata/custom-notify.sh` — shell script that POSTs to ntfy
- `/etc/netdata/health.d/km_track.conf` — custom health rules

### Alert Rules (4 rules)

| Rule | Metric | Threshold | Severity |
|------|--------|-----------|----------|
| `km_track_cpu_high` | `system.cpu` user+system | > 80% for 3 min | WARNING |
| `km_track_ram_high` | `mem.ram` used | > 75% | WARNING |
| `km_track_service_down` | `systemdunits_service-units.unit_km_track_service_state` | not active | CRITICAL |
| `redis_down` | `redis_local.operations` | no data 30s | CRITICAL |

Cooldown: 15 minutes between repeat notifications for the same rule.

### Custom Notify Script

`/etc/netdata/custom-notify.sh` receives Netdata environment variables and POSTs to ntfy:

```bash
#!/bin/bash
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
```

### health_alarm_notify.conf

```
SEND_CUSTOM=YES
DEFAULT_RECIPIENT_CUSTOM="admin"
CUSTOM_SENDER_ENABLED=YES
```

## Part 2: Focused Dashboard (6 charts)

Created via Netdata UI → Dashboard tab → New Dashboard named "Race Day".

| Tile | Chart ID | Why |
|------|----------|-----|
| CPU utilization | `system.cpu` | Overall CPU load |
| RAM used | `mem.ram` | Memory pressure |
| km_track RAM | `systemd_km_track.mem` | App-specific memory |
| TCP sockets | `ip.sockstat_sockets` | Real SSE connection count (kernel-level) |
| nginx requests/s | `web_log_nginx.requests_total` | HTTP traffic rate |
| Redis ops/s | `redis_local.operations` | Redis load |

## What We Don't Change

- `collector.py` ntfy code — left as-is (continues writing CSV history)
- Netdata Cloud — not connected
- Disk/network alerts — not configured (not critical for SSE workload)

## Verification

1. `netdatacli reload-health` — no errors
2. Test alert: `netdatacli send-test-alarm` → ntfy notification arrives
3. Dashboard visible at `https://analytics.krasmarafon.ru/netdata/` → Dashboard tab
4. TCP sockets chart shows non-zero ESTABLISHED connections
