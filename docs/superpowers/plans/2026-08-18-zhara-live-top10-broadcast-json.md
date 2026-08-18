# Live-топ-10 по отметкам для трансляции Жары — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Обновляемый в реальном времени JSON-файл с топ-10 участников (абсолют/муж/жен) на каждой отметке дистанций «5 км» и «21.1 км» Жары — для вывода в эфир режиссёром трансляции.

**Architecture:** Новый модуль `live_top10_export.py` собирает данные из уже населяемой live-таблицы `results` (через `load_race_results.py --continuous`) и атомарно перезаписывает JSON-файл после каждого цикла опроса Copernico. Новая таблица `participant_photos` + маленькая admin-форма — для ручного ввода ссылок на фото элитного кластера (у остальных — заглушка). Файл раздаётся nginx без кэша, вне `/static/`.

**Tech Stack:** Python 3.13, mysql-connector (без ORM), FastAPI (admin API), pytest, nginx.

**Спека:** `docs/superpowers/specs/2026-08-18-zhara-live-top10-broadcast-json-design.md` — прочитать целиком перед реализацией, там обоснования всех решений.

---

## File Structure

- Create: `migrations/create_participant_photos.sql`
- Create: `src/krasmarafon/models/participant_photos.py`
- Modify: `src/analytics/db_results.py` — новые функции CRUD в конце файла
- Modify: `src/krasmarafon/routers/admin.py` — новые endpoints
- Modify: `templates/krasmarafon/admin.html` — новая вкладка «Фото участников»
- Create: `static/images/krasmarafon/participant-placeholder.png`
- Create: `src/krasmarafon/services/live_top10_export.py` — вся логика сборки JSON
- Modify: `load_race_results.py` — CLI-флаг `--broadcast-json`, хук в `RaceLoader`
- Modify: `deploy/run_loader.sh` — опциональный `LOADER_BROADCAST_JSON`
- Modify: `deploy/nginx.conf` — новый `location /live/`
- Create: `tests/unit/test_participant_photos.py`
- Create: `tests/unit/test_live_top10_export.py`
- Modify: `tests/unit/test_race_loader_ranks.py` — тест на изоляцию ошибок хука (или новый файл `tests/unit/test_race_loader_broadcast_hook.py` — см. Task 8)

---

### Task 1: Миграция `participant_photos`

**Files:**
- Create: `migrations/create_participant_photos.sql`

- [ ] **Step 1: Написать миграцию**

```sql
-- Ссылки на фото участников для live-топ-10 трансляции Жары. Заполняется
-- вручную через /admin — организатор один раз до гонки переносит ссылки из
-- анкеты элитного кластера (внешняя гугл-форма, синхронизация с ней вне
-- объёма). У кого нет записи здесь — в JSON подставляется общая заглушка
-- (см. src/krasmarafon/services/live_top10_export.py).
-- 2026-08-18

CREATE TABLE IF NOT EXISTS participant_photos (
  id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  event_id INT UNSIGNED NOT NULL,
  start_number INT UNSIGNED NOT NULL,
  photo_url VARCHAR(500) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_participant_photo (event_id, start_number)
);
```

- [ ] **Step 2: Применить на проде**

Run: `conda run -n base python -m deploy.ssh_apply_migrations migrations/create_participant_photos.sql`
Expected: `OK: CREATE TABLE ...`, в списке индексов в конце появится `participant_photos.uq_participant_photo: (event_id,start_number)`.

- [ ] **Step 3: Commit**

```bash
git add migrations/create_participant_photos.sql
git commit -m "feat(krasmarafon): таблица participant_photos для live-топ-10 трансляции"
```

---

### Task 2: DB-слой — CRUD для `participant_photos` + список событий

**Files:**
- Modify: `src/analytics/db_results.py` (добавить в конец файла, после существующего `delete_age_group`/`calculate_age_group`, порядок неважен — но проще всего в самый конец файла)
- Test: `tests/unit/test_participant_photos.py`

- [ ] **Step 1: Написать падающие тесты**

```python
"""Тесты для CRUD-функций participant_photos (ссылки на фото для
live-топ-10 трансляции Жары) и list_db_events() (числовой event_id для
селектора в /admin)."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import (
    list_db_events, list_participant_photos,
    upsert_participant_photo, delete_participant_photo,
)


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


@patch("src.analytics.db_results.get_pooled_connection")
def test_list_db_events_returns_rows(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"id": 116, "event_name": "Жара", "event_distance": 21.1, "event_year": 2026},
    ]

    result = list_db_events()

    assert result == [{"id": 116, "event_name": "Жара", "event_distance": 21.1, "event_year": 2026}]


@patch("src.analytics.db_results.get_pooled_connection")
def test_list_participant_photos_filters_by_event(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"id": 1, "event_id": 116, "start_number": 245, "photo_url": "https://example.com/a.jpg"},
    ]

    result = list_participant_photos(116)

    assert len(result) == 1
    select_call = cur.execute.call_args_list[0]
    assert "event_id = %s" in select_call.args[0]
    assert select_call.args[1] == (116,)


@patch("src.analytics.db_results.get_pooled_connection")
def test_upsert_participant_photo_returns_saved_row(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = {
        "id": 7, "event_id": 116, "start_number": 245, "photo_url": "https://example.com/a.jpg",
    }

    result = upsert_participant_photo(116, 245, "https://example.com/a.jpg")

    assert result["id"] == 7
    assert result["photo_url"] == "https://example.com/a.jpg"
    conn.commit.assert_called_once()
    insert_call = cur.execute.call_args_list[0]
    assert "ON DUPLICATE KEY UPDATE" in insert_call.args[0]


@patch("src.analytics.db_results.get_pooled_connection")
def test_delete_participant_photo_returns_true_on_success(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.rowcount = 1

    assert delete_participant_photo(7) is True
    conn.commit.assert_called_once()


@patch("src.analytics.db_results.get_pooled_connection")
def test_delete_participant_photo_returns_false_when_not_found(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.rowcount = 0

    assert delete_participant_photo(999) is False
```

- [ ] **Step 2: Убедиться, что тест падает (функции ещё не существуют)**

Run: `conda run -n base python -m pytest tests/unit/test_participant_photos.py -v`
Expected: `ImportError: cannot import name 'list_db_events' from 'src.analytics.db_results'`

- [ ] **Step 3: Реализовать функции**

Добавить в конец `src/analytics/db_results.py`:

```python
def list_db_events() -> List[Dict[str, Any]]:
    """Список событий из таблицы events (числовой id + человекочитаемые
    поля) — для выбора конкретного event_id в админке (напр. вкладка «Фото
    участников»), где нужен именно ID, а не event_name/event_distance
    строки, как в age_group_configs."""
    conn = get_pooled_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(
            "SELECT id, event_name, event_distance, event_year FROM events "
            "ORDER BY event_year DESC, event_name, event_distance"
        )
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"list_db_events error: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def list_participant_photos(event_id: int) -> List[Dict[str, Any]]:
    conn = get_pooled_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(
            "SELECT * FROM participant_photos WHERE event_id = %s ORDER BY start_number",
            (event_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"list_participant_photos error: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def upsert_participant_photo(event_id: int, start_number: int, photo_url: str) -> Optional[Dict[str, Any]]:
    """INSERT ... ON DUPLICATE KEY UPDATE — форма в /admin всегда просто
    "сохраняет", не важно, новая это запись или правка существующей."""
    conn = get_pooled_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(
            "INSERT INTO participant_photos (event_id, start_number, photo_url) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE photo_url = VALUES(photo_url)",
            (event_id, start_number, photo_url),
        )
        conn.commit()
        cur.execute(
            "SELECT * FROM participant_photos WHERE event_id = %s AND start_number = %s",
            (event_id, start_number),
        )
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"upsert_participant_photo error: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def delete_participant_photo(photo_id: int) -> bool:
    conn = get_pooled_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor(buffered=True)
        cur.execute("DELETE FROM participant_photos WHERE id = %s", (photo_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        cur.close()
        return deleted
    except Exception as e:
        logger.error(f"delete_participant_photo error: {e}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass
```

- [ ] **Step 4: Прогнать тесты**

Run: `conda run -n base python -m pytest tests/unit/test_participant_photos.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/analytics/db_results.py tests/unit/test_participant_photos.py
git commit -m "feat(krasmarafon): CRUD для participant_photos + list_db_events"
```

---

### Task 3: Pydantic-модели

**Files:**
- Create: `src/krasmarafon/models/participant_photos.py`

- [ ] **Step 1: Создать модели**

```python
"""Pydantic-модели для фото участников live-топ-10 трансляции (admin API) —
см. src/analytics/db_results.py: list_db_events()/list_participant_photos()/
upsert_participant_photo()/delete_participant_photo()."""

from pydantic import BaseModel


class DbEvent(BaseModel):
    """Событие из таблицы events — для выбора event_id в /admin."""

    id: int
    event_name: str
    event_distance: float
    event_year: int


class ParticipantPhoto(BaseModel):
    """Одна ссылка на фото — ответ API."""

    id: int
    event_id: int
    start_number: int
    photo_url: str


class ParticipantPhotoUpsert(BaseModel):
    """Тело POST /api/admin/participant-photos."""

    event_id: int
    start_number: int
    photo_url: str
```

- [ ] **Step 2: Проверить, что модуль импортируется без ошибок**

Run: `conda run -n base python -c "from src.krasmarafon.models.participant_photos import DbEvent, ParticipantPhoto, ParticipantPhotoUpsert; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/krasmarafon/models/participant_photos.py
git commit -m "feat(krasmarafon): Pydantic-модели для participant_photos API"
```

---

### Task 4: Admin API endpoints

**Files:**
- Modify: `src/krasmarafon/routers/admin.py`

- [ ] **Step 1: Добавить импорт моделей**

В начало файла, рядом с существующим импортом `age_groups`:

```python
from src.krasmarafon.models.age_groups import AgeGroupConfig, AgeGroupCreate, AgeGroupPatch
from src.krasmarafon.models.participant_photos import DbEvent, ParticipantPhoto, ParticipantPhotoUpsert
```

- [ ] **Step 2: Добавить endpoints**

После существующего `delete_age_group_endpoint` (заканчивается строкой `return {"status": "ok"}` перед комментарием `@router.post("/api/admin/leads/import/upload")`), вставить:

```python
# Числовой event_id для вкладки «Фото участников» — age_group_configs
# использует event_name+event_distance строки, но participant_photos
# ссылается на реальный results.event_id, поэтому нужен отдельный список
# с настоящими ID.

@router.get("/api/admin/db-events")
async def list_db_events_endpoint(user: str = Depends(api_require_auth)) -> dict:
    from src.analytics.db_results import list_db_events

    rows = await asyncio.get_event_loop().run_in_executor(None, list_db_events)
    return {"items": [DbEvent.model_validate(r).model_dump() for r in rows]}


@router.get("/api/admin/participant-photos")
async def list_participant_photos_endpoint(
    event_id: int = Query(...), user: str = Depends(api_require_auth)
) -> dict:
    from src.analytics.db_results import list_participant_photos

    rows = await asyncio.get_event_loop().run_in_executor(
        None, lambda: list_participant_photos(event_id)
    )
    return {"items": [ParticipantPhoto.model_validate(r).model_dump() for r in rows]}


@router.post("/api/admin/participant-photos")
async def upsert_participant_photo_endpoint(
    body: ParticipantPhotoUpsert, user: str = Depends(api_require_auth)
) -> dict:
    from src.analytics.db_results import upsert_participant_photo

    saved = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: upsert_participant_photo(body.event_id, body.start_number, body.photo_url),
    )
    if saved is None:
        raise HTTPException(status_code=400, detail="Не удалось сохранить фото")
    return ParticipantPhoto.model_validate(saved).model_dump()


@router.delete("/api/admin/participant-photos/{photo_id}")
async def delete_participant_photo_endpoint(
    photo_id: int, user: str = Depends(api_require_auth)
) -> dict:
    from src.analytics.db_results import delete_participant_photo

    deleted = await asyncio.get_event_loop().run_in_executor(
        None, lambda: delete_participant_photo(photo_id)
    )
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Фото {photo_id} не найдено")
    return {"status": "ok"}
```

- [ ] **Step 3: Проверить регистрацию роутов локально**

Run:
```bash
conda run -n base python -m uvicorn app:app --port 8123 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8123/api/admin/db-events
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8123/api/admin/participant-photos?event_id=1
kill %1
```
Expected: `401` для обоих (не `404`) — подтверждает, что роуты зарегистрированы и требуют авторизацию, как и остальные `/api/admin/*`.

- [ ] **Step 4: Commit**

```bash
git add src/krasmarafon/routers/admin.py
git commit -m "feat(krasmarafon): admin API для participant_photos"
```

---

### Task 5: Admin UI — вкладка «Фото участников»

**Files:**
- Modify: `templates/krasmarafon/admin.html`

- [ ] **Step 1: Добавить кнопку вкладки**

После `<button class="admin-tab" onclick="switchTab('age-groups', this)">Возрастные группы</button>`:

```html
<button class="admin-tab" onclick="switchTab('photos', this)">Фото участников</button>
```

- [ ] **Step 2: Добавить разметку вкладки**

После `</div>` закрывающего `<div id="tab-age-groups" ...>` (перед комментарием вкладки «АНАЛИТИКА»):

```html
<!-- ================================================================ -->
<!-- ВКЛАДКА: ФОТО УЧАСТНИКОВ (live-топ-10 трансляции)                -->
<!-- ================================================================ -->
<div id="tab-photos" class="admin-tab-content" style="display:none">
    <div class="admin-section-note">
        Ссылки на фото участников для live-топ-10 трансляции Жары. У кого нет
        фото — в JSON автоматически подставляется общая заглушка. Номер
        участника — это стартовый номер (bib) из результатов, не номер заявки.
    </div>

    <div class="admin-leads-toolbar">
        <div class="admin-leads-filters">
            <select id="ph-event" class="admin-select" onchange="loadParticipantPhotos()">
                <option value="">— событие —</option>
            </select>
        </div>
    </div>

    <div id="photos-content">
        <div class="admin-loading">Выберите событие</div>
    </div>
</div>
```

- [ ] **Step 3: Добавить JS-функции**

После существующей функции `addAgeGroupRow` (перед следующим логическим блоком JS), добавить:

```javascript
async function loadPhotosTab() {
    const sel = document.getElementById('ph-event');
    try {
        const r = await fetch('/api/admin/db-events');
        if (!r.ok) return;
        const data = await r.json();
        data.items.forEach(ev => {
            const opt = document.createElement('option');
            opt.value = ev.id;
            opt.textContent = `${ev.event_name} ${ev.event_distance} км (${ev.event_year})`;
            sel.appendChild(opt);
        });
    } catch(e) { /* silent */ }
}

async function loadParticipantPhotos() {
    const eventId = document.getElementById('ph-event').value;
    const content = document.getElementById('photos-content');
    if (!eventId) {
        content.innerHTML = '<div class="admin-loading">Выберите событие</div>';
        return;
    }
    content.innerHTML = '<div class="admin-loading">Загрузка…</div>';
    try {
        const r = await fetch(`/api/admin/participant-photos?event_id=${eventId}`);
        const data = await r.json();
        renderParticipantPhotos(data.items);
    } catch(e) {
        content.innerHTML = `<div class="admin-error">Ошибка загрузки: ${e.message}</div>`;
    }
}

function renderParticipantPhotos(items) {
    const content = document.getElementById('photos-content');
    const rows = items.map(row => `
        <tr data-id="${row.id}">
            <td>${row.start_number}</td>
            <td><input type="text" class="admin-select ph-url" value="${row.photo_url}" style="width:320px"></td>
            <td>
                <button class="km-btn km-btn--secondary" onclick="saveParticipantPhotoRow(${row.start_number}, this)">Сохранить</button>
                <button class="km-btn km-btn--secondary" onclick="removeParticipantPhoto(${row.id})">Удалить</button>
            </td>
        </tr>
    `).join('');
    content.innerHTML = `
        <table class="admin-loader-table">
            <thead><tr><th>Номер</th><th>Ссылка на фото</th><th></th></tr></thead>
            <tbody>${rows || '<tr><td colspan="3">Фото ещё не добавлены</td></tr>'}</tbody>
        </table>
        <div class="admin-leads-toolbar" style="margin-top:8px">
            <input type="number" class="admin-select" id="ph-new-number" placeholder="Номер участника" style="width:140px">
            <input type="text" class="admin-select" id="ph-new-url" placeholder="Ссылка на фото" style="width:320px">
            <button class="km-btn km-btn--primary" onclick="addParticipantPhoto()">Сохранить</button>
        </div>
    `;
}

async function saveParticipantPhotoRow(startNumber, btn) {
    const tr = btn.closest('tr');
    const photo_url = tr.querySelector('.ph-url').value.trim();
    const eventId = parseInt(document.getElementById('ph-event').value, 10);
    if (!photo_url) { alert('Заполните ссылку'); return; }
    try {
        const r = await fetch('/api/admin/participant-photos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_id: eventId, start_number: startNumber, photo_url }),
        });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        loadParticipantPhotos();
    } catch(e) {
        alert('Ошибка сохранения: ' + e.message);
    }
}

async function removeParticipantPhoto(id) {
    if (!confirm('Удалить это фото?')) return;
    try {
        const r = await fetch(`/api/admin/participant-photos/${id}`, { method: 'DELETE' });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        loadParticipantPhotos();
    } catch(e) {
        alert('Ошибка удаления: ' + e.message);
    }
}

async function addParticipantPhoto() {
    const eventId = parseInt(document.getElementById('ph-event').value, 10);
    const start_number = parseInt(document.getElementById('ph-new-number').value, 10);
    const photo_url = document.getElementById('ph-new-url').value.trim();
    if (isNaN(start_number) || !photo_url) { alert('Заполните номер и ссылку'); return; }
    try {
        const r = await fetch('/api/admin/participant-photos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_id: eventId, start_number, photo_url }),
        });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        loadParticipantPhotos();
    } catch(e) {
        alert('Ошибка сохранения: ' + e.message);
    }
}
```

- [ ] **Step 4: Подключить вкладку в `switchTab()`**

Найти блок:
```javascript
            if (name === 'age-groups') loadAgeGroupsTab();
            if (name === 'analytics') loadAnalyticsTab();
```
Заменить на:
```javascript
            if (name === 'age-groups') loadAgeGroupsTab();
            if (name === 'photos') loadPhotosTab();
            if (name === 'analytics') loadAnalyticsTab();
```

- [ ] **Step 5: Визуальная проверка**

Run: `conda run -n base python -m uvicorn app:app --reload --port 8000` (или через уже запущенный dev-сервер), затем зайти в `/admin`, открыть вкладку «Фото участников», выбрать событие, добавить тестовую запись (например, номер 1, любая ссылка), убедиться, что строка появилась в таблице, удалить её.

- [ ] **Step 6: Commit**

```bash
git add templates/krasmarafon/admin.html
git commit -m "feat(krasmarafon): вкладка «Фото участников» в /admin"
```

---

### Task 6: Заглушка фото

**Files:**
- Create: `static/images/krasmarafon/participant-placeholder.png`

- [ ] **Step 1: Сгенерировать временную заглушку через PIL**

Run:
```bash
conda run -n base python -c "
from PIL import Image, ImageDraw, ImageFont
img = Image.new('RGB', (400, 400), color=(230, 230, 235))
draw = ImageDraw.Draw(img)
draw.ellipse((120, 90, 280, 250), fill=(200, 200, 210))
draw.ellipse((140, 250, 260, 400), fill=(200, 200, 210))
draw.text((200, 20), 'Фото не загружено', fill=(120, 120, 130), anchor='ma')
img.save('static/images/krasmarafon/participant-placeholder.png')
print('saved')
"
```
Expected: `saved`, файл `static/images/krasmarafon/participant-placeholder.png` появился.

Примечание: это временная заглушка (простой силуэт). Пользователь заменит файл реальной картинкой позже — путь `static/images/krasmarafon/participant-placeholder.png` при этом не меняется, весь остальной код ссылается только на путь, не на конкретное содержимое файла.

- [ ] **Step 2: Commit**

```bash
git add static/images/krasmarafon/participant-placeholder.png
git commit -m "feat(krasmarafon): временная заглушка фото участника"
```

---

### Task 7: Модуль сборки JSON — `live_top10_export.py`

**Files:**
- Create: `src/krasmarafon/services/live_top10_export.py`
- Test: `tests/unit/test_live_top10_export.py`

Это основной модуль задачи. Реализуется по частям — сначала чистые функции форматирования (без БД), затем `_build_checkpoint` (с мок-БД), затем `generate_top10_json` (оркестрация, тоже с мок-БД).

- [ ] **Step 1: Написать падающие тесты на чистые функции форматирования**

```python
"""Тесты для live_top10_export.py — сборка live-JSON топ-10 по отметкам
для трансляции Жары. TIME-поля MySQL (mysql-connector) приходят как
datetime.timedelta, не строки — см. _td_to_seconds()."""
from datetime import timedelta

from src.krasmarafon.services.live_top10_export import (
    _td_to_seconds, _seconds_to_hms, _seconds_to_pace_str, _format_gap,
    _sex_code, _format_distance_label,
)


def test_td_to_seconds_converts_timedelta():
    assert _td_to_seconds(timedelta(hours=1, minutes=2, seconds=3)) == 3723.0


def test_td_to_seconds_none_for_none():
    assert _td_to_seconds(None) is None


def test_seconds_to_hms_formats_with_leading_zeros():
    assert _seconds_to_hms(3723) == "01:02:03"


def test_seconds_to_hms_under_an_hour():
    assert _seconds_to_hms(125) == "00:02:05"


def test_seconds_to_pace_str_mmss():
    assert _seconds_to_pace_str(349) == "5:49"


def test_format_gap_leader_is_zero():
    assert _format_gap(0) == "Лидер"


def test_format_gap_negative_treated_as_leader():
    """Защита от округления/погрешности — небольшая отрицательная разница
    (сам лидер, сравнение с самим собой) не должна давать "-00:00"."""
    assert _format_gap(-0.4) == "Лидер"


def test_format_gap_under_an_hour():
    assert _format_gap(18) == "+00:18"


def test_format_gap_over_an_hour():
    assert _format_gap(3725) == "+01:02:05"


def test_sex_code_male():
    assert _sex_code("Мужчина") == "M"


def test_sex_code_female():
    assert _sex_code("Женщина") == "F"


def test_format_distance_label_drops_trailing_zero():
    assert _format_distance_label(5.0) == "5 км"


def test_format_distance_label_keeps_decimal():
    assert _format_distance_label(21.1) == "21.1 км"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -v`
Expected: `ModuleNotFoundError: No module named 'src.krasmarafon.services.live_top10_export'`

- [ ] **Step 3: Реализовать форматирующие функции**

Создать `src/krasmarafon/services/live_top10_export.py`:

```python
"""
Сборка live-JSON топ-10 участников по контрольным точкам для трансляции
Жары (5 км/21.1 км). Источник данных — таблица results, которую в реальном
времени населяет load_race_results.py --continuous (см. RaceLoader.
_maybe_write_broadcast_json() в load_race_results.py — точка вызова).

"Официальное" время/место на отметке = чистое время (time_clear_kt*,
rank_absolute_kt*/rank_sex_kt*) — на уровне промежуточных КТ в БД вообще
нет gun-time варианта, только на старте/финише. Для финиша сознательно
берутся _clean-поля (rank_absolute_clean/rank_sex_clean/
finish_pace_avg_clean), а не обычные rank_absolute/rank_sex — Жара в этом
сезоне награждает по чистому времени (см. коммит 9b1d549).

Полная схема JSON и обоснования решений — в
docs/superpowers/specs/2026-08-18-zhara-live-top10-broadcast-json-design.md.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

PARTICIPANT_PHOTO_PLACEHOLDER_URL = (
    "https://analytics.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"
)

_TOP_N = 10


def _td_to_seconds(value) -> Optional[float]:
    """MySQL TIME-поля (mysql-connector) приходят как datetime.timedelta,
    не строки — в отличие от load_race_results.py, который сам форматирует
    время в строки ПЕРЕД записью в БД. Здесь мы читаем уже сохранённые
    значения заново через отдельный SELECT, получая сырой driver-тип."""
    if value is None:
        return None
    if isinstance(value, timedelta):
        return value.total_seconds()
    return None


def _seconds_to_hms(seconds: float) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _seconds_to_pace_str(seconds: float) -> str:
    total = int(round(seconds))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _format_gap(seconds: float) -> str:
    """+ММ:СС (+ЧЧ:ММ:СС если ≥ часа), "Лидер" у первого места (0 или
    отрицательное — защита от погрешности округления при сравнении лидера
    с самим собой)."""
    if seconds <= 0:
        return "Лидер"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"+{h:02d}:{m:02d}:{s:02d}"
    return f"+{m:02d}:{s:02d}"


def _sex_code(sex_ru: str) -> str:
    return "M" if sex_ru == "Мужчина" else "F"


def _format_distance_label(distance_km: float) -> str:
    return f"{distance_km:g} км"
```

- [ ] **Step 4: Прогнать тесты форматирования**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -v`
Expected: 12 passed

- [ ] **Step 5: Написать падающий тест на `_build_checkpoint`**

Добавить в `tests/unit/test_live_top10_export.py`:

```python
from unittest.mock import MagicMock

from src.krasmarafon.services.live_top10_export import _build_checkpoint


def _row(start_number, surname, sex, city, rank_abs, rank_sex, time_str, pace_str):
    h, m, s = map(int, time_str.split(':'))
    ph, pm = map(int, pace_str.split(':'))
    return {
        "start_number": start_number, "surname": surname, "name": "Тест", "sex": sex,
        "city": city, "rank_absolute": rank_abs, "rank_sex": rank_sex,
        "time_clear": timedelta(hours=h, minutes=m, seconds=s),
        "pace_avg": timedelta(minutes=ph, seconds=pm),
    }


def test_build_checkpoint_splits_absolute_and_sex_with_shared_row_shape():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur

    abs_rows = [
        _row(10, "Иванов", "Мужчина", "Красноярск", 1, 1, "00:14:14", "5:41"),
        _row(20, "Петрова", "Женщина", "Москва", 2, 1, "00:14:32", "5:49"),
    ]
    male_rows = [abs_rows[0]]
    female_rows = [abs_rows[1]]
    # Порядок вызовов внутри _build_checkpoint: абсолют, мужчины, женщины
    cur.fetchall.side_effect = [abs_rows, male_rows, female_rows]

    photo_map = {10: "https://example.com/ivanov.jpg"}

    checkpoint = _build_checkpoint(
        conn, event_id=116, code="kt1", label="КТ1 (6.0 км)",
        time_col="time_clear_kt1", rank_abs_col="rank_absolute_kt1",
        rank_sex_col="rank_sex_kt1", pace_col="pace_avg_kt1",
        photo_map=photo_map,
    )

    assert checkpoint["code"] == "kt1"
    assert len(checkpoint["top10_absolute"]) == 2
    assert checkpoint["top10_absolute"][0]["gap_absolute"] == "Лидер"
    assert checkpoint["top10_absolute"][1]["gap_absolute"] == "+00:18"
    # Петрова — лидер СВОЕГО пола (единственная женщина в списке), хотя
    # вторая по абсолюту
    assert checkpoint["top10_absolute"][1]["gap_sex"] == "Лидер"
    assert checkpoint["top10_absolute"][0]["photo_url"] == "https://example.com/ivanov.jpg"
    assert checkpoint["top10_absolute"][1]["photo_url"] == (
        "https://analytics.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"
    )
    assert checkpoint["top10_absolute"][0]["sex"] == "M"
    assert checkpoint["top10_absolute"][1]["sex"] == "F"


def test_build_checkpoint_truncates_below_ten_without_padding():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    three_rows = [_row(i, f"Участник{i}", "Мужчина", "Красноярск", i, i, "00:10:0" + str(i), "4:0" + str(i)) for i in range(1, 4)]
    cur.fetchall.side_effect = [three_rows, three_rows, []]

    checkpoint = _build_checkpoint(
        conn, event_id=116, code="finish", label="Финиш",
        time_col="time_clear_finish", rank_abs_col="rank_absolute_clean",
        rank_sex_col="rank_sex_clean", pace_col="finish_pace_avg_clean",
        photo_map={},
    )

    assert len(checkpoint["top10_absolute"]) == 3
    assert checkpoint["top10_female"] == []
```

- [ ] **Step 6: Убедиться, что тест падает**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -v -k build_checkpoint`
Expected: `ImportError: cannot import name '_build_checkpoint'`

- [ ] **Step 7: Реализовать `_query_checkpoint_rows` и `_build_checkpoint`**

Добавить в конец `src/krasmarafon/services/live_top10_export.py`:

```python
def _query_checkpoint_rows(
    connection, event_id: int, time_col: str, rank_abs_col: str,
    rank_sex_col: str, pace_col: str, sex_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Столбцы (time_col/rank_abs_col/...) — не пользовательский ввод, один
    из фиксированного набора имён вида time_clear_kt1..kt6/time_clear_finish,
    которые формирует только generate_top10_json() ниже — параметризовать
    их через placeholder нельзя (это имена колонок, не значения)."""
    cur = connection.cursor(dictionary=True)
    params: List[Any] = [event_id]
    sex_clause = ""
    if sex_filter:
        sex_clause = "AND r.sex = %s"
        params.append(sex_filter)
    query = (
        f"SELECT r.start_number, r.surname, r.name, r.sex, c.city, "
        f"       r.{rank_abs_col} AS rank_absolute, r.{rank_sex_col} AS rank_sex, "
        f"       r.{time_col} AS time_clear, r.{pace_col} AS pace_avg "
        f"FROM results r "
        f"LEFT JOIN clients c ON c.id = r.client_id "
        f"WHERE r.event_id = %s AND r.{time_col} IS NOT NULL {sex_clause} "
        f"ORDER BY r.{time_col} ASC "
        f"LIMIT {_TOP_N}"
    )
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def _build_checkpoint(
    connection, event_id: int, code: str, label: str, time_col: str,
    rank_abs_col: str, rank_sex_col: str, pace_col: str,
    photo_map: Dict[int, str],
) -> Dict[str, Any]:
    abs_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col)
    male_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col, sex_filter="Мужчина")
    female_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col, sex_filter="Женщина")

    leader_abs_s = _td_to_seconds(abs_rows[0]["time_clear"]) if abs_rows else None
    leader_male_s = _td_to_seconds(male_rows[0]["time_clear"]) if male_rows else None
    leader_female_s = _td_to_seconds(female_rows[0]["time_clear"]) if female_rows else None

    def build_list(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for rec in rows:
            seconds = _td_to_seconds(rec["time_clear"])
            leader_sex_s = leader_male_s if rec["sex"] == "Мужчина" else leader_female_s
            pace_seconds = _td_to_seconds(rec["pace_avg"])
            result.append({
                "start_number": rec["start_number"],
                "surname": rec["surname"],
                "name": rec["name"],
                "sex": _sex_code(rec["sex"]),
                "city": rec.get("city") or "",
                "rank_absolute": int(rec["rank_absolute"]) if rec["rank_absolute"] is not None else None,
                "rank_sex": int(rec["rank_sex"]) if rec["rank_sex"] is not None else None,
                "time": _seconds_to_hms(seconds),
                "pace": _seconds_to_pace_str(pace_seconds) if pace_seconds is not None else None,
                "gap_absolute": _format_gap(seconds - leader_abs_s) if leader_abs_s is not None else "Лидер",
                "gap_sex": _format_gap(seconds - leader_sex_s) if leader_sex_s is not None else "Лидер",
                "photo_url": photo_map.get(rec["start_number"], PARTICIPANT_PHOTO_PLACEHOLDER_URL),
            })
        return result

    return {
        "code": code,
        "label": label,
        "top10_absolute": build_list(abs_rows),
        "top10_male": build_list(male_rows),
        "top10_female": build_list(female_rows),
    }
```

- [ ] **Step 8: Прогнать тесты**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -v`
Expected: 14 passed

- [ ] **Step 9: Написать падающий тест на `generate_top10_json` (оркестрация + атомарная запись)**

Добавить в `tests/unit/test_live_top10_export.py`:

```python
from unittest.mock import patch

from src.krasmarafon.services import live_top10_export
from src.krasmarafon.services.live_top10_export import generate_top10_json


def test_generate_top10_json_writes_atomic_file_with_all_checkpoints(tmp_path, monkeypatch):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    # 1-й fetchone — событие; 1-й fetchall — фото (пусто)
    cur.fetchone.return_value = {
        "event_name": "Жара", "event_distance": 5.0, "event_year": 2026,
        "checkpoint_distances": "[0, 2.5, 5.0]",
    }
    cur.fetchall.return_value = []

    calls = []

    def fake_build_checkpoint(connection, event_id, code, label, **kwargs):
        calls.append(code)
        return {"code": code, "label": label, "top10_absolute": [], "top10_male": [], "top10_female": []}

    monkeypatch.setattr(live_top10_export, "_build_checkpoint", fake_build_checkpoint)

    output_path = str(tmp_path / "zhara_5km_top10.json")
    generate_top10_json(conn, event_id=115, output_path=output_path)

    assert calls == ["kt1", "finish"], "5 км: 1 промежуточная КТ + финиш"
    assert not (tmp_path / "zhara_5km_top10.json.tmp").exists(), "временный файл должен быть переименован, не остаться"

    with open(output_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["event_name"] == "Жара"
    assert data["distance"] == "5 км"
    assert len(data["checkpoints"]) == 2
    assert data["checkpoints"][0]["code"] == "kt1"
    assert data["checkpoints"][1]["code"] == "finish"


def test_generate_top10_json_creates_parent_directory(tmp_path, monkeypatch):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = {
        "event_name": "Жара", "event_distance": 2.0, "event_year": 2026,
        "checkpoint_distances": None,
    }
    cur.fetchall.return_value = []

    def fake_build_checkpoint(connection, event_id, code, label, **kwargs):
        return {"code": code, "label": label, "top10_absolute": [], "top10_male": [], "top10_female": []}

    monkeypatch.setattr(live_top10_export, "_build_checkpoint", fake_build_checkpoint)

    nested_path = str(tmp_path / "nested" / "dir" / "zhara_top10.json")
    generate_top10_json(conn, event_id=135, output_path=nested_path)

    assert (tmp_path / "nested" / "dir" / "zhara_top10.json").exists()
```

Добавить `import json` в начало тестового файла, если ещё не импортирован.

- [ ] **Step 10: Убедиться, что тест падает**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -v -k generate_top10_json`
Expected: `ImportError: cannot import name 'generate_top10_json'`

- [ ] **Step 11: Реализовать `generate_top10_json`**

Добавить в конец `src/krasmarafon/services/live_top10_export.py`:

```python
def _load_photo_map(connection, event_id: int) -> Dict[int, str]:
    cur = connection.cursor(dictionary=True)
    cur.execute(
        "SELECT start_number, photo_url FROM participant_photos WHERE event_id = %s",
        (event_id,),
    )
    rows = cur.fetchall()
    cur.close()
    return {r["start_number"]: r["photo_url"] for r in rows}


def generate_top10_json(connection, event_id: int, output_path: str) -> None:
    """Собирает live-топ-10 по всем отметкам события event_id и атомарно
    перезаписывает JSON-файл по пути output_path (полностью пишет во
    временный файл, затем os.replace() — читающая сторона никогда не видит
    файл в момент записи наполовину)."""
    cur = connection.cursor(dictionary=True)
    cur.execute(
        "SELECT event_name, event_distance, event_year, checkpoint_distances "
        "FROM events WHERE id = %s",
        (event_id,),
    )
    event = cur.fetchone()
    cur.close()
    if not event:
        raise ValueError(f"event_id={event_id} не найден в events")

    checkpoint_distances = (
        json.loads(event["checkpoint_distances"]) if event["checkpoint_distances"] else []
    )
    num_kt = max(0, len(checkpoint_distances) - 2)

    photo_map = _load_photo_map(connection, event_id)

    checkpoints = []
    for i in range(1, num_kt + 1):
        checkpoints.append(_build_checkpoint(
            connection, event_id,
            code=f"kt{i}", label=f"КТ{i} ({checkpoint_distances[i]} км)",
            time_col=f"time_clear_kt{i}", rank_abs_col=f"rank_absolute_kt{i}",
            rank_sex_col=f"rank_sex_kt{i}", pace_col=f"pace_avg_kt{i}",
            photo_map=photo_map,
        ))

    checkpoints.append(_build_checkpoint(
        connection, event_id,
        code="finish", label="Финиш",
        time_col="time_clear_finish", rank_abs_col="rank_absolute_clean",
        rank_sex_col="rank_sex_clean", pace_col="finish_pace_avg_clean",
        photo_map=photo_map,
    ))

    data = {
        "event_name": event["event_name"],
        "event_year": event["event_year"],
        "distance": _format_distance_label(float(event["event_distance"])),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "checkpoints": checkpoints,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, output_path)
```

- [ ] **Step 12: Прогнать все тесты модуля**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -v`
Expected: 16 passed

- [ ] **Step 13: Commit**

```bash
git add src/krasmarafon/services/live_top10_export.py tests/unit/test_live_top10_export.py
git commit -m "feat(krasmarafon): генератор live-JSON топ-10 по отметкам"
```

---

### Task 8: Хук в `load_race_results.py`

**Files:**
- Modify: `load_race_results.py`
- Test: `tests/unit/test_race_loader_broadcast_hook.py`

- [ ] **Step 1: Написать падающие тесты**

```python
"""Хук live-JSON топ-10 (broadcast_json) в RaceLoader.continuous_mode() —
ошибка генерации не должна ронять весь live-цикл обновления результатов
(тот же принцип изоляции, что уже применён для avg_speed_kmh на Siberman —
см. спеку docs/superpowers/specs/2026-08-18-zhara-live-top10-broadcast-json-design.md)."""
import logging
from unittest.mock import patch

from load_race_results import RaceLoader


def _make_loader(broadcast_json_path="/tmp/x.json"):
    logger = logging.getLogger("test_broadcast_json_hook")
    loader = RaceLoader(event_id=999, logger=logger, broadcast_json_path=broadcast_json_path)
    loader.connection = object()
    return loader


@patch("src.krasmarafon.services.live_top10_export.generate_top10_json")
def test_maybe_write_broadcast_json_calls_generator_with_own_state(mock_gen):
    loader = _make_loader()
    loader._maybe_write_broadcast_json()
    mock_gen.assert_called_once_with(loader.connection, 999, "/tmp/x.json")


@patch("src.krasmarafon.services.live_top10_export.generate_top10_json", side_effect=RuntimeError("db down"))
def test_maybe_write_broadcast_json_swallows_errors(mock_gen):
    loader = _make_loader()
    loader._maybe_write_broadcast_json()  # не должно бросить исключение наружу


def test_broadcast_json_path_defaults_to_none():
    loader = RaceLoader(event_id=1, logger=logging.getLogger("t"))
    assert loader.broadcast_json_path is None
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `conda run -n base python -m pytest tests/unit/test_race_loader_broadcast_hook.py -v`
Expected: `TypeError: RaceLoader.__init__() got an unexpected keyword argument 'broadcast_json_path'`

- [ ] **Step 3: Добавить параметр конструктора**

В `load_race_results.py`, найти `def __init__` класса `RaceLoader` (строка ~290):

```python
    def __init__(self, event_id: int, logger: logging.LoggerAdapter,
                 copernico_race_id: Optional[str] = None,
                 copernico_login: Optional[str] = None,
                 copernico_preset: Optional[str] = None,
                 copernico_event: Optional[str] = None,
                 preset_cfg: Optional[Dict] = None,
                 broadcast_json_path: Optional[str] = None):
```

И сразу после `self.event_id = event_id`:

```python
        self.event_id = event_id
        self.broadcast_json_path = broadcast_json_path
```

- [ ] **Step 4: Добавить метод `_maybe_write_broadcast_json`**

Сразу после метода `continuous_mode` (перед `def _build_kt_field_map_from_preset`, строка ~740):

```python
    def _maybe_write_broadcast_json(self) -> None:
        """Обновляет live-JSON топ-10 по отметкам для трансляции (см.
        src/krasmarafon/services/live_top10_export.py). Ошибка здесь не
        должна останавливать continuous_mode() — тот же принцип изоляции,
        что уже применён для единичных сбоев пересчёта (см. урок про
        avg_speed_kmh на Siberman)."""
        try:
            from src.krasmarafon.services.live_top10_export import generate_top10_json
            generate_top10_json(self.connection, self.event_id, self.broadcast_json_path)
        except Exception as e:
            self.logger.error(f"⚠️ Не удалось обновить broadcast JSON: {e}")
```

- [ ] **Step 5: Вызвать хук в `continuous_mode`**

Найти блок (строки ~676-681):

```python
                t_rank = time.time()
                if updated_r > 0:
                    self._recalculate_ranks()
                if updated_s > 0:
                    self._recalculate_segment_ranks()
                rank_t = time.time() - t_rank
```

Заменить на:

```python
                t_rank = time.time()
                if updated_r > 0:
                    self._recalculate_ranks()
                if updated_s > 0:
                    self._recalculate_segment_ranks()
                if self.broadcast_json_path and (updated_r > 0 or updated_s > 0):
                    self._maybe_write_broadcast_json()
                rank_t = time.time() - t_rank
```

- [ ] **Step 6: Прогнать тесты**

Run: `conda run -n base python -m pytest tests/unit/test_race_loader_broadcast_hook.py -v`
Expected: 3 passed

- [ ] **Step 7: Добавить CLI-флаг**

В `load_race_results.py`, в `main()`, после блока `parser.add_argument('--reset-cache', ...)` (строки ~1431-1436):

```python
    parser.add_argument(
        '--broadcast-json',
        type=str,
        default=None,
        help='Путь для live-JSON топ-10 по отметкам (для трансляции); если не задан — не генерируется'
    )
```

Найти создание `RaceLoader` в `main()` (строки ~1520-1528) и добавить параметр:

```python
    loader = RaceLoader(
        event_id=event_id,
        logger=logger,
        copernico_race_id=copernico_race_id,
        copernico_login=copernico_login,
        copernico_preset=copernico_preset,
        copernico_event=copernico_event,
        preset_cfg=preset_cfg,
        broadcast_json_path=args.broadcast_json,
    )
```

- [ ] **Step 8: Проверить, что `--help` показывает новый флаг**

Run: `conda run -n base python load_race_results.py --help`
Expected: в выводе присутствует `--broadcast-json BROADCAST_JSON`

- [ ] **Step 9: Прогнать полный набор тестов проекта (регрессия)**

Run: `conda run -n base python -m pytest tests/unit/ -v`
Expected: все тесты зелёные (включая новые из Task 2/7/8)

- [ ] **Step 10: Commit**

```bash
git add load_race_results.py tests/unit/test_race_loader_broadcast_hook.py
git commit -m "feat(krasmarafon): хук --broadcast-json в live-опросе load_race_results.py"
```

---

### Task 9: `run_loader.sh` — опциональный флаг для systemd-сервисов

**Files:**
- Modify: `deploy/run_loader.sh`

- [ ] **Step 1: Прочитать текущий файл**

Текущее содержимое (для справки):
```bash
#!/bin/bash
# Wrapper для load_race_results.py — используется systemd-шаблоном km_race_loader@.service.
# Аргумент $1: имя конфига (без .env), напр. vesna_5km
set -a
source /opt/km_track/config/loader/"$1".env
set +a
exec /opt/km_track/venv/bin/python load_race_results.py \
    --config "$LOADER_CONFIG" \
    --distance "$LOADER_DISTANCE" \
    --interval "${LOADER_INTERVAL:-5}" \
    --reset-cache "${LOADER_RESET_CACHE:-60}"
```

- [ ] **Step 2: Добавить опциональный `--broadcast-json`**

Заменить целиком на:

```bash
#!/bin/bash
# Wrapper для load_race_results.py — используется systemd-шаблоном km_race_loader@.service.
# Аргумент $1: имя конфига (без .env), напр. vesna_5km
set -a
source /opt/km_track/config/loader/"$1".env
set +a
BROADCAST_ARGS=()
if [ -n "$LOADER_BROADCAST_JSON" ]; then
    BROADCAST_ARGS=(--broadcast-json "$LOADER_BROADCAST_JSON")
fi
exec /opt/km_track/venv/bin/python load_race_results.py \
    --config "$LOADER_CONFIG" \
    --distance "$LOADER_DISTANCE" \
    --interval "${LOADER_INTERVAL:-5}" \
    --reset-cache "${LOADER_RESET_CACHE:-60}" \
    "${BROADCAST_ARGS[@]}"
```

Обратная совместимость: если `LOADER_BROADCAST_JSON` не задан в конкретном `config/loader/<name>.env` (как у всех существующих событий сейчас), `BROADCAST_ARGS` остаётся пустым массивом — команда не меняется.

- [ ] **Step 3: Проверить синтаксис shell-скрипта**

Run: `bash -n deploy/run_loader.sh`
Expected: без вывода (синтаксис корректен)

- [ ] **Step 4: Commit**

```bash
git add deploy/run_loader.sh
git commit -m "feat(krasmarafon): опциональный LOADER_BROADCAST_JSON в run_loader.sh"
```

**Примечание (вне объёма этой задачи):** сами файлы `config/loader/zhara_5km.env`/`zhara_211km.env` с `LOADER_BROADCAST_JSON=/opt/km_track/live_data/zhara_5km_top10.json` создаются позже, во время подготовки к дню гонки Жары — вместе с заполнением `copernico.race_id` и остальных полей `config/events/zhara.yaml`, помеченных `# ← заполнить перед стартом`. На момент этой задачи `race_id` для Жары ещё `null`, конфиги загрузчика создавать рано.

---

### Task 10: nginx — раздача без кэша

**Files:**
- Modify: `deploy/nginx.conf`

- [ ] **Step 1: Добавить `location /live/`**

В блоке `server { listen 443 ssl; server_name analytics.krasmarafon.ru; ... }`, сразу после существующего блока `location /static/ { ... }` (строки ~66-71), вставить:

```nginx
        # Live-JSON топ-10 по отметкам для трансляции (Жара) — обновляется
        # каждые несколько секунд во время гонки load_race_results.py
        # --continuous, поэтому НЕ должен попадать под 7-дневный кэш
        # /static/ выше (иначе режиссёр трансляции будет получать
        # недельной давности данные вместо реального времени).
        location /live/ {
            alias /opt/km_track/live_data/;
            add_header Cache-Control "no-store";
        }
```

- [ ] **Step 2: Проверить синтаксис nginx-конфига**

Run: `nginx -t -c "$(pwd)/deploy/nginx.conf"` (если nginx установлен локально; если нет — пропустить, синтаксис будет проверен на проде автоматически через `nginx -t` в `.github/workflows/deploy.yml` перед `systemctl reload nginx`)

- [ ] **Step 3: Commit**

```bash
git add deploy/nginx.conf
git commit -m "feat(krasmarafon): nginx location /live/ без кэша для broadcast JSON"
```

- [ ] **Step 4: Push — задеплоится автоматически через GH Actions**

Run: `git push origin main`
Expected: workflow `deploy.yml` проходит зелёным (тесты + деплой + `nginx -t` + `systemctl reload nginx`)

---

## Финальная верификация

- [ ] **Полный прогон тестов**

Run: `conda run -n base python -m pytest tests/unit/ -v`
Expected: все тесты зелёные, включая ~19 новых из этого плана (5 CRUD + 16 live_top10_export + 3 hook, минус небольшие пересечения в подсчёте)

- [ ] **Локальная сквозная проверка генератора** (без реального event_id гонки — на любом существующем событии с checkpoint_distances, например уже прошедшем)

```bash
conda run -n base python -c "
from src.analytics.db_connection_optimized import create_connection
from src.krasmarafon.services.live_top10_export import generate_top10_json
conn = create_connection()
generate_top10_json(conn, event_id=132, output_path='/tmp/test_top10.json')
print(open('/tmp/test_top10.json', encoding='utf-8').read()[:500])
"
```
Expected: валидный JSON с реальными checkpoint-данными события 132 (Жара, 21.1 км — если там уже есть какие-то результаты; иначе пустые top10-списки, но без ошибки).

- [ ] **Проверка admin UI вживую** — `/admin` → «Фото участников», добавление/редактирование/удаление записи, сверка что `GET /api/admin/participant-photos?event_id=...` отдаёт актуальные данные.

- [ ] **Проверка nginx-заголовков после деплоя**

Run: `curl -I https://analytics.krasmarafon.ru/live/anything.json` (даже на несуществующий файл — важны заголовки, не код ответа)
Expected: `Cache-Control: no-store` в заголовках ответа.

---

## Явно вне объёма (см. спеку)

- Создание `config/loader/zhara_5km.env`/`zhara_211km.env` — часть race-day prep, не этой задачи.
- Автоматическая синхронизация с внешней гугл-анкетой элитного кластера.
- Дистанция «2 км» — без промежуточных КТ, топ-10 не строится.
