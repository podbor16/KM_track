---
name: reference-gh-cli
description: gh CLI установлен и авторизован локально — использовать для диагностики GitHub Actions/PR вместо предположений
metadata:
  type: reference
---

`gh` CLI установлен через winget (`C:\Program Files\GitHub CLI\gh.exe`) и авторизован под аккаунтом `podbor16` (2026-07-09). PATH подхватывается только в новых окнах терминала — если `gh` не находится, звать по полному пути.

Полезные команды для KM_track:
- `gh run list --limit N` — последние workflow-раны
- `gh run view <id>` — статус джобов конкретного рана
- `gh run view <id> --job=<job-id>` / `gh run view --log-failed` — логи упавшего джоба
- `gh api repos/podbor16/KM_track/actions/jobs/<id>` — сырые данные джоба (status/conclusion/started_at), когда `gh run view` не даёт деталей

**Why:** раньше не было способа проверить статус GH Actions кроме скриншотов от пользователя — теперь можно диагностировать самостоятельно (например, зависшие в Queued деплои).
**How to apply:** при жалобах на зависший/упавший CI — сначала `gh run list`/`gh run view`, прежде чем просить скриншот или гадать.
