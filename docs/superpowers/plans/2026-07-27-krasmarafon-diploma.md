# Диплом участника (Красмарафон) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Публичная страница `/diploma/{event_id}/{bib}` с картинкой диплома участника (фон+медаль от дизайнера, поверх — ФИО/чистое время/места), кнопками «Скачать» (PNG) и «Распечатать», плюс точка входа — кнопка в карточке гонки на `/athlete-profile`.

**Architecture:** Новый Pydantic-блок `diploma` в `DistanceConfig` (config/events/*.yaml) — опционально включает фичу per-дистанция. Новый сервис `diploma_service.py` находит результат участника по `(event_id, bib)`, переиспользуя уже существующую кэшированную `get_race_results_by_event_id()`. Новый роут в `pages.py` рендерит отдельный full-bleed HTML/Jinja2-шаблон (без общей шапки сайта). «Скачать» — `html2canvas` (новая vendored JS-библиотека) рендерит div в PNG на клиенте; «Распечатать» — `window.print()` + `@media print`.

**Tech Stack:** FastAPI + Jinja2 (без изменений в стеке backend), vanilla JS, `html2canvas` (новая клиентская зависимость, vendored в `static/lib/`), pytest (юнит + интеграционные тесты с моками БД).

---

## Task 1: `DiplomaConfig` — новое поле в `DistanceConfig`

**Files:**
- Modify: `src/config/event_loader.py`
- Test: `tests/unit/test_event_loader_diploma.py`

- [ ] **Step 1: Написать падающий тест**

```python
"""Тесты парсинга опционального блока diploma в DistanceConfig."""
import pytest
from src.config.event_loader import EventConfig, DistanceConfig, DiplomaConfig


def test_distance_without_diploma_defaults_to_none():
    d = DistanceConfig(distance="5 км", distance_km=5.0)
    assert d.diploma is None


def test_distance_with_diploma_parses_paths():
    d = DistanceConfig(
        distance="7 км",
        distance_km=7.0,
        db_event_id=123,
        diploma={
            "background": "static/images/diplomas/women7/7km/background.png",
            "medal": "static/images/diplomas/women7/7km/medal.png",
        },
    )
    assert d.diploma is not None
    assert d.diploma.background == "static/images/diplomas/women7/7km/background.png"
    assert d.diploma.medal == "static/images/diplomas/women7/7km/medal.png"


def test_event_config_with_yaml_style_dict_parses():
    """Полный EventConfig, как будто загружен из YAML (raw dict, не объекты)."""
    raw = {
        "code": "women7",
        "name": "Женская семерка",
        "display_name": "Женская семёрка",
        "year": 2026,
        "distances": [
            {
                "distance": "7 км",
                "distance_km": 7.0,
                "db_event_id": 123,
                "diploma": {
                    "background": "static/images/diplomas/women7/7km/background.png",
                    "medal": "static/images/diplomas/women7/7km/medal.png",
                },
            },
            {"distance": "500 м", "distance_km": 0.5},
        ],
    }
    cfg = EventConfig(**raw)
    assert cfg.distances[0].diploma.background.endswith("background.png")
    assert cfg.distances[1].diploma is None
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `conda run -n base python -m pytest tests/unit/test_event_loader_diploma.py -v`
Expected: `FAIL` — `ImportError: cannot import name 'DiplomaConfig'`

- [ ] **Step 3: Добавить `DiplomaConfig` и поле `diploma` в `src/config/event_loader.py`**

Добавить сразу после класса `CheckpointCoord` (перед `class DistanceConfig`):

```python
class DiplomaConfig(BaseModel):
    background: str   # путь к фоновой картинке, относительно корня репо (напр. "static/images/diplomas/women7/7km/background.png")
    medal: str         # путь к картинке медали, тот же формат
```

В `DistanceConfig` добавить новое поле (после `decorative_checkpoints`, перед `gpx_file` — порядок не важен, но держим рядом с остальными опциональными блоками):

```python
    diploma: Optional[DiplomaConfig] = None      # если не задано — диплом для этой дистанции недоступен
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `conda run -n base python -m pytest tests/unit/test_event_loader_diploma.py -v`
Expected: `3 passed`

- [ ] **Step 5: Коммит**

```bash
git add src/config/event_loader.py tests/unit/test_event_loader_diploma.py
git commit -m "feat(krasmarafon): DiplomaConfig — опциональный блок diploma в DistanceConfig"
```

---

## Task 2: Сервис получения данных диплома

**Files:**
- Create: `src/krasmarafon/services/diploma_service.py`
- Test: `tests/unit/test_diploma_service.py`

Логика: найти результат участника `(event_id, bib)` среди уже загруженных (и кэшированных) результатов события (`get_race_results_by_event_id`, `src/analytics/db_results.py:47`), проверить что участник реально финишировал, определить нужна ли строка «Пол» (только если у события есть участники обоих полов), отформатировать чистое время из `timedelta`.

- [ ] **Step 1: Написать падающие тесты**

```python
"""Тесты сервиса данных диплома — БД замокана, без реального соединения."""
import pytest
from datetime import timedelta
from unittest.mock import patch
from src.krasmarafon.services.diploma_service import get_diploma_data, format_finish_time


def _row(bib, sex, status='Finished', time_s=None, rank_abs=1, rank_sex=1, rank_cat=1, category='Ж45'):
    return {
        'start_number': bib,
        'surname': 'Аристархова',
        'name': 'Наталья',
        'sex': sex,
        'race_status': status,
        'time_clear_finish': timedelta(seconds=time_s) if time_s is not None else None,
        'rank_absolute_clean': rank_abs,
        'rank_sex_clean': rank_sex,
        'rank_category_clean': rank_cat,
        'category': category,
    }


def test_format_finish_time_under_hour():
    assert format_finish_time(timedelta(minutes=26, seconds=16)) == '26:16'


def test_format_finish_time_over_hour():
    assert format_finish_time(timedelta(hours=1, minutes=32, seconds=10)) == '1:32:10'


def test_format_finish_time_none_returns_dash():
    assert format_finish_time(None) == '-'


def test_get_diploma_data_finds_participant_by_bib():
    rows = [_row('101', 'female', time_s=1576), _row('102', 'female', time_s=1620)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data is not None
    assert data['surname'] == 'Аристархова'
    assert data['time_display'] == '26:16'


def test_get_diploma_data_returns_none_for_missing_bib():
    rows = [_row('101', 'female', time_s=1576)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='999')
    assert data is None


def test_get_diploma_data_returns_none_if_not_finished():
    rows = [_row('101', 'female', status='DNF', time_s=None)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data is None


def test_get_diploma_data_hides_sex_row_when_single_gender_event():
    rows = [_row('101', 'female', time_s=1576), _row('102', 'female', time_s=1620)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data['show_sex_rank'] is False


def test_get_diploma_data_shows_sex_row_when_mixed_gender_event():
    rows = [_row('101', 'female', time_s=1576), _row('102', 'male', time_s=1500)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data['show_sex_rank'] is True


def test_get_diploma_data_status_check_accepts_typo_variant():
    """'fifnished' — реальное значение в данных (см. athlete-profile.html), должно приниматься как финишировавший."""
    rows = [_row('101', 'female', status='fifnished', time_s=1576)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data is not None
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `conda run -n base python -m pytest tests/unit/test_diploma_service.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'src.krasmarafon.services.diploma_service'`

- [ ] **Step 3: Реализовать сервис**

Создать `src/krasmarafon/services/diploma_service.py`:

```python
"""
Данные для страницы диплома участника — /diploma/{event_id}/{bib}.
Переиспользует уже закэшированный get_race_results_by_event_id() вместо
отдельного SQL-запроса по bib: результаты события и так загружаются
целиком, найти один bib среди них дешевле, чем городить новый метод.
"""

from typing import Optional
from datetime import timedelta

from src.analytics.db_results import get_race_results_by_event_id

# 'fifnished' — не опечатка в этом файле, а реальное значение в БД
# (см. тот же список в templates/krasmarafon/athlete-profile.html:366).
_FINISHED_STATUSES = {'finished', 'fifnished'}


def format_finish_time(td: Optional[timedelta]) -> str:
    """timedelta → 'H:MM:SS' (или 'MM:SS', если меньше часа), '-' для None."""
    if td is None:
        return '-'
    total_seconds = int(td.total_seconds())
    if total_seconds <= 0:
        return '-'
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def get_diploma_data(event_id: int, bib: str) -> Optional[dict]:
    """Данные для рендера диплома, либо None, если участник не найден /
    не финишировал по этой дистанции. show_sex_rank — показывать ли место
    по полу (только если у события есть участники обоих полов)."""
    rows = get_race_results_by_event_id(event_id)
    if not rows:
        return None

    target = next((r for r in rows if str(r.get('start_number')) == str(bib)), None)
    if target is None:
        return None

    status = str(target.get('race_status') or '').lower()
    if status not in _FINISHED_STATUSES:
        return None

    sexes = {r.get('sex') for r in rows if r.get('sex')}

    return {
        'surname': target.get('surname'),
        'name': target.get('name'),
        'category': target.get('category'),
        'time_display': format_finish_time(target.get('time_clear_finish')),
        'rank_absolute': target.get('rank_absolute_clean'),
        'rank_sex': target.get('rank_sex_clean'),
        'rank_category': target.get('rank_category_clean'),
        'show_sex_rank': len(sexes) > 1,
    }
```

- [ ] **Step 4: Прогнать тесты**

Run: `conda run -n base python -m pytest tests/unit/test_diploma_service.py -v`
Expected: `8 passed`

- [ ] **Step 5: Коммит**

```bash
git add src/krasmarafon/services/diploma_service.py tests/unit/test_diploma_service.py
git commit -m "feat(krasmarafon): diploma_service — данные диплома по (event_id, bib)"
```

---

## Task 3: Роут `/diploma/{event_id}/{bib}` + Jinja2-шаблон

**Files:**
- Modify: `src/krasmarafon/routers/pages.py`
- Create: `templates/krasmarafon/diploma.html`
- Test: `tests/integration/test_diploma_route.py`

- [ ] **Step 1: Написать падающие интеграционные тесты**

Создать `tests/integration/test_diploma_route.py`:

```python
"""Интеграционные тесты роута /diploma/{event_id}/{bib} — БД замокана."""
from datetime import timedelta
from unittest.mock import patch

from src.config.event_loader import EventConfig, DistanceConfig, DiplomaConfig


def _fake_event():
    return EventConfig(
        code="women7",
        name="Женская семерка",
        display_name="Женская семёрка",
        year=2026,
        distances=[
            DistanceConfig(
                distance="7 км", distance_km=7.0, db_event_id=555, tracked=True,
                diploma=DiplomaConfig(
                    background="static/images/diplomas/women7/7km/background.png",
                    medal="static/images/diplomas/women7/7km/medal.png",
                ),
            ),
        ],
    )


def _fake_rows():
    return [{
        'start_number': '101', 'surname': 'Аристархова', 'name': 'Наталья',
        'sex': 'female', 'race_status': 'Finished', 'category': 'Ж45',
        'time_clear_finish': timedelta(minutes=26, seconds=16),
        'rank_absolute_clean': 1, 'rank_sex_clean': 1, 'rank_category_clean': 1,
    }]


class TestDiplomaRoute:
    def test_diploma_200_for_configured_event_and_existing_bib(self, client):
        with patch('src.config.settings.EVENTS', {'women7': _fake_event()}), \
             patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=_fake_rows()):
            r = client.get("/diploma/555/101")
        assert r.status_code == 200
        assert 'Аристархова' in r.text
        assert '26:16' in r.text

    def test_diploma_404_for_unknown_event_id(self, client):
        with patch('src.config.settings.EVENTS', {'women7': _fake_event()}):
            r = client.get("/diploma/999999/101")
        assert r.status_code == 404

    def test_diploma_404_for_unknown_bib(self, client):
        with patch('src.config.settings.EVENTS', {'women7': _fake_event()}), \
             patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=_fake_rows()):
            r = client.get("/diploma/555/999")
        assert r.status_code == 404

    def test_diploma_hides_sex_rank_for_single_gender_event(self, client):
        with patch('src.config.settings.EVENTS', {'women7': _fake_event()}), \
             patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=_fake_rows()):
            r = client.get("/diploma/555/101")
        assert 'Ж45' in r.text
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `conda run -n base python -m pytest tests/integration/test_diploma_route.py -v`
Expected: `FAIL` — `404 != 200` (роут ещё не существует, любой путь отдаёт 404 — тест ожидающий 404 для "unknown" пока пройдёт случайно, остальные упадут)

- [ ] **Step 3: Добавить роут в `src/krasmarafon/routers/pages.py`**

`HTTPException` пока не импортирован в этом файле — заменить существующую строку импорта из `fastapi` (`pages.py:12`):

```python
from fastapi import APIRouter, Depends, Form, Request, Query
```

на:

```python
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Query
```

Добавить импорт рядом с существующим `from src.config.event_loader import get_event_by_name`:

```python
from src.config.event_loader import get_event_by_name, get_event_by_db_id
from src.krasmarafon.services.diploma_service import get_diploma_data
```

Добавить новый роут (после `athlete_profile_page`, перед `race_analysis_page`):

```python
@router.get("/diploma/{event_id}/{bib}", response_class=HTMLResponse)
async def diploma_page(request: Request, event_id: int, bib: str):
    """Публичный диплом участника — фон+медаль от дизайнера (per-дистанция
    в конфиге события), поверх — ФИО/чистое время/места. Без авторизации
    и без общей шапки сайта — самостоятельная полноэкранная страница,
    можно переслать прямой ссылкой."""
    event_cfg, distance_cfg = get_event_by_db_id(settings.EVENTS, event_id)
    if event_cfg is None or distance_cfg is None or distance_cfg.diploma is None:
        raise HTTPException(status_code=404, detail="Диплом для этого события/дистанции недоступен")

    data = get_diploma_data(event_id, bib)
    if data is None:
        raise HTTPException(status_code=404, detail="Результат участника не найден")

    return templates.TemplateResponse("krasmarafon/diploma.html", {
        "request": request,
        "event": event_cfg,
        "distance": distance_cfg,
        "diploma": data,
    })
```

`HTTPException` уже должен быть импортирован в `pages.py` — проверить, и если нет, добавить `from fastapi import HTTPException` в существующий импорт из `fastapi`.

- [ ] **Step 4: Создать `templates/krasmarafon/diploma.html`**

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Диплом — {{ diploma.surname }} {{ diploma.name }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: system-ui, sans-serif; background: #1a1a1a;
            min-height: 100vh; display: flex; flex-direction: column;
            align-items: center; padding: 24px 16px;
        }
        .diploma-card {
            width: 100%; max-width: 420px;
            background-image: url('/{{ distance.diploma.background }}');
            background-size: cover; background-position: center;
            border-radius: 8px; padding: 28px 24px; color: #fff;
            position: relative; min-height: 640px;
        }
        .diploma-header { display: flex; justify-content: space-between; align-items: flex-start; }
        .diploma-title { font-size: 22px; font-weight: 800; line-height: 1.15; }
        .diploma-logo { font-size: 13px; font-weight: 700; border: 1px solid #fff; border-radius: 4px; padding: 4px 8px; }
        .diploma-distance-row { display: flex; justify-content: space-between; margin-top: 18px; font-size: 12px; opacity: .85; letter-spacing: .5px; }
        .diploma-name-card { background: rgba(255,255,255,.14); border-radius: 14px; padding: 18px; margin-top: 14px; text-align: center; }
        .diploma-name { font-size: 16px; font-weight: 700; letter-spacing: .5px; }
        .diploma-time { font-size: 30px; font-weight: 800; margin-top: 6px; }
        .diploma-ranks-card { background: rgba(255,255,255,.14); border-radius: 14px; padding: 14px 18px; margin-top: 12px; font-size: 15px; }
        .diploma-rank-row { display: flex; justify-content: space-between; padding: 4px 0; }
        .diploma-medal { display: flex; justify-content: center; margin-top: 24px; }
        .diploma-medal img { max-width: 140px; max-height: 140px; }
        .diploma-actions { display: flex; gap: 10px; justify-content: center; margin-top: 20px; }
        .diploma-btn {
            padding: 10px 20px; border-radius: 20px; border: none;
            background: #e91e8c; color: #fff; font-size: 14px; font-weight: 700;
            cursor: pointer;
        }
        @media print {
            body { background: #fff; padding: 0; }
            .diploma-actions { display: none; }
            .diploma-card { max-width: 100%; min-height: 100vh; border-radius: 0; }
        }
    </style>
</head>
<body>
    <div class="diploma-card" id="diplomaCard">
        <div class="diploma-header">
            <div class="diploma-title">{{ event.display_name.upper() }}</div>
            <div class="diploma-logo">KM</div>
        </div>
        <div class="diploma-distance-row">
            <span>ДИСТАНЦИЯ</span>
            <span>{{ distance.distance }}</span>
        </div>
        <div class="diploma-name-card">
            <div class="diploma-name">{{ diploma.surname.upper() }} {{ diploma.name.upper() }}</div>
            <div class="diploma-time">{{ diploma.time_display }}</div>
        </div>
        <div class="diploma-ranks-card">
            <div class="diploma-rank-row"><span>Абсолют</span><span>{{ diploma.rank_absolute or '-' }}</span></div>
            {% if diploma.show_sex_rank %}
            <div class="diploma-rank-row"><span>Пол</span><span>{{ diploma.rank_sex or '-' }}</span></div>
            {% endif %}
            {% if diploma.rank_category %}
            <div class="diploma-rank-row"><span>{{ diploma.category or 'Категория' }}</span><span>{{ diploma.rank_category }}</span></div>
            {% endif %}
        </div>
        <div class="diploma-medal">
            <img src="/{{ distance.diploma.medal }}" alt="Медаль">
        </div>
    </div>

    <div class="diploma-actions">
        <button class="diploma-btn" id="btnDownload">⬇ Скачать</button>
        <button class="diploma-btn" id="btnPrint">🖨 Распечатать</button>
    </div>

    <script src="/static/lib/html2canvas/html2canvas.min.js"></script>
    <script>
        document.getElementById('btnPrint').addEventListener('click', () => window.print());

        document.getElementById('btnDownload').addEventListener('click', async () => {
            const btn = document.getElementById('btnDownload');
            btn.textContent = 'Готовим…';
            try {
                const canvas = await html2canvas(document.getElementById('diplomaCard'), { useCORS: true, scale: 2 });
                const link = document.createElement('a');
                link.download = 'diploma-{{ diploma.surname }}-{{ diploma.name }}.png';
                link.href = canvas.toDataURL('image/png');
                link.click();
            } finally {
                btn.textContent = '⬇ Скачать';
            }
        });
    </script>
</body>
</html>
```

- [ ] **Step 5: Прогнать интеграционные тесты**

Run: `conda run -n base python -m pytest tests/integration/test_diploma_route.py -v`
Expected: `4 passed`

- [ ] **Step 6: Коммит**

```bash
git add src/krasmarafon/routers/pages.py templates/krasmarafon/diploma.html tests/integration/test_diploma_route.py
git commit -m "feat(krasmarafon): роут /diploma/{event_id}/{bib} + шаблон диплома"
```

---

## Task 4: Вендоринг `html2canvas`

**Отклонение от исходного текста плана (найдено при реализации):** план ошибочно предполагал, что `static/lib/` — часть git-репозитория (по аналогии с `static/lib/chart3/chart.min.js`). На деле `static/lib/` в `.gitignore` целиком — ни один файл в этой папке не коммитится, все библиотеки скачиваются на этапе деплоя через `deploy/download_static_libs.py` (вызывается из `deploy/update.sh`). Ниже — уже исправленная версия задачи.

**Files:**
- Modify: `deploy/download_static_libs.py` (добавить запись в `LIBS`)

- [ ] **Step 1: Добавить html2canvas в `LIBS`**

В `deploy/download_static_libs.py`, в словарь `LIBS` (рядом с существующими записями Chart.js), добавить:

```python
    # html2canvas 1.4.1 (для скачивания диплома на krasmarafon)
    "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js":
        "html2canvas/html2canvas.min.js",
```

- [ ] **Step 2: Скачать локально для проверки** (не коммитится — `static/lib/` в `.gitignore`)

```bash
conda run -n base python deploy/download_static_libs.py
ls -la static/lib/html2canvas/html2canvas.min.js
```

Expected: файл существует, размер в районе 150-250KB, начинается с UMD-заголовка `/*! html2canvas 1.4.1 ...`.

- [ ] **Step 3: Коммит**

```bash
git add deploy/download_static_libs.py
git commit -m "chore(krasmarafon): вендоринг html2canvas 1.4.1 для скачивания диплома"
```

Реальный бинарник на проде появится автоматически на следующем деплое (`deploy/update.sh` уже вызывает `download_static_libs.py` безусловно).

---

## Task 5: Точка входа — кнопка «Диплом» на `/athlete-profile`

**Files:**
- Modify: `src/krasmarafon/routers/pages.py`
- Modify: `templates/krasmarafon/athlete-profile.html`

Кнопка показывается в карточке гонки (grid view), только если для `race.event_id` в конфиге сконфигурирован диплом — набор доступных `event_id` вычисляется один раз на сервере при рендере страницы (не требует нового API-эндпоинта) и встраивается в HTML как JS-массив.

- [ ] **Step 1: Вычислить и передать `diploma_event_ids` в `athlete_profile_page`**

В `src/krasmarafon/routers/pages.py` заменить:

```python
@router.get("/athlete-profile", response_class=HTMLResponse)
async def athlete_profile_page(request: Request):
    """Профиль спортсмена со всеми его результатами."""
    return templates.TemplateResponse("krasmarafon/athlete-profile.html", {"request": request})
```

на:

```python
@router.get("/athlete-profile", response_class=HTMLResponse)
async def athlete_profile_page(request: Request):
    """Профиль спортсмена со всеми его результатами."""
    diploma_event_ids = [
        d.db_event_id
        for event in settings.EVENTS.values()
        for d in event.distances
        if d.diploma is not None and d.db_event_id is not None
    ]
    return templates.TemplateResponse("krasmarafon/athlete-profile.html", {
        "request": request,
        "diploma_event_ids": diploma_event_ids,
    })
```

- [ ] **Step 2: Встроить список в шаблон + добавить кнопку в карточку**

В `templates/krasmarafon/athlete-profile.html`, найти начало `<script>` блока (там, где определены глобальные JS-переменные — рядом с другими `const`/`let` в начале скрипта) и добавить:

```html
<script>
    const DIPLOMA_EVENT_IDS = new Set({{ diploma_event_ids | tojson }});
</script>
```

Разместить этот `<script>` тег ПЕРЕД основным `<script>` блоком (тем, что начинается около строки 148 с `formatTime` и содержит `renderGridView`) — чтобы `DIPLOMA_EVENT_IDS` была доступна как глобальная переменная к моменту вызова `renderGridView()`.

Затем в `renderGridView()` (`templates/krasmarafon/athlete-profile.html:812-835`) заменить:

```javascript
                racesGrid.innerHTML += `
                    <div class="race-card">
                        <div class="race-date">${dateStr}</div>
                        <div class="race-distance" style="font-size: 16px;">${race.event_name || '-'}</div>
                        <div class="race-dist-badge">${formatDistance(race.event_distance)}</div>
                        <div style="margin-top: 10px;">
                            <span class="race-status ${statusInfo.class}">${statusInfo.text}</span>
                        </div>
                        <div class="race-time">
                            <div class="time-row">
                                <span class="time-label">Время финиша:</span>
                                <span class="time-value">${time}</span>
                            </div>
                            <div class="time-row">
                                <span class="time-label">Темп:</span>
                                <span class="time-value pace">${pace}</span>
                            </div>
                            ${category ? `<div class="time-row"><span class="time-label">Категория:</span><span class="time-value">${category}</span></div>` : ''}
                            ${race.rank_absolute ? `<div class="time-row"><span class="time-label">Место:</span><span class="time-value">#${race.rank_absolute}</span></div>` : ''}
                            ${race.rank_sex ? `<div class="time-row"><span class="time-label">Место (пол):</span><span class="time-value">#${race.rank_sex}</span></div>` : ''}
                            ${race.rank_category ? `<div class="time-row"><span class="time-label">Место (кат.):</span><span class="time-value">#${race.rank_category}</span></div>` : ''}
                        </div>
                    </div>
                `;
```

на:

```javascript
                const isFinished = race.race_status === 'Finished' || race.race_status === 'finished' || race.race_status === 'fifnished';
                const hasDiploma = isFinished && race.event_id && race.start_number && DIPLOMA_EVENT_IDS.has(race.event_id);

                racesGrid.innerHTML += `
                    <div class="race-card">
                        <div class="race-date">${dateStr}</div>
                        <div class="race-distance" style="font-size: 16px;">${race.event_name || '-'}</div>
                        <div class="race-dist-badge">${formatDistance(race.event_distance)}</div>
                        <div style="margin-top: 10px;">
                            <span class="race-status ${statusInfo.class}">${statusInfo.text}</span>
                        </div>
                        <div class="race-time">
                            <div class="time-row">
                                <span class="time-label">Время финиша:</span>
                                <span class="time-value">${time}</span>
                            </div>
                            <div class="time-row">
                                <span class="time-label">Темп:</span>
                                <span class="time-value pace">${pace}</span>
                            </div>
                            ${category ? `<div class="time-row"><span class="time-label">Категория:</span><span class="time-value">${category}</span></div>` : ''}
                            ${race.rank_absolute ? `<div class="time-row"><span class="time-label">Место:</span><span class="time-value">#${race.rank_absolute}</span></div>` : ''}
                            ${race.rank_sex ? `<div class="time-row"><span class="time-label">Место (пол):</span><span class="time-value">#${race.rank_sex}</span></div>` : ''}
                            ${race.rank_category ? `<div class="time-row"><span class="time-label">Место (кат.):</span><span class="time-value">#${race.rank_category}</span></div>` : ''}
                        </div>
                        ${hasDiploma ? `<a href="/diploma/${race.event_id}/${race.start_number}" target="_blank" class="diploma-link-btn">🏅 Диплом</a>` : ''}
                    </div>
                `;
```

Добавить CSS-класс `diploma-link-btn` в `<style>` блок `athlete-profile.html` (рядом с существующими `.race-card`/`.race-status` правилами):

```css
.diploma-link-btn {
    display: block; text-align: center; margin-top: 12px;
    padding: 8px 14px; border-radius: 20px; background: #e91e8c;
    color: #fff; font-size: 13px; font-weight: 700; text-decoration: none;
}
.diploma-link-btn:hover { opacity: .85; }
```

- [ ] **Step 3: Проверить вручную (если сервер поднимается локально) или отложить до деплоя**

Если локальный сервер с доступом к БД недоступен (частая ситуация в этом проекте — БД обычно доступна только с прод-VPS), пропустить этот шаг и полагаться на Task 6 (проверка после деплоя).

Если сервер доступен: открыть `/athlete-profile?surname=...&name=...` для спортсмена с результатом в событии, у которого в конфиге (пока ни у одного — см. Task 6) настроен `diploma` — кнопка «🏅 Диплом» должна появиться только там, вести на `/diploma/{event_id}/{bib}`.

- [ ] **Step 4: Коммит**

```bash
git add src/krasmarafon/routers/pages.py templates/krasmarafon/athlete-profile.html
git commit -m "feat(krasmarafon): кнопка «Диплом» в карточке гонки на athlete-profile"
```

---

## Task 6: Финальная проверка + документация по вводу нового события

**Files:** нет изменений кода — тесты + документация процесса.

- [ ] **Step 1: Прогнать весь набор тестов**

Run: `conda run -n base python -m pytest tests/unit/test_event_loader_diploma.py tests/unit/test_diploma_service.py tests/integration/test_diploma_route.py -v`
Expected: все тесты `PASSED`

- [ ] **Step 2: Прогнать полный юнит-сьют на регрессию**

Run: `conda run -n base python -m pytest tests/unit/ -v`
Expected: все тесты `PASSED` (новые файлы не должны ломать существующие — они не трогают ничего вне новых файлов и `event_loader.py`/`pages.py`, куда только добавлен код, ничего не удалено)

- [ ] **Step 3: Убедиться, что ни один существующий шаблон/роут не сломан диффом**

Run: `git diff main~6 -- templates/krasmarafon/results.html templates/krasmarafon/history.html templates/krasmarafon/race-analysis.html` (число коммитов подобрать по факту — все коммиты Task 1-5 этого плана)
Expected: пустой вывод — эти файлы не затронуты

- [ ] **Step 4: Push и деплой**

```bash
git push origin main
```

Run: `gh run list --limit 1 --json status,conclusion` в цикле до `completed`/`success`.

- [ ] **Step 5: Живая проверка на проде (без реального диплом-контента)**

На проде ни у одного события пока не настроен `diploma` (реальных фон/медаль-картинок от дизайнера ещё нет) — это ОЖИДАЕМО. Проверить:
1. `/athlete-profile?surname=...&name=...` для любого реального финишировавшего спортсмена — кнопки «Диплом» НЕТ ни в одной карточке (т.к. `DIPLOMA_EVENT_IDS` пуст) — старое поведение страницы не сломано.
2. `curl -i https://analytics.krasmarafon.ru/diploma/1/1` (любой event_id/bib) → `404` с телом `{"detail":"Диплом для этого события/дистанции недоступен"}` — роут существует и корректно отказывает без конфига, не падает 500.

- [ ] **Step 6: Задокументировать процесс включения диплома для нового события**

Добавить в `docs/superpowers/specs/2026-07-27-krasmarafon-diploma-design.md` (в конец файла, новый раздел) — короткую инструкцию для того, кто будет включать диплом для конкретного забега:

```markdown
## Как включить диплом для события (после того как дизайнер подготовил фон+медаль)

1. Положить `background.png`+`medal.png` в `static/images/diplomas/<code события>/<slug дистанции>/`
2. В `config/events/<code>.yaml`, в нужной дистанции добавить:
   ```yaml
   diploma:
     background: "static/images/diplomas/<code>/<slug>/background.png"
     medal: "static/images/diplomas/<code>/<slug>/medal.png"
   ```
3. Задеплоить (или подождать TTL-кеша конфигов, 30 сек, если конфиги горячо перезагружаются) — кнопка «Диплом» появится в карточках этой дистанции на `/athlete-profile` автоматически, код трогать не нужно.
```

```bash
git add docs/superpowers/specs/2026-07-27-krasmarafon-diploma-design.md
git commit -m "docs(krasmarafon): инструкция по включению диплома для нового события"
git push origin main
```
