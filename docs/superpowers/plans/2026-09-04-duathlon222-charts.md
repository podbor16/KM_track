# Дуатлон 222 — графики «Позиция» и «Темп/Скорость» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить пятую вкладку «График» на страницу результатов Дуатлона 222 (`duathlon_results.html`) с двумя режимами — «Позиция» (место на дистанции, X — реальные/виртуальные км) и «Темп/скорость» (по этапам) — с сайдбаром (десктоп)/bottom-sheet (мобилка) для выбора участников к сравнению.

**Architecture:** Бэкенд (`get_standings()`) отдаёт новое поле `checkpoints` на участника — полную историю отметок по каждому этапу (км уже посчитан через существующий `_lap_distance_km`, время — уже хранящееся в БД `elapsed_s` от старта гонки). Фронтенд — новый файл `static/js/duathlon222-chart.js` с чистыми функциями трансформации данных (ранг по позиции, сплит-темп/скорость, виртуальные X-сегменты) поверх существующей вёрстки `.tri-chart-*` (уже есть в `tri_results.css`, используется в `tri_results.html` — переиспользуется 1:1, новых CSS почти не требуется) и Chart.js (уже подключён проектом как `chart.umd.min.js`).

**Tech Stack:** Python 3.13/FastAPI (без изменений API-контракта, кроме нового поля), ванильный JS (без фреймворка, без модулей — общий global scope между `<script>`-тегами), Chart.js 4 (`/static/lib/chart4/chart.umd.min.js`), pytest (бэкенд), `node:vm`-харнесс для JS-тестов (тот же паттерн, что `tests/js/test_siberman_results_merge.js` — **прочитать первые 90 строк этого файла перед Task 4**, чтобы не переизобретать `domStub`/`ChartStub`/`check()`).

**Спека:** `docs/superpowers/specs/2026-09-04-duathlon222-charts-design.md` (одобрена пользователем).

---

## Task 1: Backend — `_build_checkpoint_series()`

**Files:**
- Modify: `src/duathlon222/service.py`
- Test: `tests/unit/test_duathlon222_service.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в конец `tests/unit/test_duathlon222_service.py`:

```python
def test_build_checkpoint_series_includes_stage_start_as_lap_zero():
    stage_starts = {"run1": 0, "bike": 3720, "run2": None}
    laps_by_key = {
        (1, "run1"): [(1, 400), (8, 2600)],
        (1, "bike"): [(1, 4380)],
    }
    result = _build_checkpoint_series(1, stage_starts, laps_by_key)
    assert result["run1"][0] == {"lap": 0, "km": 0.0, "elapsed_s": 0}
    assert result["run1"][1] == {"lap": 1, "km": 1.25, "elapsed_s": 400}
    assert result["run1"][2] == {"lap": 8, "km": 9.98, "elapsed_s": 2600}
    assert result["bike"][0] == {"lap": 0, "km": 0.0, "elapsed_s": 3720}
    assert result["bike"][1] == {"lap": 1, "km": 3.4, "elapsed_s": 4380}


def test_build_checkpoint_series_no_lap_zero_when_stage_start_unknown():
    # run2 ещё не начат (run2_start_s=None) — нет виртуальной отметки 0, и
    # нет вообще никаких отметок (нет записей в laps_by_key для run2).
    stage_starts = {"run1": 0, "bike": 3720, "run2": None}
    result = _build_checkpoint_series(1, stage_starts, {})
    assert result["run2"] == []


def test_build_checkpoint_series_empty_for_participant_with_no_laps():
    stage_starts = {"run1": 0, "bike": None, "run2": None}
    result = _build_checkpoint_series(1, stage_starts, {})
    assert result == {"run1": [{"lap": 0, "km": 0.0, "elapsed_s": 0}], "bike": [], "run2": []}
```

Обновить импорт в начале файла — добавить `_build_checkpoint_series`:

```python
from src.duathlon222.service import (
    _stage_times, _speed_kmh, _current_stage, _forecast_stage_finish,
    _lap_ranks_from_rows, _build_stage_laps,
    _distance_covered_km, _display_status, _rank_standings_rows,
    _forecast_race_finish, _speed_kmh_for_distance,
    _stage_start_s, _frontier_lap,
    _lap_distance_km, _lap_split_distance_km,
    _global_km, _live_gap_map,
    _stage_mark_zero_broadcast,
    _build_checkpoint_series,
)
```

- [ ] **Step 2: Запустить тесты, убедиться что новые падают**

Run: `conda run -n base python -m pytest tests/unit/test_duathlon222_service.py -k build_checkpoint_series -v`
Expected: 3 теста FAIL с `ImportError` (функции ещё нет).

- [ ] **Step 3: Реализовать функцию**

В `src/duathlon222/service.py` добавить сразу после `_stage_mark_zero_broadcast` (перед `_live_gap_map`, если она физически выше — смотреть точный порядок в файле, вставить в любое место модуля выше `get_standings`, но рядом с `_lap_distance_km`/`_stage_start_s`, раз это их прямой потребитель):

```python
def _build_checkpoint_series(
    participant_id: int,
    stage_starts: dict[str, Optional[int]],
    laps_by_key: dict[tuple[int, str], list[tuple[int, int]]],
) -> dict[str, list[dict]]:
    """Полная история отметок участника по каждому этапу — для графиков
    «Позиция»/«Темп-скорость» (см. get_standings). elapsed_s — ВСЕГДА от
    старта ГОНКИ (то же значение, что checkpoints.cumulative_s в БД — см.
    load_duathlon_results.py), не от старта этапа: так один и тот же массив
    годится и для живого ранга по гонке целиком, и для сплит-темпа внутри
    этапа (разница cumulative_s между соседними точками не зависит от точки
    отсчёта). lap=0 — виртуальная отметка выхода из транзитки (тот же
    источник, что и _stage_mark_zero_broadcast), добавляется только если
    старт этапа уже известен — даёт точную (не экстраполированную) первую
    точку сплита вместо прежнего трюка "продлить линию плоско до X=0"."""
    result: dict[str, list[dict]] = {}
    for stage_code in _STAGE_ORDER:
        points: list[dict] = []
        start_s = stage_starts.get(stage_code)
        if start_s is not None:
            points.append({"lap": 0, "km": 0.0, "elapsed_s": start_s})
        for lap_number, cumulative_s in laps_by_key.get((participant_id, stage_code), []):
            points.append({
                "lap": lap_number,
                "km": round(_lap_distance_km(stage_code, lap_number), 2),
                "elapsed_s": cumulative_s,
            })
        result[stage_code] = points
    return result
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_duathlon222_service.py -k build_checkpoint_series -v`
Expected: 3 теста PASS.

- [ ] **Step 5: Полный прогон юнит-тестов модуля (регрессия)**

Run: `conda run -n base python -m pytest tests/unit/test_duathlon222_service.py -v`
Expected: все тесты PASS (никаких падений от нового кода — функция не трогает существующую логику).

- [ ] **Step 6: Commit**

```bash
git add src/duathlon222/service.py tests/unit/test_duathlon222_service.py
git commit -m "feat(duathlon222): _build_checkpoint_series для данных графиков

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: Backend — вписать `checkpoints` в `get_standings()`

**Files:**
- Modify: `src/duathlon222/service.py:774-853` (цикл построения `enriched`)

- [ ] **Step 1: Добавить вычисление `stage_starts_for_row` и вызов в существующий цикл**

В `get_standings()`, внутри `for row in rows:` (второй цикл, где строится `enriched`), сразу после строки

```python
            current_stage, current_stage_start_s = _current_stage(
                row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"], row["run2_s"],
                row["bike_start_s"], row["run2_start_s"],
            )
```

вставить:

```python
            # Старт каждого из 3 этапов (не только текущего) — нужен для
            # checkpoints (виртуальная отметка lap=0 в _build_checkpoint_series).
            stage_starts_for_row = {
                sc: _stage_start_s(
                    sc, row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"],
                    row["bike_start_s"], row["run2_start_s"],
                )
                for sc in _STAGE_ORDER
            }
```

Затем в самом словаре `enriched.append({...})` добавить новое поле (после `"forecast_race_finish_s": forecast_race_s,`):

```python
                "checkpoints": _build_checkpoint_series(row["id"], stage_starts_for_row, laps_by_key),
```

- [ ] **Step 2: Ручная проверка через запущенный dev-сервер**

Запустить локальный сервер (если ещё не запущен) и проверить, что поле появилось и не сломало существующий ответ:

```bash
conda run -n base python -c "
import json
from src.duathlon222.service import get_standings
rows = get_standings(event_id=1)
print(json.dumps(rows[0].get('checkpoints'), ensure_ascii=False, indent=2)[:800] if rows else 'no rows')
print('total rows:', len(rows))
"
```

Expected: печатается словарь `{"run1": [...], "bike": [...], "run2": [...]}` без ошибок; `event_id` заменить на реальный ID события Дуатлона 222 (посмотреть в `config/events/duathlon_222.yaml`, если не помнишь наизусть).

- [ ] **Step 3: Прогнать полный юнит-набор проекта (регрессия)**

Run: `conda run -n base python -m pytest tests/unit/ -v`
Expected: все тесты PASS (это чисто аддитивное изменение — новое поле в словаре, ничего не удалено/переименовано).

- [ ] **Step 4: Commit**

```bash
git add src/duathlon222/service.py
git commit -m "feat(duathlon222): checkpoints в /standings для графиков

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: Разметка — вкладка «График» и точки входа

**Files:**
- Modify: `templates/race_triatleta/duathlon_results.html`
- Modify: `static/css/tri_results.css`

- [ ] **Step 1: Добавить CSS — только один недостающий кусочек (поиск в сайдбаре)**

`.tri-search` в `tri_results.css` имеет фиксированную ширину 180px — подходит для строки фильтров наверху страницы, но не для узкого (180px) сайдбара графика, где вокруг инпута ещё нужны отступы. Добавить в конец `static/css/tri_results.css`:

```css
/* Поиск участника внутри сайдбара графика — тот же .tri-search, но на всю
   ширину узкого сайдбара (180px), с отступами по бокам вместо фикс. 180px. */
.tri-chart-sidebar .tri-search,
.tri-chart-sheet .tri-search {
    width: calc(100% - 24px);
    margin: 0 12px 8px;
    display: block;
}
```

- [ ] **Step 2: Добавить кнопку вкладки «График»**

В `templates/race_triatleta/duathlon_results.html`, в блоке `#page-tabs` (строка 31-36), после кнопки «Бег-2»:

```html
        <button class="tri-page-tab" data-tab="run2" onclick="switchPageTab('run2', this)">Бег-2</button>
```

добавить:

```html
        <button class="tri-page-tab" data-tab="chart" onclick="switchPageTab('chart', this)">График</button>
```

- [ ] **Step 3: Добавить разметку вкладки `tab-chart` (вне `.tri-container` — во всю ширину)**

После закрывающего `</div>` контейнера `.tri-container` (строка 64, `<div class="tri-container tri-container--full">...</div>`) и перед `<script>` (строка 66) вставить:

```html
    <div id="tab-chart" style="display:none">
        <div style="padding:12px 16px 0">
            <div class="filter-group" id="chart-mode-group">
                <button class="filter-btn active" data-mode="position" onclick="switchChartMode('position', this)">Позиция</button>
                <button class="filter-btn" data-mode="pace" onclick="switchChartMode('pace', this)">Темп/скорость</button>
            </div>
        </div>
        <div style="padding:10px 16px 0">
            <div class="filter-group" id="chart-stage-group"></div>
        </div>
        <div class="tri-chart-mobile-bar">
            <div class="tri-chart-mobile-trigger" onclick="openChartSheet()">
                <span class="tri-chart-mobile-label">Участники</span>
                <span class="tri-chart-mobile-badge" id="chart-mobile-badge">0</span>
                <span class="tri-chart-mobile-hint">нажмите для выбора ›</span>
            </div>
            <div class="tri-chart-mobile-chips" id="chart-mobile-chips"></div>
        </div>
        <div class="tri-chart-layout" style="padding:12px 16px">
            <div class="tri-chart-sidebar">
                <input type="search" class="tri-search" id="chart-search-input"
                       placeholder="Поиск участника..." oninput="onChartSearchInput(this.value)">
                <div class="tri-chart-sidebar__actions">
                    <button class="tri-chart-select-btn" id="chart-select-all-btn" onclick="toggleSelectAllChartFromUi()">Выбрать всех</button>
                </div>
                <div id="chart-legend-list"></div>
                <div class="tri-chart-sidebar__hint" id="chart-sidebar-hint">Выберите участников для сравнения</div>
            </div>
            <div class="tri-chart-main">
                <div class="tri-chart-mobile-info" id="chart-mobile-info" style="display:none"></div>
                <div class="tri-chart-wrap">
                    <canvas id="duathlon-chart-canvas"></canvas>
                </div>
            </div>
        </div>
        <div class="tri-refresh" id="chart-refresh-label"></div>
        <div class="tri-chart-sheet-overlay" id="chart-sheet-overlay" onclick="closeChartSheet()"></div>
        <div class="tri-chart-sheet" id="chart-sheet">
            <div class="tri-chart-sheet-handle"></div>
            <div class="tri-chart-sheet-header">
                <span>Выбор участников</span>
                <div class="tri-chart-sheet-header-actions">
                    <button class="tri-chart-sheet-header-btn" id="chart-sheet-select-all-btn" onclick="toggleSelectAllChartFromUi()">Выбрать всех</button>
                </div>
            </div>
            <input type="search" class="tri-search" id="chart-sheet-search-input"
                   placeholder="Поиск участника..." oninput="onChartSearchInput(this.value)">
            <div id="chart-sheet-list"></div>
        </div>
    </div>

    <script src="/static/lib/chart4/chart.umd.min.js"></script>
    <script src="/static/js/duathlon222-chart.js?v={{ v }}"></script>
```

(`{{ v }}` — та же cache-busting переменная, что уже используется для `tri_results.css` на строке 12.)

- [ ] **Step 4: Вписать таб «chart» в существующую логику переключения/URL-состояния**

В том же файле, функция `switchPageTab` (было):

```js
    function switchPageTab(name, btn) {
        _pageTab = name;
        document.querySelectorAll('.tri-page-tab').forEach(b => b.classList.remove('active'));
        (btn || document.querySelector(`.tri-page-tab[data-tab="${name}"]`)).classList.add('active');
        ['overall', 'run1', 'bike', 'run2'].forEach(name2 => {
            document.getElementById('tab-' + name2).style.display = name2 === name ? '' : 'none';
        });
        syncUrlFromState();
    }
```

заменить на:

```js
    function switchPageTab(name, btn) {
        _pageTab = name;
        document.querySelectorAll('.tri-page-tab').forEach(b => b.classList.remove('active'));
        (btn || document.querySelector(`.tri-page-tab[data-tab="${name}"]`)).classList.add('active');
        ['overall', 'run1', 'bike', 'run2', 'chart'].forEach(name2 => {
            document.getElementById('tab-' + name2).style.display = name2 === name ? '' : 'none';
        });
        if (name === 'chart') onChartTabShown();
        syncUrlFromState();
    }
```

Функция `readStateFromUrl` (было):

```js
    function readStateFromUrl() {
        const params = new URLSearchParams(location.search);
        const tab = params.get('tab');
        if (['overall', 'run1', 'bike', 'run2'].includes(tab)) _pageTab = tab;
```

заменить список на:

```js
        if (['overall', 'run1', 'bike', 'run2', 'chart'].includes(tab)) _pageTab = tab;
```

Функция `loadStandings` (было):

```js
            allStandings = data.standings || [];
            renderFiltered();
            renderRaceTimer();
```

заменить на:

```js
            allStandings = data.standings || [];
            renderFiltered();
            if (_pageTab === 'chart') renderActiveChart();
            renderRaceTimer();
```

- [ ] **Step 5: Ручная проверка (пока без `duathlon222-chart.js` — ожидаем ошибку в консоли, это нормально на этом шаге)**

Открыть `/duathlon222_2026` в браузере, кликнуть вкладку «График» → появляется пустой скелет (кнопки режима/этапа, пустой сайдбар, пустой canvas), в консоли браузера ошибка `onChartTabShown is not defined` — **это ожидаемо**, функция появится в Task 4. Главное — вкладка переключается, разметка не ломает остальные вкладки (проверить, что «Итоги гонки»/«Бег-1»/«Вело»/«Бег-2» по-прежнему работают).

- [ ] **Step 6: Commit**

```bash
git add templates/race_triatleta/duathlon_results.html static/css/tri_results.css
git commit -m "feat(duathlon222): разметка вкладки График (скелет, без данных)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: JS-тест-харнесс + виртуальные X-сегменты

**Files:**
- Create: `static/js/duathlon222-chart.js`
- Create: `tests/js/test_duathlon222_chart.js`

Перед началом — прочитать первые ~90 строк `tests/js/test_siberman_results_merge.js` (уже видел в этой сессии, но освежить): паттерн `node:vm`, `domStub`, `check()`. В отличие от Siberman (весь JS инлайн в `results.html`), у Дуатлона 222 логика графика — в ОТДЕЛЬНОМ файле `static/js/duathlon222-chart.js`, а вспомогательные глобалы (`STAGE_KM`, `STAGE_LABEL`, `fmtS`, `fmtPaceOrSpeed`) — в инлайн-скрипте `duathlon_results.html`. Тестовый харнесс грузит ОБА в один sandbox, в этом порядке (инлайн-скрипт первым — он объявляет `STAGE_KM` и т.п., до которых `duathlon222-chart.js` не обращается на верхнем уровне, только внутри тел функций, так что порядок для корректности не критичен, но так проще для читателя теста).

- [ ] **Step 1: Написать падающий тест**

Создать `tests/js/test_duathlon222_chart.js`:

```js
// Тесты чистых функций static/js/duathlon222-chart.js — те же паттерны
// node:vm/domStub/check(), что и tests/js/test_siberman_results_merge.js
// (см. первые ~90 строк того файла, если нужен более подробный образец).
// Запуск: node tests/js/test_duathlon222_chart.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const html = fs.readFileSync(path.join(ROOT, 'templates/race_triatleta/duathlon_results.html'), 'utf-8');
const inlineScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1])[0];
const chartJs = fs.readFileSync(path.join(ROOT, 'static/js/duathlon222-chart.js'), 'utf-8');

const elementsById = {};
function domStub(id) {
    if (id && elementsById[id]) return elementsById[id];
    const el = {
        innerHTML: '', style: {}, textContent: '', value: '',
        classList: { toggle() {}, add() {}, remove() {} },
        dataset: {}, addEventListener: () => {}, getContext: () => ({}),
    };
    if (id) elementsById[id] = el;
    return el;
}
class ChartStub {
    constructor(ctx, config) {
        this.config = config; this.options = config.options || {}; this.data = config.data || {};
        this.scales = {
            x: { getValueForPixel: px => px, getPixelForValue: v => v },
            y: { getValueForPixel: px => px, getPixelForValue: v => v },
        };
    }
    destroy() {}
    update() {}
    getDatasetMeta(i) {
        const ds = this.data.datasets?.[i];
        return { data: (ds?.data || []).map(p => ({ x: p.x, y: p.y })) };
    }
}
const sandbox = {
    console,
    document: {
        getElementById: (id) => domStub(id),
        querySelectorAll: () => [],
        querySelector: () => domStub(),
    },
    Chart: ChartStub,
    setInterval: () => 0,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    window: {},
    matchMedia: () => ({ matches: false }),
    getComputedStyle: () => ({ getPropertyValue: () => '#DE0000' }),
    URLSearchParams,
    location: { pathname: '/', search: '', hash: '' },
    history: { replaceState: () => {} },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(inlineScript, sandbox);
vm.runInContext(chartJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('kmToVirtualX: run1 km=0 -> начало сегмента (0)', () => {
    assert.strictEqual(sandbox.kmToVirtualX('run1', 0), 0);
});
check('kmToVirtualX: run1 km=10 (весь этап) -> конец сегмента (25)', () => {
    assert.strictEqual(sandbox.kmToVirtualX('run1', 10), 25);
});
check('kmToVirtualX: bike km=85 (половина 170) -> середина сегмента bike (25+25=50)', () => {
    assert.strictEqual(sandbox.kmToVirtualX('bike', 85), 50);
});
check('kmToVirtualX: run2 km=42 (весь этап) -> конец сегмента (100)', () => {
    assert.strictEqual(sandbox.kmToVirtualX('run2', 42), 100);
});
check('kmToVirtualX: км за пределами этапа (баг данных) не вылезает за границу сегмента', () => {
    assert.strictEqual(sandbox.kmToVirtualX('run1', 999), 25);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
```

- [ ] **Step 2: Запустить тест, убедиться что падает**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: `Cannot find module '.../static/js/duathlon222-chart.js'` (файла ещё нет) — ошибка чтения файла, весь скрипт падает с исключением до первого `check()`.

- [ ] **Step 3: Создать `static/js/duathlon222-chart.js` с виртуальными сегментами**

```js
// Дуатлон 222 — вкладка «График» (Позиция / Темп-скорость). Использует
// глобалы, объявленные в инлайн-скрипте duathlon_results.html (STAGE_KM,
// STAGE_LABEL, allStandings, _genderFilter, fmtS, fmtPaceOrSpeed) — общий
// global scope между classic <script> тегами одной страницы, без модулей
// (см. tests/js/test_duathlon222_chart.js — тот же приём, что и харнесс для
// Siberman). Спека: docs/superpowers/specs/2026-09-04-duathlon222-charts-design.md

const STAGE_ORDER = ['run1', 'bike', 'run2'];

// «Раздутые» сегменты оси X в режиме «Вся гонка» (см. спеку, раздел 3) —
// фиксированные доли ширины НЕЗАВИСИМО от реальных км этапа, иначе Бег-1
// (10км) и Бег-2 (42км) схлопнутся в нечитаемые полоски рядом с Вело (170км).
const CHART_VIRTUAL_SEGMENTS = {
    run1: { start: 0, end: 25 },
    bike: { start: 25, end: 75 },
    run2: { start: 75, end: 100 },
};

// Реальный км внутри этапа -> позиция на виртуальной оси X (0-100). Клэмп
// в границы сегмента — защита от кривых данных (км > длины этапа).
function kmToVirtualX(stageCode, km) {
    const seg = CHART_VIRTUAL_SEGMENTS[stageCode];
    const stageKm = STAGE_KM[stageCode];
    const frac = stageKm > 0 ? Math.min(1, Math.max(0, km / stageKm)) : 0;
    return seg.start + frac * (seg.end - seg.start);
}
```

- [ ] **Step 4: Запустить тест, убедиться что проходит**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: `ALL PASSED`, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add static/js/duathlon222-chart.js tests/js/test_duathlon222_chart.js
git commit -m "feat(duathlon222): виртуальные X-сегменты графика + тест-харнесс

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Ранжирование участников по позиции (`computeRanksAtPositions`)

**Files:**
- Modify: `static/js/duathlon222-chart.js`
- Modify: `tests/js/test_duathlon222_chart.js`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_duathlon222_chart.js`, перед финальным `console.log(failures === 0 ...`:

```js
check('computeRanksAtPositions: лидер по elapsedS получает ранг 1 на общей позиции', () => {
    const participants = [
        { bib: 1, points: [{ pos: 1, elapsedS: 100 }, { pos: 2, elapsedS: 210 }] },
        { bib: 2, points: [{ pos: 1, elapsedS: 90 }, { pos: 2, elapsedS: 200 }] },
    ];
    const ranks = sandbox.computeRanksAtPositions(participants);
    assert.deepStrictEqual(ranks.get(1), [{ x: 1, y: 2 }, { x: 2, y: 2 }]);
    assert.deepStrictEqual(ranks.get(2), [{ x: 1, y: 1 }, { x: 2, y: 1 }]);
});
check('computeRanksAtPositions: свои точки участника ранжируются по последней известной точке соперника НЕ ПОЗЖЕ этой позиции', () => {
    // Участник 2 ещё не дошёл до pos=2 (у него только pos=1) — на позиции 2
    // участника 1 берётся последнее известное значение участника 2 (100 на pos=1).
    const participants = [
        { bib: 1, points: [{ pos: 1, elapsedS: 150 }, { pos: 2, elapsedS: 260 }] },
        { bib: 2, points: [{ pos: 1, elapsedS: 100 }] },
    ];
    const ranks = sandbox.computeRanksAtPositions(participants);
    // На pos=2 участника 1 сравнение идёт с elapsedS=100 участника 2 (его
    // последняя известная точка) -> участник 1 (260) позади -> ранг 2.
    assert.deepStrictEqual(ranks.get(1), [{ x: 1, y: 2 }, { x: 2, y: 2 }]);
});
check('computeRanksAtPositions: точка участника без ни одного валидного соперника получает ранг 1 (только он сам)', () => {
    const participants = [
        { bib: 1, points: [{ pos: 5, elapsedS: 500 }] },
    ];
    const ranks = sandbox.computeRanksAtPositions(participants);
    assert.deepStrictEqual(ranks.get(1), [{ x: 5, y: 1 }]);
});
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: 3 новых теста FAIL (`sandbox.computeRanksAtPositions is not a function`), 5 ранее прошедших (`kmToVirtualX`) — по-прежнему PASS.

- [ ] **Step 3: Реализовать функцию**

Добавить в `static/js/duathlon222-chart.js` после `kmToVirtualX`:

```js
// Ранг участника в каждой ЕГО СОБСТВЕННОЙ точке — среди всех остальных,
// сравнивая elapsedS на момент этой же позиции (pos). У соперника берётся
// его ПОСЛЕДНЯЯ известная точка с pos <= текущей (интерполяция "назад" —
// тот же принцип, что у _live_gap_map на бэкенде, но здесь не гэп, а ранг).
// participants: [{ bib, points: [{pos, elapsedS, plotX?}, ...] }], points
// должны быть отсортированы по pos по возрастанию (гарантируется тем, что
// checkpoints с бэкенда уже отсортированы по lap_number). plotX, если
// указан, используется в возвращаемых точках вместо pos как x-координата
// (нужно для виртуальных X-сегментов режима "вся гонка" — см. Task 6).
function computeRanksAtPositions(participants) {
    const result = new Map();
    participants.forEach(p => result.set(p.bib, []));
    participants.forEach(p => {
        p.points.forEach(pt => {
            const atPos = participants.map(pp => {
                let val = null;
                for (const c of pp.points) {
                    if (c.pos <= pt.pos) val = c.elapsedS; else break;
                }
                return { bib: pp.bib, elapsedS: val };
            }).filter(e => e.elapsedS != null);
            atPos.sort((a, b) => a.elapsedS - b.elapsedS);
            const rank = atPos.findIndex(e => e.bib === p.bib) + 1;
            if (rank > 0) result.get(p.bib).push({ x: pt.plotX != null ? pt.plotX : pt.pos, y: rank });
        });
    });
    return result;
}
```

- [ ] **Step 4: Запустить, убедиться что проходит**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add static/js/duathlon222-chart.js tests/js/test_duathlon222_chart.js
git commit -m "feat(duathlon222): computeRanksAtPositions для графика Позиция

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Датасеты «Позиция» (одиночный этап и вся гонка)

**Files:**
- Modify: `static/js/duathlon222-chart.js`
- Modify: `tests/js/test_duathlon222_chart.js`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_duathlon222_chart.js`:

```js
function mkRow(bib, checkpoints) {
    return { start_number: bib, surname: `Уч${bib}`, name: 'Тест', checkpoints };
}

check('buildPositionDatasetsSingleStage: точки берутся из checkpoints[stage], x=km, y=ранг', () => {
    const rows = [
        mkRow(1, { run1: [{ lap: 0, km: 0, elapsed_s: 0 }, { lap: 1, km: 1.25, elapsed_s: 300 }] }),
        mkRow(2, { run1: [{ lap: 0, km: 0, elapsed_s: 0 }, { lap: 1, km: 1.25, elapsed_s: 280 }] }),
    ];
    const datasets = sandbox.buildPositionDatasetsSingleStage('run1', rows);
    const ds1 = datasets.find(d => d._bib === 1);
    const ds2 = datasets.find(d => d._bib === 2);
    assert.deepStrictEqual(ds1.data, [{ x: 0, y: 1 }, { x: 1.25, y: 2 }]);
    assert.deepStrictEqual(ds2.data, [{ x: 0, y: 1 }, { x: 1.25, y: 1 }]);
});
check('buildPositionDatasetsSingleStage: участник без отметок этого этапа не попадает в датасеты', () => {
    const rows = [mkRow(1, { run1: [] }), mkRow(2, { run1: [{ lap: 0, km: 0, elapsed_s: 0 }] })];
    const datasets = sandbox.buildPositionDatasetsSingleStage('run1', rows);
    assert.strictEqual(datasets.length, 1);
    assert.strictEqual(datasets[0]._bib, 2);
});
check('buildPositionDatasetsWholeRace: км второго/третьего этапа считается от глобального накопления, x — виртуальный', () => {
    const rows = [
        mkRow(1, {
            run1: [{ lap: 0, km: 0, elapsed_s: 0 }, { lap: 8, km: 9.98, elapsed_s: 3000 }],
            bike: [{ lap: 0, km: 0, elapsed_s: 3100 }, { lap: 1, km: 3.4, elapsed_s: 3700 }],
            run2: [],
        }),
    ];
    const datasets = sandbox.buildPositionDatasetsWholeRace(rows);
    const ds = datasets[0];
    // run1: x = kmToVirtualX('run1', km); bike: x = kmToVirtualX('bike', km)
    assert.strictEqual(ds.data[0].x, sandbox.kmToVirtualX('run1', 0));
    assert.strictEqual(ds.data[1].x, sandbox.kmToVirtualX('run1', 9.98));
    assert.strictEqual(ds.data[2].x, sandbox.kmToVirtualX('bike', 0));
    assert.strictEqual(ds.data[3].x, sandbox.kmToVirtualX('bike', 3.4));
    assert.strictEqual(ds.data.length, 4); // run2 пуст — 0 точек оттуда
});
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: 3 новых теста FAIL (функций ещё нет), остальные — PASS.

- [ ] **Step 3: Реализовать обе функции**

Добавить в `static/js/duathlon222-chart.js` после `computeRanksAtPositions`:

```js
function buildPositionDatasetsSingleStage(stageCode, rows) {
    const participants = rows.map(r => ({
        bib: r.start_number,
        name: `${r.surname} ${r.name}`,
        points: (r.checkpoints?.[stageCode] || []).map(cp => ({ pos: cp.km, elapsedS: cp.elapsed_s })),
    })).filter(p => p.points.length);
    const ranks = computeRanksAtPositions(participants);
    return participants.map(p => ({ _bib: p.bib, _name: p.name, data: ranks.get(p.bib) }));
}

function buildPositionDatasetsWholeRace(rows) {
    const participants = rows.map(r => {
        const points = [];
        let globalBase = 0;
        STAGE_ORDER.forEach(sc => {
            (r.checkpoints?.[sc] || []).forEach(cp => {
                points.push({
                    pos: globalBase + cp.km,
                    elapsedS: cp.elapsed_s,
                    plotX: kmToVirtualX(sc, cp.km),
                });
            });
            globalBase += STAGE_KM[sc];
        });
        return { bib: r.start_number, name: `${r.surname} ${r.name}`, points };
    }).filter(p => p.points.length);
    const ranks = computeRanksAtPositions(participants);
    return participants.map(p => ({ _bib: p.bib, _name: p.name, data: ranks.get(p.bib) }));
}
```

- [ ] **Step 4: Запустить, убедиться что проходит**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add static/js/duathlon222-chart.js tests/js/test_duathlon222_chart.js
git commit -m "feat(duathlon222): датасеты Позиция (этап/вся гонка)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: Датасеты «Темп/Скорость»

**Files:**
- Modify: `static/js/duathlon222-chart.js`
- Modify: `tests/js/test_duathlon222_chart.js`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_duathlon222_chart.js`:

```js
check('buildPaceDatasets: скорость всегда км/ч (dKm/dT*3600), даже для беговых этапов', () => {
    const rows = [mkRow(1, { run1: [
        { lap: 0, km: 0, elapsed_s: 0 },
        { lap: 1, km: 1.25, elapsed_s: 300 }, // 1.25км за 300с = 15 км/ч
    ] })];
    const datasets = sandbox.buildPaceDatasets('run1', rows);
    assert.strictEqual(datasets.length, 1);
    assert.strictEqual(datasets[0].data.length, 1);
    assert.strictEqual(datasets[0].data[0].x, 1.25);
    assert.ok(Math.abs(datasets[0].data[0].y - 15) < 0.001);
});
check('buildPaceDatasets: меньше 2 отметок на этапе -> нет сплитов, участник не попадает в список', () => {
    const rows = [mkRow(1, { run1: [{ lap: 0, km: 0, elapsed_s: 0 }] })];
    const datasets = sandbox.buildPaceDatasets('run1', rows);
    assert.strictEqual(datasets.length, 0);
});
check('buildPaceDatasets: нулевая/отрицательная дельта км или времени пропускается (защита от кривых данных)', () => {
    const rows = [mkRow(1, { run1: [
        { lap: 0, km: 0, elapsed_s: 0 },
        { lap: 1, km: 0, elapsed_s: 300 },   // dKm=0 -> пропуск
        { lap: 2, km: 2.5, elapsed_s: 600 }, // относительно lap=1: dKm=2.5, dT=300
    ] })];
    const datasets = sandbox.buildPaceDatasets('run1', rows);
    assert.strictEqual(datasets[0].data.length, 1);
    assert.strictEqual(datasets[0].data[0].x, 2.5);
});
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: 3 новых теста FAIL, остальные PASS.

- [ ] **Step 3: Реализовать функцию**

Добавить в `static/js/duathlon222-chart.js`:

```js
// Y всегда км/ч (даже для беговых этапов) — единообразно с тем, как уже
// хранится _speed_kmh/current_stage_speed_kmh на бэкенде; перевод в темп
// (мин/км) — только на отображении, через уже существующий fmtPaceOrSpeed().
// Так не нужна условная инверсия оси Y между бегом/вело (быстрее = больше
// км/ч = выше на графике, для обоих типов этапов одинаково).
function buildPaceDatasets(stageCode, rows) {
    return rows.map(r => {
        const cps = r.checkpoints?.[stageCode] || [];
        const pts = [];
        for (let i = 1; i < cps.length; i++) {
            const dKm = cps[i].km - cps[i - 1].km;
            const dT = cps[i].elapsed_s - cps[i - 1].elapsed_s;
            if (dKm <= 0 || dT <= 0) continue;
            pts.push({ x: cps[i].km, y: dKm / (dT / 3600) });
        }
        return pts.length ? { _bib: r.start_number, _name: `${r.surname} ${r.name}`, data: pts } : null;
    }).filter(Boolean);
}
```

- [ ] **Step 4: Запустить, убедиться что проходит**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add static/js/duathlon222-chart.js tests/js/test_duathlon222_chart.js
git commit -m "feat(duathlon222): датасеты Темп/Скорость

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 8: Hit-test наведения на «спагетти»-линии

**Files:**
- Modify: `static/js/duathlon222-chart.js`
- Modify: `tests/js/test_duathlon222_chart.js`

Портируется из `templates/siberman/results.html` (`nearestDatasetIndexAtPixel`, строки ~2205-2231, уже прочитано ранее в этой сессии) — геометрический hit-test по интерполяции между соседними точками, а не по ближайшей одиночной точке (иначе при редких отметках подсвечивалась не та линия, что реально проходит под курсором — баг, найденный пользователем на Siberman 2026-07-22, тот же риск здесь при малом числе отметок на этапе).

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_duathlon222_chart.js`:

```js
check('nearestDatasetIndexAtPixel: курсор точно на линии участника 2 -> выбирает участника 2', () => {
    const chart = new ChartStub(null, { data: { datasets: [
        { data: [{ x: 0, y: 10 }, { x: 10, y: 20 }] },
        { data: [{ x: 0, y: 0 }, { x: 10, y: 0 }] },
    ] } });
    // ChartStub: 1px=1 единица, x=5 -> курсор между точками датасета 0
    // (y интерполируется в 15), датасета 1 (y=0). Курсор на y=15 -> ближе к 0-му.
    const idx = sandbox.nearestDatasetIndexAtPixel(chart, 5, 15);
    assert.strictEqual(idx, 0);
});
check('nearestDatasetIndexAtPixel: курсор левее первой точки -> берёт крайнюю левую точку линии', () => {
    const chart = new ChartStub(null, { data: { datasets: [
        { data: [{ x: 5, y: 50 }, { x: 10, y: 60 }] },
    ] } });
    const idx = sandbox.nearestDatasetIndexAtPixel(chart, 0, 50);
    assert.strictEqual(idx, 0);
});
check('nearestDatasetIndexAtPixel: maxDistPx ограничивает клик — далёкий клик мимо всех линий -> null', () => {
    const chart = new ChartStub(null, { data: { datasets: [
        { data: [{ x: 0, y: 0 }, { x: 10, y: 0 }] },
    ] } });
    const idx = sandbox.nearestDatasetIndexAtPixel(chart, 5, 500, 30);
    assert.strictEqual(idx, null);
});
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: 3 новых теста FAIL, остальные PASS.

- [ ] **Step 3: Реализовать функцию (порт с адаптацией имён из Siberman)**

Добавить в `static/js/duathlon222-chart.js`:

```js
// Какая ЛИНИЯ ближе всего к пикселю курсора/клика — по Y на прямой между
// двумя соседними по X точками ЭТОГО датасета, интерполированной РОВНО в X
// курсора (так же, как Chart.js физически рисует линию), а не по ближайшей
// одиночной точке. Портировано из templates/siberman/results.html
// (nearestDatasetIndexAtPixel) — тот же риск (редкие отметки на этапе
// Дуатлона 222, особенно Бег-1/Бег-2 с 8-25 точками на ~15 участников).
function nearestDatasetIndexAtPixel(chart, xPixel, yPixel, maxDistPx = null) {
    const xScale = chart.scales?.x, yScale = chart.scales?.y;
    if (!xScale || !yScale) return null;
    const cursorX = xScale.getValueForPixel(xPixel);
    let bestIdx = null, bestDist = Infinity;
    chart.data.datasets.forEach((ds, i) => {
        const pts = ds.data;
        if (!pts || pts.length === 0) return;
        let p0 = null, p1 = null;
        for (let k = 0; k < pts.length - 1; k++) {
            if (pts[k].x <= cursorX && cursorX <= pts[k + 1].x) { p0 = pts[k]; p1 = pts[k + 1]; break; }
        }
        let yAtCursor;
        if (p0 && p1) {
            const frac = p1.x === p0.x ? 0 : (cursorX - p0.x) / (p1.x - p0.x);
            yAtCursor = p0.y + frac * (p1.y - p0.y);
        } else {
            const edge = cursorX < pts[0].x ? pts[0] : pts[pts.length - 1];
            yAtCursor = edge.y;
        }
        const dist = Math.abs(yScale.getPixelForValue(yAtCursor) - yPixel);
        if (dist < bestDist) { bestDist = dist; bestIdx = i; }
    });
    if (bestIdx == null) return null;
    return (maxDistPx != null && bestDist > maxDistPx) ? null : bestIdx;
}
```

- [ ] **Step 4: Запустить, убедиться что проходит**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add static/js/duathlon222-chart.js tests/js/test_duathlon222_chart.js
git commit -m "feat(duathlon222): геометрический hit-test для спагетти-линий

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 9: Выбор участников — сайдбар/bottom-sheet (состояние + рендер списка)

**Files:**
- Modify: `static/js/duathlon222-chart.js`
- Modify: `tests/js/test_duathlon222_chart.js`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_duathlon222_chart.js`:

```js
check('chartToggleSelect: добавляет/убирает bib из выбора', () => {
    vm.runInContext('_chartSelectedBibs = []; _chartSearchQuery = "";', sandbox);
    sandbox.chartToggleSelect(9001);
    assert.deepStrictEqual(vm.runInContext('_chartSelectedBibs', sandbox), [9001]);
    sandbox.chartToggleSelect(9001);
    assert.deepStrictEqual(vm.runInContext('_chartSelectedBibs', sandbox), []);
});
check('chartFilteredParticipants: поиск фильтрует по фамилии (регистронезависимо)', () => {
    vm.runInContext('_chartSearchQuery = "иван";', sandbox);
    const rows = [mkRow(1, {}), mkRow(2, {})];
    rows[0].surname = 'Иванов'; rows[1].surname = 'Петров';
    const filtered = sandbox.chartFilteredParticipants(rows);
    assert.strictEqual(filtered.length, 1);
    assert.strictEqual(filtered[0].start_number, 1);
    vm.runInContext('_chartSearchQuery = "";', sandbox);
});
check('toggleSelectAllChart: если ничего не выбрано -> выбирает всех отфильтрованных; если все выбраны -> очищает', () => {
    vm.runInContext('_chartSelectedBibs = [];', sandbox);
    const rows = [mkRow(1, {}), mkRow(2, {})];
    rows.forEach(r => r.surname = 'Т');
    sandbox.toggleSelectAllChart(rows);
    assert.deepStrictEqual(vm.runInContext('_chartSelectedBibs', sandbox).sort(), [1, 2]);
    sandbox.toggleSelectAllChart(rows);
    assert.deepStrictEqual(vm.runInContext('_chartSelectedBibs', sandbox), []);
});
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: 3 новых теста FAIL, остальные PASS.

- [ ] **Step 3: Реализовать состояние выбора + вспомогательные функции**

Добавить в `static/js/duathlon222-chart.js` (в начало файла, рядом с `STAGE_ORDER`):

```js
let _chartMode = 'position';       // 'position' | 'pace'
let _chartStage = 'all';           // 'all'|'run1'|'bike'|'run2' (position) или 'run1'|'bike'|'run2' (pace)
let _chartSelectedBibs = [];       // номера участников, выбранных для сравнения
let _chartSearchQuery = '';
let _chartSheetOpen = false;       // мобильный bottom-sheet
```

и функции (после `buildPaceDatasets`):

```js
function chartToggleSelect(bib) {
    const idx = _chartSelectedBibs.indexOf(bib);
    if (idx !== -1) _chartSelectedBibs.splice(idx, 1);
    else _chartSelectedBibs.push(bib);
}
function chartFilteredParticipants(rows) {
    const q = _chartSearchQuery.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(r => (r.surname || '').toLowerCase().includes(q));
}
function toggleSelectAllChart(rows) {
    const filtered = chartFilteredParticipants(rows);
    const allSelected = filtered.length > 0 && filtered.every(r => _chartSelectedBibs.includes(r.start_number));
    if (allSelected) {
        const filteredBibs = new Set(filtered.map(r => r.start_number));
        _chartSelectedBibs = _chartSelectedBibs.filter(bib => !filteredBibs.has(bib));
    } else {
        filtered.forEach(r => { if (!_chartSelectedBibs.includes(r.start_number)) _chartSelectedBibs.push(r.start_number); });
    }
}
```

- [ ] **Step 4: Запустить, убедиться что проходит**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: `ALL PASSED`.

- [ ] **Step 5: Реализовать рендер списка (без юнит-теста — чистый DOM-рендер, проверяется вручную в Task 11)**

Добавить в `static/js/duathlon222-chart.js`:

```js
const CHART_COLORS = [
    '#FF8562', '#263146', '#18A558', '#DE0000', '#4B7BE5',
    '#F5A623', '#9B59B6', '#1ABC9C', '#E67E22', '#2C3E50',
];
function chartColorForBib(bib, sortedRows) {
    const idx = sortedRows.findIndex(r => r.start_number === bib);
    return CHART_COLORS[(idx >= 0 ? idx : 0) % CHART_COLORS.length];
}
function renderChartParticipantPickers(rows) {
    const sorted = rows.slice().sort((a, b) => a.surname.localeCompare(b.surname, 'ru'));
    const filtered = chartFilteredParticipants(sorted);
    const itemsHtml = filtered.map(r => {
        const color = chartColorForBib(r.start_number, sorted);
        const isActive = _chartSelectedBibs.includes(r.start_number);
        return `<div class="tri-chart-legend-item${isActive ? ' active' : ''}"
                     onclick="chartToggleSelect(${r.start_number});renderActiveChart()">
            <span class="tri-chart-legend-dot" style="background:${color}"></span>
            <span>${r.surname} ${r.name}</span>
        </div>`;
    }).join('') || '<div class="tri-chart-sidebar__hint">Ничего не найдено</div>';
    const selectAllLabel = filtered.length && filtered.every(r => _chartSelectedBibs.includes(r.start_number))
        ? 'Очистить всех' : 'Выбрать всех';

    document.getElementById('chart-legend-list').innerHTML = itemsHtml;
    document.getElementById('chart-sheet-list').innerHTML = itemsHtml;
    document.getElementById('chart-select-all-btn').textContent = selectAllLabel;
    document.getElementById('chart-sheet-select-all-btn').textContent = selectAllLabel;
    document.getElementById('chart-sidebar-hint').style.display = _chartSelectedBibs.length ? 'none' : '';
    document.getElementById('chart-mobile-badge').textContent = _chartSelectedBibs.length;

    const chipsEl = document.getElementById('chart-mobile-chips');
    chipsEl.innerHTML = _chartSelectedBibs.map(bib => {
        const r = sorted.find(rr => rr.start_number === bib);
        if (!r) return '';
        const color = chartColorForBib(bib, sorted);
        return `<div class="tri-chart-mobile-chip">
            <span class="tri-chart-mobile-chip-dot" style="background:${color}"></span>${r.surname}</div>`;
    }).join('');
}
function onChartSearchInput(value) {
    _chartSearchQuery = value;
    renderActiveChart();
}
// toggleSelectAllChart() принимает rows явным параметром (нужно для
// юнит-теста без обращения к allStandings) — разметке нужен вызов без
// аргументов, отсюда обёртка (использует getChartFilteredStandings() —
// появится в Task 10, но вызывается только по клику пользователя, не при
// загрузке скрипта, так что порядок объявления функций в файле не важен —
// function-декларации поднимаются в область видимости целиком).
function toggleSelectAllChartFromUi() {
    toggleSelectAllChart(getChartFilteredStandings());
    renderActiveChart();
}
function openChartSheet() {
    _chartSheetOpen = true;
    document.getElementById('chart-sheet').classList.add('open');
    document.getElementById('chart-sheet-overlay').classList.add('open');
}
function closeChartSheet() {
    _chartSheetOpen = false;
    document.getElementById('chart-sheet').classList.remove('open');
    document.getElementById('chart-sheet-overlay').classList.remove('open');
}
```

Разметка (Task 3) уже вызывает `onclick="toggleSelectAllChartFromUi()"` (не саму `toggleSelectAllChart`, которая требует явный параметр `rows` — нужен для юнит-теста без обращения к `allStandings`) — здесь просто добавляется реализация этой обёртки, в `duathlon_results.html` ничего менять не нужно.

- [ ] **Step 6: Запустить полный JS-набор ещё раз (регрессия)**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: `ALL PASSED`.

- [ ] **Step 7: Commit**

```bash
git add static/js/duathlon222-chart.js templates/race_triatleta/duathlon_results.html tests/js/test_duathlon222_chart.js
git commit -m "feat(duathlon222): сайдбар/bottom-sheet выбора участников графика

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 10: Рендер Chart.js — спагетти/сравнение, режимы, оркестрация

**Files:**
- Modify: `static/js/duathlon222-chart.js`

Финальная сборка — здесь нет новых чистых функций для юнит-теста (Chart.js-рендер и DOM-оркестрация), проверяется вручную в Task 11. Добавить в конец `static/js/duathlon222-chart.js`:

- [ ] **Step 1: Опции режимов/этапов и переключатели**

```js
const CHART_STAGE_OPTIONS = {
    position: [
        { code: 'all', label: 'Вся гонка' },
        { code: 'run1', label: 'Бег-1' },
        { code: 'bike', label: 'Вело' },
        { code: 'run2', label: 'Бег-2' },
    ],
    pace: [
        { code: 'run1', label: 'Бег-1' },
        { code: 'bike', label: 'Вело' },
        { code: 'run2', label: 'Бег-2' },
    ],
};
function switchChartMode(mode, btn) {
    _chartMode = mode;
    document.querySelectorAll('#chart-mode-group .filter-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
    _chartStage = mode === 'position' ? 'all' : 'run1';
    renderChartStageButtons();
    renderActiveChart();
}
function renderChartStageButtons() {
    const group = document.getElementById('chart-stage-group');
    group.innerHTML = CHART_STAGE_OPTIONS[_chartMode].map(opt =>
        `<button class="filter-btn${opt.code === _chartStage ? ' active' : ''}" onclick="switchChartStage('${opt.code}', this)">${opt.label}</button>`
    ).join('');
}
function switchChartStage(code, btn) {
    _chartStage = code;
    document.querySelectorAll('#chart-stage-group .filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderActiveChart();
}
```

- [ ] **Step 2: Точка входа графика (вызывается из `duathlon_results.html`)**

```js
function getChartFilteredStandings() {
    // allStandings уже отфильтрован по полу на бэкенде (см. setGenderFilter/
    // loadStandings в инлайн-скрипте) — здесь дополнительно убираем тех, у
    // кого вообще нет ни одной отметки (иначе на графике пустые линии).
    return (typeof allStandings !== 'undefined' ? allStandings : [])
        .filter(r => r.checkpoints && Object.values(r.checkpoints).some(arr => arr.length));
}
function onChartTabShown() {
    if (!document.getElementById('chart-stage-group').innerHTML) renderChartStageButtons();
    renderActiveChart();
}
function renderActiveChart() {
    const rows = getChartFilteredStandings();
    renderChartParticipantPickers(rows);
    if (_chartMode === 'position') renderPositionChart(rows);
    else renderPaceChart(rows);
    const label = document.getElementById('chart-refresh-label');
    if (label) label.textContent = `Обновлено: ${new Date().toLocaleTimeString('ru-RU')}`;
}
```

- [ ] **Step 3: Границы этапов (только для режима «Вся гонка»)**

```js
function chartStageBoundaries() {
    return STAGE_ORDER.slice(0, -1).map(sc => ({
        x: CHART_VIRTUAL_SEGMENTS[sc].end,
        label: STAGE_LABEL[sc] + ' →',
    }));
}
const stageBoundaryPlugin = {
    id: 'stageBoundary',
    afterDatasetsDraw(chart) {
        const boundaries = chart._stageBoundaries;
        if (!boundaries || !boundaries.length) return;
        const { ctx, chartArea, scales } = chart;
        if (!chartArea) return;
        ctx.save();
        ctx.strokeStyle = 'rgba(0,0,0,0.15)';
        ctx.setLineDash([4, 4]);
        ctx.font = '700 11px Onest, Arial, sans-serif';
        ctx.fillStyle = 'var(--tri-muted)';
        boundaries.forEach(b => {
            const px = scales.x.getPixelForValue(b.x);
            ctx.beginPath();
            ctx.moveTo(px, chartArea.top);
            ctx.lineTo(px, chartArea.bottom);
            ctx.stroke();
            ctx.fillText(b.label, px + 4, chartArea.top + 12);
        });
        ctx.restore();
    },
};
```

- [ ] **Step 4: Общий рендер спагетти/сравнение (используется и Позицией, и Темпом)**

```js
let _duathlonChart = null;

function renderSpaghettiOrCompareChart(datasets, opts) {
    const wrap = document.getElementById('duathlon-chart-canvas').parentElement;
    if (!datasets.length) {
        if (_duathlonChart) { _duathlonChart.destroy(); _duathlonChart = null; }
        wrap.innerHTML = '<canvas id="duathlon-chart-canvas"></canvas>' +
            '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--tri-muted);font-size:14px;text-align:center;padding:24px">Нет данных</div>';
        return;
    }
    if (!document.getElementById('duathlon-chart-canvas').isConnected) {
        wrap.innerHTML = '<canvas id="duathlon-chart-canvas"></canvas>';
    }
    const hasSelection = _chartSelectedBibs.length > 0;
    const chartDatasetBibs = datasets.map(d => d._bib);
    const sortedForColor = datasets.slice().sort((a, b) => a._name.localeCompare(b._name, 'ru'));

    const chartDatasets = datasets.map(d => {
        const isSelected = hasSelection && _chartSelectedBibs.includes(d._bib);
        const color = chartColorForBib(d._bib, sortedForColor.map(x => ({ start_number: x._bib })));
        let borderColor, borderWidth;
        if (!hasSelection) { borderColor = '#c8c8c8'; borderWidth = 1; }
        else if (isSelected) { borderColor = color; borderWidth = 2.5; }
        else { borderColor = '#e8e8e8'; borderWidth = 1; }
        return {
            _bib: d._bib, label: d._name, data: d.data,
            borderColor, backgroundColor: borderColor, borderWidth,
            pointRadius: 2, pointHoverRadius: 5, tension: 0.15, spanGaps: true,
        };
    });

    const ctx = document.getElementById('duathlon-chart-canvas').getContext('2d');
    const config = {
        type: 'line',
        data: { datasets: chartDatasets },
        plugins: [stageBoundaryPlugin],
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'nearest', intersect: false },
            plugins: {
                legend: { display: hasSelection },
                tooltip: {
                    filter: (item) => !hasSelection || _chartSelectedBibs.includes(chartDatasetBibs[item.datasetIndex]),
                    callbacks: { label: (item) => ` ${item.dataset.label}: ${opts.formatPoint(item.parsed.x, item.parsed.y)}` },
                },
            },
            scales: {
                x: opts.xScale || { type: 'linear' },
                y: {
                    reverse: !!opts.yReverse,
                    title: { display: true, text: opts.yLabel },
                    ticks: opts.yTickFormat ? { callback: v => opts.yTickFormat(v) } : {},
                },
            },
        },
    };
    if (_duathlonChart) { _duathlonChart.destroy(); _duathlonChart = null; }
    _duathlonChart = new Chart(ctx, config);
    _duathlonChart._stageBoundaries = opts.boundaries || null;
    if (!hasSelection) attachSpaghettiHover(_duathlonChart, chartDatasetBibs, opts.formatPoint);
    attachSpaghettiClick(_duathlonChart, chartDatasetBibs);
}

function attachSpaghettiHover(chart, chartDatasetBibs, formatPoint) {
    chart.options.onHover = function (evt) {
        const activeIdx = nearestDatasetIndexAtPixel(this, evt.x, evt.y);
        this.data.datasets.forEach((d, i) => {
            const active = i === activeIdx;
            d.borderColor = active ? getComputedStyle(document.documentElement).getPropertyValue('--tri-red') || '#DE0000' : '#c8c8c8';
            d.borderWidth = active ? 2.5 : 1;
        });
        this.update('none');
    };
}
function attachSpaghettiClick(chart, chartDatasetBibs) {
    chart.options.onClick = function (evt) {
        const idx = nearestDatasetIndexAtPixel(this, evt.x, evt.y, 30);
        if (idx == null) return;
        chartToggleSelect(chartDatasetBibs[idx]);
        renderActiveChart();
    };
}
```

- [ ] **Step 5: Position/Pace обёртки**

```js
function renderPositionChart(rows) {
    const datasets = _chartStage === 'all'
        ? buildPositionDatasetsWholeRace(rows)
        : buildPositionDatasetsSingleStage(_chartStage, rows);
    renderSpaghettiOrCompareChart(datasets, {
        yLabel: 'Место', yReverse: true,
        formatPoint: (x, y) => `место ${Math.round(y)}`,
        boundaries: _chartStage === 'all' ? chartStageBoundaries() : null,
    });
}
function renderPaceChart(rows) {
    const datasets = buildPaceDatasets(_chartStage, rows);
    renderSpaghettiOrCompareChart(datasets, {
        yLabel: _chartStage === 'bike' ? 'Скорость, км/ч' : 'Темп',
        yReverse: false,
        formatPoint: (x, y) => fmtPaceOrSpeed(_chartStage, y),
        yTickFormat: y => fmtPaceOrSpeed(_chartStage, y),
        boundaries: null,
    });
}
```

- [ ] **Step 6: Запустить полный JS-тест-набор (регрессия — новый код не должен ломать чистые функции из прошлых задач)**

Run: `node tests/js/test_duathlon222_chart.js`
Expected: `ALL PASSED` (Chart.js-рендер функции не покрыты юнит-тестами — это оркестрация с реальным DOM/Chart, проверяется вручную в Task 11 — но весь ранее протестированный чистый код должен остаться зелёным).

- [ ] **Step 7: Commit**

```bash
git add static/js/duathlon222-chart.js
git commit -m "feat(duathlon222): рендер графиков Позиция/Темп-скорость (Chart.js)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 11: Полная ручная проверка на dev-сервере

**Files:** нет изменений кода — только верификация.

- [ ] **Step 1: Запустить dev-сервер локально**

Использовать обычный способ запуска проекта (uvicorn/run-скрипт — какой уже используется в этом репозитории для локальной разработки; если не помнишь команду, посмотреть `README.md`/`Makefile`/существующие `run_*.sh` в корне).

- [ ] **Step 2: Пройти чеклист в браузере на `/duathlon222_2026`**

- [ ] Клик по вкладке «График» → появляется скелет без ошибок в консоли.
- [ ] По умолчанию режим «Позиция», этап «Вся гонка» — на графике видны серые линии всех участников с данными (спагетти), ось Y подписана «Место», 1-е место сверху.
- [ ] Видны 2 пунктирные вертикальные линии-границы этапов с подписями «Бег-1 →» / «Вело →».
- [ ] Клик по этапу «Бег-1» — X теперь реальные км (0-10), без границ-пунктиров.
- [ ] Переключение на «Темп/скорость» — стаб этапов меняется на Бег-1/Вело/Бег-2 (без «Вся гонка»), ось Y подписана «Темп» (Бег-1/Бег-2) или «Скорость, км/ч» (Вело), подписи тиков в формате мин/км или км/ч.
- [ ] Клик по участнику в сайдбаре — линия становится цветной, легенда Chart.js появляется, остальные — серые/бледные.
- [ ] Кнопка «Выбрать всех»/«Очистить всех» работает, текст переключается.
- [ ] Поиск в сайдбаре фильтрует список по фамилии.
- [ ] Навести курсор на серую (не выбранную) линию — она подсвечивается (без выбора участников).
- [ ] Клик по линии на графике (не по элементу сайдбара) — добавляет участника в сравнение.
- [ ] Сузить окно браузера до мобильной ширины (`<640px`) — сайдбар скрывается, появляется кнопка-триггер снизу с бейджем количества и чипами выбранных.
- [ ] Клик по триггеру — открывается bottom-sheet снизу, работает тот же список/поиск/«выбрать всех», кнопка закрытия/клик по фону закрывает.
- [ ] Переключить фильтр «Пол» (Мужчины/Женщины) на основных вкладках, затем вернуться на «График» — датасеты обновились под новый фильтр.
- [ ] Обновить страницу (F5) с URL `?tab=chart` — вкладка «График» открывается сразу, без ошибок в консоли.
- [ ] Подождать автообновление (30с) — график перерисовывается с обновлёнными данными без визуального "прыжка"/ошибок.

- [ ] **Step 3: Если что-то не так — исправить, отметить в этом файле какие пункты чеклиста провалились и как исправлено, до перехода к Task 12.**

- [ ] **Step 4: Прогнать полный набор тестов проекта (финальная регрессия)**

Run:
```bash
conda run -n base python -m pytest tests/unit/ -v
node tests/js/test_duathlon222_chart.js
node tests/js/test_siberman_results_merge.js
```

Expected: все PASS / `ALL PASSED` (второй JS-файл — регрессия, что новый код не сломал общие соглашения, если там что-то общее переиспользуется — по факту не переиспользуется, но лишняя проверка дёшева).

---

## Task 12: Деплой и прод-smoke-test

**Files:** нет изменений кода.

- [ ] **Step 1: Push в main (или через PR — как принято в этом репозитории для остальных фичей этой сессии)**

```bash
git push
```

- [ ] **Step 2: Дождаться деплоя через GitHub Actions**

```bash
gh run watch <run_id> --exit-status
```

(`<run_id>` — взять из `gh run list --limit 1` сразу после push.)

- [ ] **Step 3: Прод-smoke-test — curl + визуальная проверка**

```bash
curl -s https://live-race.triatleta.ru/api/duathlon222_2026/standings | python -c "import json,sys; d=json.load(sys.stdin); print(bool(d['standings'][0].get('checkpoints')))"
```

Expected: `True`.

Открыть `https://live-race.triatleta.ru/duathlon222_2026`, вкладка «График» — повторить ключевые пункты чеклиста Task 11 (Position spaghetti отображается, Pace/Speed отображается, сайдбар работает) уже на реальных production-данных.

- [ ] **Step 4: Доложить пользователю результат — что задеплоено, что проверено, ссылка на страницу.**
