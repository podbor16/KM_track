# Редизайн start_list.html — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать пустой серый баннер `.km-event-card` со страницы `start_list.html` и заменить статичный `<select>` фильтра пола на pill-кнопки (переиспользуя `.km-pill`/`.km-pills` CSS, уже задеплоенный для `results.html`), с попутным удалением теперь полностью мёртвого CSS.

**Architecture:** Второй под-проект программы редизайна Красмарафона (первый — `results.html`, уже задеплоен). В отличие от `results.html`, где пилюли пола генерировались JS по факту данных, здесь опции пола статичные (всегда «Все»/«Женщины»/«Мужчины») — pill-кнопки пишутся напрямую в HTML с `onclick`, JS только читает/переключает активное состояние через `data-value`. Полная спека: `docs/superpowers/specs/2026-08-13-krasmarafon-start-list-redesign-design.md`.

**Tech Stack:** Jinja2 HTML, ванильный JS (без фреймворка), CSS. Тесты — `node:vm` (в проекте нет JS-тест-фреймворка), pytest для бэкенда (не меняется в этой задаче, но полный прогон обязателен).

---

## Task 1: Failing-тест pill-логики фильтра пола

**Files:**
- Create: `tests/js/test_analytics_start_list_gender_pills.js`

Функции `getGenderFilterValue`/`_setGenderFilterActivePill`/`setGenderFilter` в `static/js/analytics-start-list.js` не существуют — тест должен упасть при запуске.

- [ ] **Step 1: Написать тестовый файл ровно с этим содержимым**

```javascript
// Тест pill-логики фильтра пола из static/js/analytics-start-list.js —
// замена статичного <select id="genderFilter"> на статичные pill-кнопки
// (часть редизайна start_list.html, см.
// docs/superpowers/specs/2026-08-13-krasmarafon-start-list-redesign-design.md).
// В отличие от tests/js/test_analytics_results_gender_pills.js (results.html,
// пилюли генерируются JS по данным), здесь опции пола СТАТИЧНЫЕ — тест сам
// строит 3 дочерних .km-pill элемента в genderFilter перед каждой проверкой,
// как это делает реальная разметка start_list.html.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_start_list_gender_pills.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-start-list.js'), 'utf-8');

// DOM-стаб с рабочим classList (Set поверх _classes) — нужен, т.к.
// _setGenderFilterActivePill() переключает .active класс у статичных
// дочерних кнопок через classList.toggle(), а не пересобирает их (в
// отличие от results.html, где пилюли каждый раз рендерятся заново).
function makeElement(tag) {
    const children = [];
    const classes = new Set();
    return {
        tagName: (tag || 'DIV').toUpperCase(),
        value: '',
        textContent: '',
        style: {},
        dataset: {},
        _children: children,
        get options() { return children.filter(c => c.tagName === 'OPTION'); },
        set innerHTML(v) { if (v === '') children.length = 0; },
        get innerHTML() { return ''; },
        appendChild(child) { children.push(child); return child; },
        addEventListener() {},
        querySelectorAll(sel) {
            if (sel === '.km-pill') return children.filter(c => c._classes && c._classes.has('km-pill'));
            return [];
        },
        classList: {
            add: (c) => classes.add(c),
            remove: (c) => classes.delete(c),
            toggle: (c, force) => {
                if (force === undefined) { classes.has(c) ? classes.delete(c) : classes.add(c); }
                else if (force) classes.add(c); else classes.delete(c);
            },
            contains: (c) => classes.has(c),
        },
        _classes: classes,
    };
}

// getElementById должен возвращать ОДИН и тот же объект на каждый вызов
// (та же ловушка, что в tests/js/test_siberman_results_merge.js и
// tests/js/test_analytics_results_gender_pills.js).
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement('DIV');
    return elementsById[id];
}
// Пересобирает элементы заново на каждый check(), включая статичную
// разметку 3 пилюль пола внутри #genderFilter — как в реальном HTML.
function resetDom() {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
    const container = domStub('genderFilter');
    container.dataset.value = '';
    ['', 'Женщина', 'Мужчина'].forEach(value => {
        const pill = makeElement('BUTTON');
        pill.dataset.value = value;
        pill._classes.add('km-pill');
        if (value === '') pill._classes.add('active');
        container.appendChild(pill);
    });
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: domStub,
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
        querySelectorAll: () => [],
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(utilsJs, sandbox);
vm.runInContext(scriptJs, sandbox);

// allRunners/filteredRunners — module-level `let` в analytics-start-list.js:
// недоступны как sandbox.allRunners напрямую (vm не экспонирует let-биндинги
// наружу), но присваивание КОДОМ внутри того же контекста видит существующий
// биндинг.
function setAllRunners(fixture) {
    vm.runInContext(`allRunners = ${JSON.stringify(fixture)};`, sandbox);
}
function getFilteredRunners() {
    return vm.runInContext('filteredRunners', sandbox);
}

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

const RUNNERS_MIXED = [
    { sex: 'Мужчина', surname: 'Иванов', name: 'Иван', category: 'мужчины до 49 лет', distance: '5 км' },
    { sex: 'Женщина', surname: 'Петрова', name: 'Анна', category: 'женщины до 49 лет', distance: '5 км' },
];

check('getGenderFilterValue() — "" по умолчанию', () => {
    resetDom();
    assert.strictEqual(sandbox.getGenderFilterValue(), '');
});

check('_setGenderFilterActivePill() — переключает data-value и .active класс, НЕ триггерит applyFilters', () => {
    resetDom();
    setAllRunners(RUNNERS_MIXED);
    vm.runInContext('applyFilters()', sandbox);
    assert.strictEqual(getFilteredRunners().length, 2);

    // "Портим" allRunners, чтобы доказать, что applyFilters НЕ перевызывался
    setAllRunners([]);
    sandbox._setGenderFilterActivePill('Мужчина');

    assert.strictEqual(sandbox.getGenderFilterValue(), 'Мужчина');
    const container = domStub('genderFilter');
    const activePill = container._children.find(c => c._classes.has('active'));
    assert.strictEqual(activePill.dataset.value, 'Мужчина');
    assert.strictEqual(getFilteredRunners().length, 2, 'filteredRunners не должен был пересчитаться');
});

check('setGenderFilter() — переключает пилюлю И запускает applyFilters (полная цепочка)', () => {
    resetDom();
    setAllRunners(RUNNERS_MIXED);
    sandbox.setGenderFilter('Женщина');

    assert.strictEqual(sandbox.getGenderFilterValue(), 'Женщина');
    const filtered = getFilteredRunners();
    assert.strictEqual(filtered.length, 1);
    assert.strictEqual(filtered[0].surname, 'Петрова');
});

check('setGenderFilter("") после setGenderFilter("Мужчина") возвращает "Все" и полный список', () => {
    resetDom();
    setAllRunners(RUNNERS_MIXED);
    sandbox.setGenderFilter('Мужчина');
    sandbox.setGenderFilter('');
    assert.strictEqual(sandbox.getGenderFilterValue(), '');
    assert.strictEqual(getFilteredRunners().length, 2);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
```

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `node tests/js/test_analytics_start_list_gender_pills.js`
Expected: несколько `FAIL` (минимум `sandbox.getGenderFilterValue is not a function` и аналогично для `_setGenderFilterActivePill`/`setGenderFilter`) — это ожидаемое RED-состояние, реализации ещё нет. Не пытаться чинить `analytics-start-list.js` — это Task 2.

- [ ] **Step 3: Commit**

```bash
git add tests/js/test_analytics_start_list_gender_pills.js
git commit -m "test(krasmarafon): failing-тест pill-логики фильтра пола start_list.html"
```

---

## Task 2: JS-логика пилюль в analytics-start-list.js

**Files:**
- Modify: `static/js/analytics-start-list.js` (4 отдельных find/replace-правки в одном файле)

### Правка 1: Гвард `updateEventCardBackground()` на отсутствующий `#eventCard`

Найти:
```javascript
function updateEventCardBackground() {
    const eventCard = document.getElementById('eventCard');
    const eventDisplayName = eventNameMap[currentEvent];
```
Заменить на:
```javascript
function updateEventCardBackground() {
    const eventCard = document.getElementById('eventCard');
    if (!eventCard) return;
    const eventDisplayName = eventNameMap[currentEvent];
```

### Правка 2: Сброс фильтра пола в `switchEvent()` без побочных вызовов

Найти:
```javascript
    // Сбрасываем фильтры
    document.getElementById('genderFilter').value = '';
    document.getElementById('ageGroupFilter').value = '';
```
Заменить на:
```javascript
    // Сбрасываем фильтры
    _setGenderFilterActivePill('');
    document.getElementById('ageGroupFilter').value = '';
```

### Правка 3: `populateAgeGroups()` использует новый геттер

Найти:
```javascript
function populateAgeGroups(runners) {
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const genderFilter = document.getElementById('genderFilter').value; // Получаем выбранный пол
```
Заменить на:
```javascript
function populateAgeGroups(runners) {
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const genderFilter = getGenderFilterValue(); // Получаем выбранный пол
```

### Правка 4: Новые функции + `applyFilters()` использует новый геттер

Найти:
```javascript
// Обработчик изменения пола - обновляет доступные возрастные группы
function onGenderChange() {
    // Пересчитываем доступные возрастные группы в зависимости от выбранного пола
    populateAgeGroups(allRunners);
    // Затем применяем все фильтры
    applyFilters();
}

// Применяем фильтры к данным
function applyFilters() {
    const genderFilter = document.getElementById('genderFilter').value;
```
Заменить на:
```javascript
// Текущее значение пилюли пола: '' | 'Мужчина' | 'Женщина'
function getGenderFilterValue() {
    return document.getElementById('genderFilter').dataset.value || '';
}

// Устанавливает активную пилюлю пола БЕЗ побочных вызовов (onGenderChange/
// applyFilters) — нужна для программного сброса (switchEvent()), где
// пересчёт фильтров и так произойдёт позже через loadRunnersData() на
// новых данных; вызывать его здесь преждевременно (тот же принцип, что и
// обычное присваивание select.value, которое не вызывает onchange).
function _setGenderFilterActivePill(value) {
    const container = document.getElementById('genderFilter');
    container.dataset.value = value;
    container.querySelectorAll('.km-pill').forEach(pill => {
        pill.classList.toggle('active', pill.dataset.value === value);
    });
}

// Переключает активную пилюлю пола — вызывается по клику (эквивалент
// прежнего onchange у <select>).
function setGenderFilter(value) {
    _setGenderFilterActivePill(value);
    onGenderChange();
}

// Обработчик изменения пола - обновляет доступные возрастные группы
function onGenderChange() {
    // Пересчитываем доступные возрастные группы в зависимости от выбранного пола
    populateAgeGroups(allRunners);
    // Затем применяем все фильтры
    applyFilters();
}

// Применяем фильтры к данным
function applyFilters() {
    const genderFilter = getGenderFilterValue();
```

- [ ] **Step 5: Запустить тест из Task 1 и убедиться, что он проходит**

Run: `node tests/js/test_analytics_start_list_gender_pills.js`
Expected: `ALL PASSED` (все 4 проверки `OK`)

- [ ] **Step 6: Commit**

```bash
git add static/js/analytics-start-list.js
git commit -m "feat(krasmarafon): pill-логика фильтра пола + гвард на отсутствующий eventCard (start_list.html)"
```

---

## Task 3: Разметка start_list.html

**Files:**
- Modify: `templates/krasmarafon/start_list.html`

Найти (блок от `<div class="km-page">` до конца `.km-toolbar`, т.е. всё до `<div id="loadingIndicator"`):
```html
    <div class="km-page">
        <h1 id="pageTitle">Стартовый список</h1>

        <!-- Карточка события с фото и селектором -->
        <div class="km-event-card" id="eventCard">
            <div class="km-event-card__overlay"></div>
            <div class="km-event-card__controls">
                <div class="km-select-group">
                    <label class="km-label" for="eventSelector">Событие:</label>
                    <select id="eventSelector" onchange="switchEvent()" class="km-select">
                        <option value="night_run">Ночной забег</option>
                        <option value="vesna">Весна</option>
                        <option value="colorrun">Красочный забег</option>
                        <option value="girlseven">Женская семерка</option>
                        <option value="zhara">Жара</option>
                        <option value="kids">Детский забег</option>
                        <option value="xtrailrun">Х Трейл</option>
                        <option value="snow7">Снежная семерка</option>
                    </select>
                </div>
                <div class="km-select-group">
                    <label class="km-label" for="yearStartSelector">Год:</label>
                    <select id="yearStartSelector" onchange="switchEvent()" class="km-select km-select--year"></select>
                </div>
            </div>
        </div>

        <div class="km-toolbar">
            <div class="km-filters">
                <div class="km-filter-group">
                    <label class="km-label" for="genderFilter">Пол:</label>
                    <select id="genderFilter" onchange="onGenderChange()" class="km-select">
                        <option value="">Все</option>
                        <option value="Мужчина">Мужчины</option>
                        <option value="Женщина">Женщины</option>
                    </select>
                </div>

                <div class="km-filter-group" id="ageGroupFilterGroup">
                    <label class="km-label" for="ageGroupFilter">Возрастная группа:</label>
                    <select id="ageGroupFilter" onchange="applyFilters()" class="km-select">
                        <!-- Возрастные группы будут заполнены динамически -->
                    </select>
                </div>

                <div class="km-filter-group" id="distanceFilterGroup">
                    <label class="km-label" for="distanceFilter">Дистанция:</label>
                    <select id="distanceFilter" onchange="applyFilters()" class="km-select">
                        <!-- Дистанции будут заполнены динамически -->
                    </select>
                </div>
            </div>
            <div class="km-filter-group km-search-group">
                <label class="km-label" for="surnameSearch">Поиск:</label>
                <input
                    type="text"
                    id="surnameSearch"
                    placeholder="Введите фамилию..."
                    onkeyup="applyFilters()"
                    class="km-input"
                >
            </div>
            <button class="km-btn-export" onclick="exportStartListPdf()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Скачать PDF
            </button>
        </div>
```

Заменить на:
```html
    <div class="km-page">
        <h1 id="pageTitle">Стартовый список</h1>

        <div class="km-toolbar">
            <div class="km-filters">
                <div class="km-filter-group">
                    <label class="km-label">Событие:</label>
                    <select id="eventSelector" onchange="switchEvent()" class="km-select">
                        <option value="night_run">Ночной забег</option>
                        <option value="vesna">Весна</option>
                        <option value="colorrun">Красочный забег</option>
                        <option value="girlseven">Женская семерка</option>
                        <option value="zhara">Жара</option>
                        <option value="kids">Детский забег</option>
                        <option value="xtrailrun">Х Трейл</option>
                        <option value="snow7">Снежная семерка</option>
                    </select>
                </div>
                <div class="km-filter-group">
                    <label class="km-label">Год:</label>
                    <select id="yearStartSelector" onchange="switchEvent()" class="km-select km-select--year"></select>
                </div>
                <div class="km-filter-group">
                    <label class="km-label" id="genderFilterLabel">Пол:</label>
                    <div class="km-pills" id="genderFilter" data-value="" role="group" aria-labelledby="genderFilterLabel">
                        <button type="button" class="km-pill active" data-value="" onclick="setGenderFilter('')">Все</button>
                        <button type="button" class="km-pill" data-value="Женщина" onclick="setGenderFilter('Женщина')">Женщины</button>
                        <button type="button" class="km-pill" data-value="Мужчина" onclick="setGenderFilter('Мужчина')">Мужчины</button>
                    </div>
                </div>

                <div class="km-filter-group" id="ageGroupFilterGroup">
                    <label class="km-label" for="ageGroupFilter">Возрастная группа:</label>
                    <select id="ageGroupFilter" onchange="applyFilters()" class="km-select">
                        <!-- Возрастные группы будут заполнены динамически -->
                    </select>
                </div>

                <div class="km-filter-group" id="distanceFilterGroup">
                    <label class="km-label" for="distanceFilter">Дистанция:</label>
                    <select id="distanceFilter" onchange="applyFilters()" class="km-select">
                        <!-- Дистанции будут заполнены динамически -->
                    </select>
                </div>
            </div>
            <div class="km-filter-group km-search-group">
                <label class="km-label" for="surnameSearch">Поиск:</label>
                <input
                    type="text"
                    id="surnameSearch"
                    placeholder="Введите фамилию..."
                    onkeyup="applyFilters()"
                    class="km-input"
                >
            </div>
            <button class="km-btn-export" onclick="exportStartListPdf()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Скачать PDF
            </button>
        </div>
```

Остальная часть файла (`#loadingIndicator`, `#errorIndicator`, `.km-table-wrap`, таблица, `<script>` теги, футер) не меняется.

- [ ] **Step 2: Commit**

```bash
git add templates/krasmarafon/start_list.html
git commit -m "feat(krasmarafon): start_list.html — убрать баннер события, пилюли вместо select для пола"
```

---

## Task 4: Удалить мёртвый CSS из analytics.css

**Files:**
- Modify: `static/css/analytics.css`

Проверено grep'ом по всему проекту (см. спеку) — после Task 3 классы `.km-event-card`, `.km-event-card__overlay`, `.km-event-card__controls`, `.km-select-group` не используются НИ В ОДНОМ шаблоне. `.km-pills`/`.km-pill` (используются новой разметкой) уже существуют в файле, их трогать не нужно.

### Правка 1: Основные определения

Найти:
```css
/* ── Event card ──────────────────────────────────── */
.km-event-card {
  position: relative;
  border-radius: var(--km-radius-card);
  overflow: hidden;
  height: 180px;
  margin-bottom: 18px;
  background-size: cover;
  background-position: center;
  box-shadow: 0 8px 24px rgba(0,0,0,.15);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 20px;
}
.km-event-card__overlay {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,.28);
}
.km-event-card__controls {
  position: relative;
  z-index: 2;
  background: rgba(255,255,255,.96);
  padding: 14px 20px;
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(0,0,0,.12);
  display: flex;
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
}
.km-select-group { display: flex; gap: 8px; align-items: center; }
.km-label { font-weight: 600; color: #333; font-size: 14px; white-space: nowrap; }
```
Заменить на:
```css
.km-label { font-weight: 600; color: #333; font-size: 14px; white-space: nowrap; }
```

### Правка 2: Mobile-overrides

Найти:
```css
  .km-event-card {
    height: 110px;
    padding: 0 12px;
    justify-content: center;
  }
  .km-event-card__controls { padding: 10px 12px; gap: 8px; width: 100%; }
  .km-toolbar { gap: 6px; }
```
Заменить на:
```css
  .km-toolbar { gap: 6px; }
```

- [ ] **Step 3: Проверить, что CSS валиден (нет незакрытых скобок)**

Открыть `static/css/analytics.css` и убедиться, что число `{` равно числу `}` (визуально — секция «Event card» отсутствует, `.km-page`-блок сразу переходит к `.km-label`/`.km-select`).

- [ ] **Step 4: Commit**

```bash
git add static/css/analytics.css
git commit -m "chore(krasmarafon): удалить мёртвый CSS .km-event-card/.km-select-group"
```

---

## Task 5: Полный прогон тестов + визуальная проверка

**Files:** нет изменений кода — только верификация.

- [ ] **Step 1: Запустить JS-тест из Task 1**

Run: `node tests/js/test_analytics_start_list_gender_pills.js`
Expected: `ALL PASSED`

- [ ] **Step 2: Запустить JS-тест results.html (не должен был затронуться, но проверить регрессию по общему analytics.css)**

Run: `node tests/js/test_analytics_results_gender_pills.js`
Expected: `ALL PASSED`

- [ ] **Step 3: Запустить полный Python test suite**

Run: `conda run -n base python -m pytest tests/unit/ tests/integration/ -q --deselect tests/integration/test_api_runners.py`
Expected: все тесты passed (`test_api_runners.py` исключён — падает без живой БД, не связано с этой задачей)

- [ ] **Step 4: Визуальная проверка в браузере (agent-browser)**

Запустить dev-сервер (`conda run -n base python -m uvicorn app:app --host 127.0.0.1 --port <свободный>`), открыть `/start_list` через `agent-browser open`. Т.к. без живой БД `loadRunnersData()` вернёт пустой список — подставить фикстуру напрямую через `agent-browser eval`:

```javascript
allRunners = [
  { sex: 'Мужчина', surname: 'Иванов', name: 'Иван', birthday: '1990-05-01', distance: '5 км', category: 'мужчины до 49 лет', city: 'Красноярск', club: '' },
  { sex: 'Женщина', surname: 'Петрова', name: 'Анна', birthday: '1992-03-15', distance: '5 км', category: 'женщины до 49 лет', city: 'Красноярск', club: '' }
];
populateAgeGroups(allRunners);
populateDistances(allRunners);
applyFilters();
```

Проверить на скриншоте (десктоп `1280x800` и мобильная ширина `390x700`, через `agent-browser set viewport <w> <h>`):
- Серого пустого баннера события нет, Событие/Год — обычные select в тулбаре
- Пилюли «Все»/«Женщины»/«Мужчины» отрисованы, клик по «Мужчины» подсвечивает её активной и фильтрует таблицу до одной строки (Иванов)
- На мобильной ширине фильтры переносятся, ничего не переполняет экран горизонтально

Если найдены визуальные баги — исправить и повторить проверку (тот же цикл, что был на `results.html`: 2 реальные регрессии там были пойманы именно на этом шаге, не тестами).

- [ ] **Step 5: Закрыть браузер и остановить dev-сервер**

```bash
agent-browser close
```
Остановить процесс uvicorn (найти PID по занятому порту, завершить).

---

## Self-Review (для исполнителя плана)

- Спека покрыта: баннер убран (Task 3), пилюли вместо select (Task 2+3), мёртвый CSS удалён (Task 4), тесты + визуальная проверка (Task 1, 5) — всё учтено.
- Сигнатуры функций согласованы между задачами: `getGenderFilterValue()`, `_setGenderFilterActivePill(value)`, `setGenderFilter(value)` — одинаковые имена в Task 1 (тест), Task 2 (реализация), Task 3 (HTML `onclick`).
- Плейсхолдеров нет — каждый шаг содержит точный код.
