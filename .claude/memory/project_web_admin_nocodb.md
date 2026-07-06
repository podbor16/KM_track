---
name: project-web-admin-nocodb
description: Идея веб-интерфейса для нетехнических администраторов БД — NocoDB поверх MySQL
metadata:
  type: project
---

NocoDB запланирован как веб-интерфейс в стиле Google Sheets/Airtable для нетехнических администраторов KM_track.

**Why:** Администраторы без знания SQL будут работать с таблицами (leads, clients, results). DBeaver требует SSH-туннель и сложен. NocoDB даёт spreadsheet-like UI поверх существующей MySQL без дублирования данных.

**How to apply:** Когда придёт время — развернуть NocoDB через Docker на VPS (`--network host`, порт 8880), проксировать nginx на `/db/` с basic auth (`DB_ADMIN_PASSWORD` в .env). Детальный план был написан 2026-05-20, включал `deploy/ssh_install_nocodb.py`, `deploy/ssh_nginx_nocodb.py`, обновление `nginx.conf` и `.env.example`.

RAM overhead: ~200–400 MB (приемлемо, baseline VPS 332 MB при 3 GB RAM).
