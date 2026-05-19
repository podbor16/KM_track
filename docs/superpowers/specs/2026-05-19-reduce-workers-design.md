# Reduce Uvicorn Workers 3→2 — Design Spec

## Context

Idle RAM usage: ~70% (2078 MB / 2972 MB). Three uvicorn workers consume ~1335 MB RSS combined (~445 MB each). After delta SSE optimisation (commit `70dab62`), SSE broadcasting is now CPU-light (0–5 KB delta per 2s instead of 1.5 MB full payload). Two workers are sufficient for the expected production load.

## Goal

Reduce idle RAM from ~70% to ~55%, giving ~500 MB headroom for production day (race with 3000 participants, up to 5000 SSE connections, 50–150 HTTP req/s peak).

## Changes

### 1. `/etc/systemd/system/km_track.service` (VPS only, not in repo)
```
--workers 2   # was: --workers 3
```

### 2. `app.py` line 93–94
```python
# pool_size=2: 2 workers × 2 = 4 connections < max_connections=20
pool = initialize_connection_pool(pool_size=2)
```

## Rationale

- 2 async uvicorn workers handle 5000 SSE connections (asyncio, not threading — connections share the event loop, not processes)
- 50–150 HTTP req/s is well within 2-worker capacity (load test showed ~40 req/s per worker at 200 VUs)
- MySQL pool: 4 total connections (was 9) — well within max_connections=20
- No architecture changes; no new components

## Expected Result

| Metric | Before | After |
|--------|--------|-------|
| Workers | 3 | 2 |
| MySQL connections | 9 | 4 |
| Idle RAM | ~70% | ~55% |
| RAM at 5000 SSE | ~80% | ~65% |

## Verification

1. `systemctl status km_track` — 2 worker PIDs instead of 3
2. `free -m` — `used` drops ~400 MB
3. `curl /health` → `{"status": "ok"}`
4. SSE connection on tracker page — connects and receives data
