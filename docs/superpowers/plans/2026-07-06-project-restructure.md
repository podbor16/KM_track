# Project Restructure: Multi-Domain Routing + Folder Organisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monolithic FastAPI app into three logically isolated domains — `krasmarafon` (tracker/analytics), `race_triatleta` (24h велогонка, дуатлон 222), `siberman` (ультратриатлон) — each served on its own domain with correct routing, without breaking existing URLs.

**Architecture:** Single FastAPI process, single deployment. Domain middleware reads the `Host` header and sets `request.state.domain`. Each product has its own `src/<product>/` module tree, `templates/<product>/` subfolder, and router. `app.py` routes by domain. Nginx already splits traffic per domain; we add `live.siberman515.com` block.

**Tech Stack:** FastAPI, Jinja2Templates, nginx, Python 3.13, MySQL (existing DB setup), GitHub Actions CI/CD.

---

## File Map

### Created
| File | Purpose |
|------|---------|
| `src/siberman/__init__.py` | Module marker |
| `src/siberman/db.py` | `get_siberman_connection()` — same pattern as triatleta |
| `src/siberman/router.py` | Siberman routes (placeholder `/` → index) |
| `templates/race_triatleta/index.html` | Triatleta landing — «24 часа» vs «222 Дуатлон» |
| `templates/siberman/index.html` | Siberman placeholder page |

### Moved (git mv)
| From | To |
|------|----|
| `templates/tracker.html` | `templates/krasmarafon/tracker.html` |
| `templates/start_list.html` | `templates/krasmarafon/start_list.html` |
| `templates/results.html` | `templates/krasmarafon/results.html` |
| `templates/history.html` | `templates/krasmarafon/history.html` |
| `templates/athlete-profile.html` | `templates/krasmarafon/athlete-profile.html` |
| `templates/race-analysis.html` | `templates/krasmarafon/race-analysis.html` |
| `templates/login.html` | `templates/krasmarafon/login.html` |
| `templates/admin.html` | `templates/krasmarafon/admin.html` |
| `templates/business-analytics.html` | `templates/krasmarafon/business-analytics.html` |
| `templates/header.html` | `templates/krasmarafon/header.html` |
| `templates/krasmarafon_header.html` | `templates/krasmarafon/krasmarafon_header.html` |
| `templates/krasmarafon_footer.html` | `templates/krasmarafon/krasmarafon_footer.html` |
| `templates/tri_results.html` | `templates/race_triatleta/tri_results.html` |
| `templates/tri_admin.html` | `templates/race_triatleta/tri_admin.html` |
| `src/tracker/` (entire dir) | `src/krasmarafon/` |
| `src/triatleta/` (entire dir) | `src/race_triatleta/` |

### Modified
| File | Change |
|------|--------|
| `app.py` | Add domain middleware; update imports `src.tracker→src.krasmarafon` |
| `src/krasmarafon/router.py` | Update triatleta import `src.triatleta→src.race_triatleta`; add siberman router |
| `src/krasmarafon/routers/pages.py` | Domain-aware `/` handler; update all template paths to `krasmarafon/` |
| `src/krasmarafon/routers/api.py` | Update all internal `src.tracker→src.krasmarafon` imports |
| `src/krasmarafon/routers/admin.py` | Update internal imports |
| `src/krasmarafon/routers/webhook.py` | Update internal imports |
| `src/krasmarafon/services/results_service.py` | Update internal imports |
| `src/race_triatleta/router.py` | Update template path; update internal imports |
| `src/race_triatleta/service.py` | Update internal imports |
| `src/race_triatleta/db.py` | Update internal imports |
| `tests/unit/test_pace_calculator.py` | `src.tracker→src.krasmarafon` |
| `tests/unit/test_routes_service.py` | `src.tracker→src.krasmarafon` |
| `tests/unit/test_runners_service.py` | `src.tracker→src.krasmarafon` |
| `tests/unit/test_tilda_webhook.py` | `src.tracker→src.krasmarafon` |
| `tests/unit/test_tri_service.py` | `src.triatleta→src.race_triatleta` |
| `deploy/nginx.conf` | Add `live.siberman515.com` server block |
| `.env` | Add `SIBERMAN_DB_NAME=siberman` |

---

## Task 1: Domain middleware in app.py

**Files:**
- Modify: `app.py`

This middleware runs before every request and stamps `request.state.domain` with one of `"krasmarafon"`, `"triatleta"`, `"siberman"`. The rest of the app reads this to choose templates and behaviour.

- [ ] **Step 1: Add domain middleware**

In `app.py`, immediately after the existing `log_request_duration` middleware, add:

```python
@app.middleware("http")
async def domain_middleware(request: Request, call_next):
    host = request.headers.get("host", "").lower().split(":")[0]
    if "triatleta" in host:
        request.state.domain = "triatleta"
    elif "siberman" in host:
        request.state.domain = "siberman"
    else:
        request.state.domain = "krasmarafon"
    return await call_next(request)
```

- [ ] **Step 2: Verify app still starts**

```bash
conda run -n base python -c "import app; print('ok')"
```
Expected: `ok` (no import errors)

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add domain middleware (krasmarafon/triatleta/siberman)"
```

---

## Task 2: Move templates into product subfolders

**Files:**
- Move: all templates listed in File Map above
- Modify: `src/tracker/routers/pages.py` (template paths)
- Modify: `src/triatleta/router.py` (template paths)

`Jinja2Templates(directory="templates")` already points to the root — subfolder paths like `krasmarafon/tracker.html` work automatically.

- [ ] **Step 1: Create target dirs and git mv KM templates**

```bash
mkdir -p templates/krasmarafon templates/race_triatleta templates/siberman
git mv templates/tracker.html           templates/krasmarafon/tracker.html
git mv templates/start_list.html        templates/krasmarafon/start_list.html
git mv templates/results.html           templates/krasmarafon/results.html
git mv templates/history.html           templates/krasmarafon/history.html
git mv "templates/athlete-profile.html" "templates/krasmarafon/athlete-profile.html"
git mv "templates/race-analysis.html"   "templates/krasmarafon/race-analysis.html"
git mv templates/login.html             templates/krasmarafon/login.html
git mv templates/admin.html             templates/krasmarafon/admin.html
git mv "templates/business-analytics.html" "templates/krasmarafon/business-analytics.html"
git mv templates/header.html            templates/krasmarafon/header.html
git mv templates/krasmarafon_header.html templates/krasmarafon/krasmarafon_header.html
git mv templates/krasmarafon_footer.html templates/krasmarafon/krasmarafon_footer.html
git mv templates/tri_results.html       templates/race_triatleta/tri_results.html
git mv templates/tri_admin.html         templates/race_triatleta/tri_admin.html
```

- [ ] **Step 2: Update TemplateResponse paths in pages.py**

In `src/tracker/routers/pages.py`, replace every template name string with the `krasmarafon/` prefix:

| Before | After |
|--------|-------|
| `"tracker.html"` | `"krasmarafon/tracker.html"` |
| `"start_list.html"` | `"krasmarafon/start_list.html"` |
| `"results.html"` | `"krasmarafon/results.html"` |
| `"history.html"` | `"krasmarafon/history.html"` |
| `"athlete-profile.html"` | `"krasmarafon/athlete-profile.html"` |
| `"race-analysis.html"` | `"krasmarafon/race-analysis.html"` |
| `"login.html"` | `"krasmarafon/login.html"` |
| `"admin.html"` | `"krasmarafon/admin.html"` |
| `"server-metrics.html"` | `"krasmarafon/server-metrics.html"` |

Check for the dynamic template at line ~226 and update it too.

- [ ] **Step 3: Update TemplateResponse paths in triatleta router**

In `src/triatleta/router.py`:

```python
# line ~48
return templates.TemplateResponse("race_triatleta/tri_results.html", {
# line ~78
return templates.TemplateResponse("race_triatleta/tri_admin.html", {"request": request})
```

- [ ] **Step 4: Check for Jinja2 {% include %} or {% extends %} references inside templates**

```bash
grep -rn "include\|extends" templates/krasmarafon/ templates/race_triatleta/ | grep -v ".git"
```

If any template references another template by old path (e.g. `{% include 'header.html' %}`), update those paths to `krasmarafon/header.html`.

- [ ] **Step 5: Run unit tests to verify no breakage**

```bash
conda run -n base python -m pytest tests/unit/ -v
```
Expected: all pass (unit tests don't exercise templates)

- [ ] **Step 6: Commit**

```bash
git add templates/ src/tracker/routers/pages.py src/triatleta/router.py
git commit -m "refactor: move templates into krasmarafon/ and race_triatleta/ subfolders"
```

---

## Task 3: Domain-aware `/` route + Triatleta landing page

**Files:**
- Modify: `src/tracker/routers/pages.py` — `/` handler
- Create: `templates/race_triatleta/index.html`
- Create: `templates/siberman/index.html`

- [ ] **Step 1: Create Triatleta landing page**

Create `templates/race_triatleta/index.html`:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Triatleta — Выберите гонку</title>
    <link rel="stylesheet" href="/static/css/tri_results.css?v={{ v }}">
    <style>
        body { background: #f5f5f5; font-family: 'Onest', system-ui, sans-serif; margin: 0; }
        .tri-header { background: #1a1a1a; color: #fff; padding: 20px 24px; }
        .tri-header__eyebrow { font-size: 11px; color: #999; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; }
        .tri-header__title { font-size: 22px; font-weight: 800; }
        .race-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; padding: 32px 24px; max-width: 800px; margin: 0 auto; }
        .race-card { background: #fff; border-radius: 12px; padding: 28px; box-shadow: 0 1px 4px rgba(0,0,0,.08); text-decoration: none; color: inherit; border: 2px solid transparent; transition: border-color .15s, box-shadow .15s; display: block; }
        .race-card:hover { border-color: #c0392b; box-shadow: 0 4px 16px rgba(192,57,43,.15); }
        .race-card--disabled { opacity: 0.45; pointer-events: none; }
        .race-card__label { font-size: 11px; color: #999; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
        .race-card__title { font-size: 20px; font-weight: 800; color: #1a1a1a; line-height: 1.2; margin-bottom: 6px; }
        .race-card__sub { font-size: 13px; color: #666; }
        .race-card__arrow { margin-top: 20px; font-size: 13px; color: #c0392b; font-weight: 600; }
        .race-card--disabled .race-card__arrow { color: #999; }
        .soon-badge { display: inline-block; background: #f0f0f0; color: #888; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 20px; margin-top: 12px; }
    </style>
</head>
<body>
    <div class="tri-header">
        <div class="tri-header__eyebrow">Triatleta · Красноярск</div>
        <div class="tri-header__title">Выберите гонку</div>
    </div>

    <div class="race-grid">
        <a href="/24h" class="race-card">
            <div class="race-card__label">Велогонка</div>
            <div class="race-card__title">24 часа<br>Суточная велогонка</div>
            <div class="race-card__sub">25–26 июня 2026 · Красноярск</div>
            <div class="race-card__arrow">Результаты и статистика →</div>
        </a>

        <div class="race-card race-card--disabled">
            <div class="race-card__label">Дуатлон</div>
            <div class="race-card__title">222<br>Дуатлон</div>
            <div class="race-card__sub">Скоро</div>
            <div class="soon-badge">Скоро</div>
            <div class="race-card__arrow">В разработке</div>
        </div>
    </div>
</body>
</html>
```

- [ ] **Step 2: Create Siberman placeholder page**

Create `templates/siberman/index.html`:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Siberman 515 — Live</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0d1117; color: #e6edf3; font-family: system-ui, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
        .wrap { text-align: center; padding: 40px 24px; }
        .logo { font-size: 48px; font-weight: 900; letter-spacing: -2px; color: #fff; margin-bottom: 8px; }
        .logo span { color: #e85d04; }
        .sub { font-size: 14px; color: #8b949e; margin-bottom: 32px; }
        .badge { display: inline-block; background: rgba(232,93,4,.15); color: #e85d04; border: 1px solid rgba(232,93,4,.3); border-radius: 20px; padding: 6px 18px; font-size: 13px; font-weight: 600; }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="logo">SIBER<span>MAN</span></div>
        <div class="sub">515 · Ультратриатлон · Сибирь</div>
        <div class="badge">Live-трекер в разработке</div>
    </div>
</body>
</html>
```

- [ ] **Step 3: Make `/` domain-aware in pages.py**

In `src/tracker/routers/pages.py`, replace the current `/` handler:

```python
@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    domain = getattr(request.state, "domain", "krasmarafon")
    if domain == "triatleta":
        return templates.TemplateResponse("race_triatleta/index.html",
                                          {"request": request, "v": _get_deploy_version()})
    if domain == "siberman":
        return templates.TemplateResponse("siberman/index.html", {"request": request})
    return await _tracker_response(request)
```

- [ ] **Step 4: Run unit tests**

```bash
conda run -n base python -m pytest tests/unit/ -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add templates/race_triatleta/index.html templates/siberman/index.html src/tracker/routers/pages.py
git commit -m "feat: domain-aware / route + triatleta landing + siberman placeholder"
```

---

## Task 4: Rename src/tracker/ → src/krasmarafon/

**Files:**
- Move: entire `src/tracker/` tree → `src/krasmarafon/`
- Modify: all `src.tracker` import strings (8 external files + all internal files in the moved dir)

- [ ] **Step 1: Git mv the directory**

```bash
git mv src/tracker src/krasmarafon
```

- [ ] **Step 2: Fix all external imports (files outside the moved dir)**

Replace `src.tracker` → `src.krasmarafon` in these files:

```bash
# app.py (4 occurrences)
sed -i 's/src\.tracker\./src.krasmarafon./g' app.py

# test files (4 files)
sed -i 's/src\.tracker\./src.krasmarafon./g' \
    tests/unit/test_pace_calculator.py \
    tests/unit/test_routes_service.py \
    tests/unit/test_runners_service.py \
    tests/unit/test_tilda_webhook.py
```

- [ ] **Step 3: Fix all internal imports inside src/krasmarafon/**

```bash
# All .py files inside the renamed directory still reference src.tracker
find src/krasmarafon -name "*.py" | xargs sed -i 's/src\.tracker\./src.krasmarafon./g'
```

- [ ] **Step 4: Fix triatleta import in router.py**

`src/krasmarafon/router.py` line 19 still says `from src.triatleta.router`. Leave it for now — Task 6 fixes this.

- [ ] **Step 5: Verify no remaining src.tracker references**

```bash
grep -rn "src\.tracker" --include="*.py" . | grep -v __pycache__
```
Expected: no output (zero matches).

- [ ] **Step 6: Run unit tests**

```bash
conda run -n base python -m pytest tests/unit/ -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: rename src/tracker → src/krasmarafon, update all imports"
```

---

## Task 5: Rename src/triatleta/ → src/race_triatleta/

**Files:**
- Move: entire `src/triatleta/` tree → `src/race_triatleta/`
- Modify: all `src.triatleta` import strings

- [ ] **Step 1: Git mv the directory**

```bash
git mv src/triatleta src/race_triatleta
```

- [ ] **Step 2: Fix external imports**

```bash
# src/krasmarafon/router.py (line 19)
sed -i 's/src\.triatleta\./src.race_triatleta./g' src/krasmarafon/router.py

# test file
sed -i 's/src\.triatleta\./src.race_triatleta./g' tests/unit/test_tri_service.py
```

- [ ] **Step 3: Fix internal imports inside src/race_triatleta/**

```bash
find src/race_triatleta -name "*.py" | xargs sed -i 's/src\.triatleta\./src.race_triatleta./g'
```

- [ ] **Step 4: Verify no remaining src.triatleta references**

```bash
grep -rn "src\.triatleta" --include="*.py" . | grep -v __pycache__
```
Expected: no output.

- [ ] **Step 5: Run unit tests**

```bash
conda run -n base python -m pytest tests/unit/ -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: rename src/triatleta → src/race_triatleta, update all imports"
```

---

## Task 6: Create src/siberman/ skeleton

**Files:**
- Create: `src/siberman/__init__.py`
- Create: `src/siberman/db.py`
- Create: `src/siberman/router.py`
- Modify: `src/krasmarafon/router.py` — include siberman router

- [ ] **Step 1: Create src/siberman/__init__.py**

```python
```
(empty file)

- [ ] **Step 2: Create src/siberman/db.py**

```python
import os
import mysql.connector
from typing import Optional


def get_siberman_connection() -> Optional[mysql.connector.MySQLConnection]:
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("SIBERMAN_DB_NAME", "siberman"),
            user=os.getenv("DB_USER", "km_analytic"),
            password=os.getenv("DB_PASSWORD"),
            charset="utf8mb4",
            autocommit=True,
            connection_timeout=10,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"❌ siberman connect error: {e}")
        return None
```

- [ ] **Step 3: Create src/siberman/router.py**

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
router = APIRouter(tags=["Siberman"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
```
(No routes yet — the `/` route is handled domain-aware in krasmarafon/routers/pages.py)

- [ ] **Step 4: Include siberman router in main router**

In `src/krasmarafon/router.py`, add after the triatleta include:

```python
from src.siberman.router import router as siberman_router
router.include_router(siberman_router)
```

- [ ] **Step 5: Run unit tests**

```bash
conda run -n base python -m pytest tests/unit/ -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/siberman/ src/krasmarafon/router.py
git commit -m "feat: add src/siberman skeleton (db, router, placeholder page)"
```

---

## Task 7: Nginx + .env for live.siberman515.com

**Files:**
- Modify: `deploy/nginx.conf`
- Modify: `.env` (local only, not committed)

- [ ] **Step 1: Add siberman block to nginx.conf**

In `deploy/nginx.conf`, add after the `live-race.triatleta.ru` server blocks:

```nginx
# ---- live.siberman515.com ----
server {
    listen 80;
    server_name live.siberman515.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name live.siberman515.com;

    # SSL cert is issued after DNS propagation:
    # certbot --nginx -d live.siberman515.com
    ssl_certificate     /etc/letsencrypt/live/live.siberman515.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/live.siberman515.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location /static/ {
        alias /opt/km_track/static/;
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
    }

    location / {
        proxy_pass          http://127.0.0.1:8000;
        proxy_set_header    Host $host;
        proxy_set_header    X-Real-IP $remote_addr;
        proxy_set_header    X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header    X-Forwarded-Proto $scheme;
        proxy_read_timeout  60s;
        add_header          Cache-Control "no-store";
        gzip                on;
        gzip_types          text/plain application/json text/css application/javascript;
        gzip_min_length     500;
    }

    access_log /var/log/nginx/siberman_access.log;
    error_log  /var/log/nginx/siberman_error.log;
}
```

> **Note:** The 443 block will cause nginx -t to FAIL until the SSL cert is issued. Keep it commented out until DNS for `live.siberman515.com` is pointed at the VPS and `certbot --nginx -d live.siberman515.com` is run. Uncomment the 443 block after cert is issued.

- [ ] **Step 2: Add SIBERMAN_DB_NAME to .env**

In `.env` (local file, not committed), add:

```
SIBERMAN_DB_NAME=siberman
```

- [ ] **Step 3: Add the env var to GitHub Actions secrets** (manual step)

In GitHub repo → Settings → Secrets → Actions, add:
- Name: `SIBERMAN_DB_NAME`
- Value: `siberman`

Then in `.github/workflows/*.yml`, add to the env section:
```yaml
SIBERMAN_DB_NAME: ${{ secrets.SIBERMAN_DB_NAME }}
```

- [ ] **Step 4: Commit nginx.conf**

```bash
git add deploy/nginx.conf
git commit -m "feat: add live.siberman515.com nginx block (SSL pending DNS)"
```

---

## Task 8: Final verification + deploy

- [ ] **Step 1: Run full unit test suite**

```bash
conda run -n base python -m pytest tests/unit/ -v
```
Expected: all pass.

- [ ] **Step 2: Verify app import**

```bash
conda run -n base python -c "import app; print('import ok')"
```
Expected: `import ok`

- [ ] **Step 3: Verify no stale references**

```bash
grep -rn "src\.tracker\|src\.triatleta" --include="*.py" . | grep -v __pycache__
```
Expected: no output.

```bash
grep -rn '"tracker\.html"\|"tri_results\.html"\|"tri_admin\.html"' --include="*.py" . | grep -v __pycache__
```
Expected: no output (all paths should have subfolder prefix now).

- [ ] **Step 4: Push to deploy**

```bash
git push origin main
```

CI/CD (GitHub Actions) will run `pytest tests/unit/ -v`, then deploy to VPS via SSH.

- [ ] **Step 5: Post-deploy smoke test**

```
curl -s -o /dev/null -w "%{http_code}" https://analytics.krasmarafon.ru/
# Expected: 200

curl -s -o /dev/null -w "%{http_code}" https://live-race.triatleta.ru/
# Expected: 200 (triatleta landing page)

curl -s -o /dev/null -w "%{http_code}" https://live-race.triatleta.ru/24h
# Expected: 200 (unchanged)

curl -s -o /dev/null -w "%{http_code}" https://analytics.krasmarafon.ru/health
# Expected: 200
```

---

## Post-deploy: Siberman SSL setup

После того как DNS запись `live.siberman515.com` будет указывать на VPS:

```bash
# На VPS (через SSH):
certbot --nginx -d live.siberman515.com
# Certbot автоматически обновит nginx.conf с путями к сертификату

systemctl reload nginx
```

Затем раскомментировать 443-блок в `deploy/nginx.conf` и закоммитить.
