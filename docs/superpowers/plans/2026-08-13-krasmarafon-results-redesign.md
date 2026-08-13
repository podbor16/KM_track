# Редизайн results.html (вариант C) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Довести `templates/krasmarafon/results.html` до современного вида, сохранив брендинг Красмарафона: убрать пустой баннер события, заменить фильтр «Пол» на pill-кнопки, сделать таблицу плотнее и убрать градиентный хэдер.

**Architecture:** Только фронтенд — HTML-разметка, CSS (`static/css/analytics.css`), клиентский JS (`static/js/analytics-results.js`, используется исключительно этим шаблоном). Бэкенд/API не трогаются. `.km-event-card`/`.km-select-group` CSS-классы НЕ удаляются — их использует `start_list.html` (отдельный будущий под-проект), просто `results.html` перестаёт применять эту разметку у себя.

**Tech Stack:** Jinja2-шаблон, ванильный JS (без фреймворка), CSS custom properties (`km-design-tokens.css`). Тесты JS — `node:vm` (в проекте нет JS-тест-фреймворка, тот же паттерн, что и `tests/js/test_siberman_results_merge.js`). Визуальная проверка — `agent-browser`.

Спека: `docs/superpowers/specs/2026-08-13-krasmarafon-results-redesign-design.md`

---

### Task 1: Failing-тест на pill-логику фильтра пола

**Files:**
- Create: `tests/js/test_analytics_results_gender_pills.js`

Функций `getGenderFilterValue`/`setGenderFilter` в `static/js/analytics-results.js` пока нет — тест должен упасть с `TypeError`.

- [ ] **Step 1: Написать тестовый файл**

```javascript
// Тест pill-логики фильтра пола из static/js/analytics-results.js (замена
// <select id="genderFilter"> на pill-кнопки, часть редизайна results.html,
// см. docs/superpowers/specs/2026-08-13-krasmarafon-results-redesign-design.md).
// В проекте нет JS-тест-фреймворка — используется node:vm, тот же паттерн,
// что и tests/js/test_siberman_results_merge.js.
// Запуск: node tests/js/test_analytics_results_gender_pills.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

// Генерирует минимальный DOM-стаб: элементы держат детей в _children (для
// select-подобных узлов .options — вычисляемое свойство поверх _children),
// className/textContent/dataset — обычные читаемые/записываемые поля.
function makeElement(tag) {
    const children = [];
    return {
        tagName: (tag || 'DIV').toUpperCase(),
        value: '',
        textContent: '',
        className: '',
        type: '',
        style: {},
        dataset: {},
        _children: children,
        get options() { return children.filter(c => c.tagName === 'OPTION'); },
        set innerHTML(v) { if (v === '') children.length = 0; },
        get innerHTML() { return ''; },
        appendChild(child) { children.push(child); return child; },
        addEventListener() {},
        querySelectorAll() { return []; },
    };
}

// getElementById должен возвращать ОДИН и тот же объект на каждый вызов
// (не новый) — иначе populateGenderFilter() пишет в объект, который тест
// уже не увидит (та же ловушка, что в tests/js/test_siberman_results_merge.js).
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement('DIV');
    return elementsById[id];
}
function resetDom() { for (const k of Object.keys(elementsById)) delete elementsById[k]; }

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: domStub,
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
        querySelectorAll: () => [],
    },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(utilsJs, sandbox);
vm.runInContext(scriptJs, sandbox);

// allRunners — module-level `let` в analytics-results.js: недоступен как
// sandbox.allRunners напрямую (vm не экспонирует let-биндинги наружу), но
// присваивание КОДОМ внутри того же контекста видит существующий биндинг.
function setAllRunners(fixture) {
    vm.runInContext(`allRunners = ${JSON.stringify(fixture)};`, sandbox);
}

let failures = 0;
function check(name, fn) {
    try {
        fn();
        console.log(`OK   ${name}`);
    } catch (e) {
        failures++;
        console.log(`FAIL ${name}: ${e.message}`);
    }
}

const RUNNERS_MIXED = [
    { gender: 'Мужчина', surname: 'Иванов', name: 'Иван', start_number: '1', rank_absolute: 1, rank_sex: 1, event: '5 км' },
    { gender: 'Женщина', surname: 'Петрова', name: 'Анна', start_number: '2', rank_absolute: 2, rank_sex: 1, event: '5 км' },
];
const RUNNERS_FEMALE_ONLY = [
    { gender: 'Женщина', surname: 'Сидорова', name: 'Ольга', start_number: '3', rank_absolute: 1, rank_sex: 1, event: '5 км' },
];

check('populateGenderFilter() — рендерит "Все" + пилюли по факту встречающихся полов, женщины раньше мужчин', () => {
    resetDom();
    sandbox.populateGenderFilter(RUNNERS_MIXED);
    const container = domStub('genderFilter');
    const labels = container._children.map(c => c.textContent);
    assert.deepStrictEqual(labels, ['Все', 'Женщина', 'Мужчина']);
    assert.strictEqual(container.dataset.value, '');
    assert.strictEqual(container._children[0].className, 'km-pill active');
});

check('populateGenderFilter() — не показывает пол, которого нет в данных', () => {
    resetDom();
    sandbox.populateGenderFilter(RUNNERS_FEMALE_ONLY);
    const labels = domStub('genderFilter')._children.map(c => c.textContent);
    assert.deepStrictEqual(labels, ['Все', 'Женщина']);
});

check('setGenderFilter()/getGenderFilterValue() — раунд-трип', () => {
    resetDom();
    setAllRunners(RUNNERS_MIXED);
    sandbox.populateGenderFilter(RUNNERS_MIXED);
    assert.strictEqual(sandbox.getGenderFilterValue(), '');

    sandbox.setGenderFilter('Мужчина');
    assert.strictEqual(sandbox.getGenderFilterValue(), 'Мужчина');
});

check('populateGenderFilter() — сброшенное значение (пола больше нет в данных) возвращается к "Все"', () => {
    resetDom();
    const container = domStub('genderFilter');
    container.dataset.value = 'Мужчина';
    sandbox.populateGenderFilter(RUNNERS_FEMALE_ONLY);
    assert.strictEqual(container.dataset.value, '');
});

check('applyFilters() — pill "Мужчина" оставляет в filteredRunners только мужчин', () => {
    resetDom();
    setAllRunners(RUNNERS_MIXED);
    sandbox.populateGenderFilter(RUNNERS_MIXED);
    sandbox.setGenderFilter('Мужчина');
    const filtered = vm.runInContext('filteredRunners', sandbox);
    assert.strictEqual(filtered.length, 1);
    assert.strictEqual(filtered[0].surname, 'Иванов');
});

check('getActiveRankField() — rank_absolute по умолчанию, rank_sex при выбранном поле, rank_category при выбранной возрастной группе', () => {
    resetDom();
    domStub('genderFilter').dataset.value = '';
    domStub('ageGroupFilter').value = '';
    assert.strictEqual(sandbox.getActiveRankField(), 'rank_absolute');

    domStub('genderFilter').dataset.value = 'Женщина';
    assert.strictEqual(sandbox.getActiveRankField(), 'rank_sex');

    domStub('ageGroupFilter').value = 'до 49';
    assert.strictEqual(sandbox.getActiveRankField(), 'rank_category');
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
```

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `node tests/js/test_analytics_results_gender_pills.js`
Expected: `TypeError: sandbox.populateGenderFilter is not a function` (или аналогичная ошибка — `getGenderFilterValue`/`setGenderFilter` тоже ещё не существуют)

- [ ] **Step 3: Commit**

```bash
git add tests/js/test_analytics_results_gender_pills.js
git commit -m "test(krasmarafon): failing-тест pill-логики фильтра пола results.html"
```

---

### Task 2: Реализация pill-логики в analytics-results.js

**Files:**
- Modify: `static/js/analytics-results.js:127-133` (`updateEventCardBackground`)
- Modify: `static/js/analytics-results.js:306-338` (`populateGenderFilter`)
- Modify: `static/js/analytics-results.js:343` (`populateAgeGroups`)
- Modify: `static/js/analytics-results.js:485` (`applyFilters`)
- Modify: `static/js/analytics-results.js:557` (`getActiveRankField`)

- [ ] **Step 1: Защитить `updateEventCardBackground()` от отсутствующего `#eventCard`**

После Task 3 в разметке `results.html` не будет `id="eventCard"` — без гварда функция упадёт на `eventCard.style...` и оборвёт `DOMContentLoaded`-обработчик (после неё уже не вызовется `loadRunnersData()`). Функция вызывается в двух местах (`DOMContentLoaded`, `switchEventResults()`) — проще и безопаснее защитить один раз внутри неё, чем трогать оба места вызова.

Файл: `static/js/analytics-results.js`, найти:
```javascript
function updateEventCardBackground() {
    const eventCard = document.getElementById('eventCard');
    const eventDisplayName = eventNameMap[currentEvent] || '';
```
Заменить на:
```javascript
function updateEventCardBackground() {
    const eventCard = document.getElementById('eventCard');
    if (!eventCard) return;
    const eventDisplayName = eventNameMap[currentEvent] || '';
```

- [ ] **Step 2: Переписать `populateGenderFilter()`, добавить `getGenderFilterValue()`/`setGenderFilter()`**

Найти блок (от комментария `// Заполняем опции пола...` до закрывающей `}` функции `populateGenderFilter`):
```javascript
// Заполняем опции пола — только те, что реально встречаются у участников
// (напр. на "Женской семёрке" мужчин нет вообще, не показываем такой вариант)
function populateGenderFilter(runners) {
    const genderSelect = document.getElementById('genderFilter');
    const savedValue = genderSelect.value;

    const genders = new Set();
    runners.forEach(runner => {
        if (runner.gender) genders.add(runner.gender);
    });

    genderSelect.innerHTML = '';

    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = 'Все';
    genderSelect.appendChild(allOption);

    // Женщина раньше Мужчины — соответствует порядку в остальном UI
    const order = { 'Женщина': 0, 'Мужчина': 1 };
    Array.from(genders).sort((a, b) => (order[a] ?? 99) - (order[b] ?? 99)).forEach(gender => {
        const option = document.createElement('option');
        option.value = gender;
        option.textContent = gender;
        genderSelect.appendChild(option);
    });

    if (savedValue && Array.from(genderSelect.options).some(opt => opt.value === savedValue)) {
        genderSelect.value = savedValue;
    } else {
        genderSelect.value = '';
    }
}
```

Заменить на:
```javascript
// Пилюли пола — только те, что реально встречаются у участников (напр. на
// "Женской семёрке" мужчин нет вообще, не показываем такой вариант).
// genderFilter — контейнер <div>, а не <select>: активное значение хранится
// в data-value, читается через getGenderFilterValue().
function populateGenderFilter(runners) {
    const container = document.getElementById('genderFilter');
    const savedValue = container.dataset.value || '';

    const genders = new Set();
    runners.forEach(runner => {
        if (runner.gender) genders.add(runner.gender);
    });

    // Женщина раньше Мужчины — соответствует порядку в остальном UI
    const order = { 'Женщина': 0, 'Мужчина': 1 };
    const sortedGenders = Array.from(genders).sort((a, b) => (order[a] ?? 99) - (order[b] ?? 99));
    const values = ['', ...sortedGenders];
    const newValue = values.includes(savedValue) ? savedValue : '';

    container.innerHTML = '';
    values.forEach(value => {
        const pill = document.createElement('button');
        pill.type = 'button';
        pill.className = 'km-pill' + (value === newValue ? ' active' : '');
        pill.textContent = value || 'Все';
        pill.addEventListener('click', () => setGenderFilter(value));
        container.appendChild(pill);
    });
    container.dataset.value = newValue;
}

// Текущее значение пилюли пола: '' | 'Мужчина' | 'Женщина'
function getGenderFilterValue() {
    return document.getElementById('genderFilter').dataset.value || '';
}

// Переключает активную пилюлю пола — вызывается по клику (эквивалент
// прежнего onchange у <select>). Дальнейший ре-рендер пилюль (с уже
// правильным активным значением) происходит внутри applyFilters() →
// populateGenderFilter(allRunners), как и раньше для select.
function setGenderFilter(value) {
    document.getElementById('genderFilter').dataset.value = value;
    onGenderChange();
}
```

- [ ] **Step 3: Обновить `populateAgeGroups()`**

Найти:
```javascript
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const genderFilter = document.getElementById('genderFilter').value; // Получаем выбранный пол
```
Заменить на:
```javascript
    const ageGroupSelect = document.getElementById('ageGroupFilter');
    const genderFilter = getGenderFilterValue(); // Получаем выбранный пол
```

- [ ] **Step 4: Обновить `applyFilters()`**

Найти:
```javascript
function applyFilters() {
    const genderFilter = document.getElementById('genderFilter').value;
```
Заменить на:
```javascript
function applyFilters() {
    const genderFilter = getGenderFilterValue();
```

- [ ] **Step 5: Обновить `getActiveRankField()`**

Найти:
```javascript
function getActiveRankField() {
    const genderFilter = document.getElementById('genderFilter').value;
```
Заменить на:
```javascript
function getActiveRankField() {
    const genderFilter = getGenderFilterValue();
```

- [ ] **Step 6: Запустить тест и убедиться, что он проходит**

Run: `node tests/js/test_analytics_results_gender_pills.js`
Expected: `ALL PASSED` (6/6 `OK`)

- [ ] **Step 7: Commit**

```bash
git add static/js/analytics-results.js
git commit -m "feat(krasmarafon): pill-логика фильтра пола + гвард на отсутствующий eventCard"
```

---

### Task 3: Разметка results.html — убрать баннер события, пилюли пола

**Files:**
- Modify: `templates/krasmarafon/results.html:23-83`

- [ ] **Step 1: Заменить блок карточки события + тулбар фильтров**

Найти (от `<div class="km-page">` до открывающего `<div id="loadingIndicator"`):
```html
    <div class="km-page">
      <h1 id="pageTitle">Результаты забега</h1>

      <div class="km-event-card" id="eventCard">
        <div class="km-event-card__overlay"></div>
        <div class="km-event-card__controls">
          <div class="km-select-group">
            <label class="km-label">Событие:</label>
            <select id="eventResultsSelector" onchange="switchEventResults()" class="km-select">
              <option value="night_run">Ночной забег</option>
              <option value="vesna">Весна</option>
              <option value="colorrun">Красочный забег</option>
              <option value="girlseven">Женская семерка</option>
              <option value="zhara">Жара</option>
              <option value="kids">Детский забег</option>
              <option value="xtrailrun">Х Трейл</option>
              <option value="snow7">Снежная семерка</option>
              <option value="pervomay">Первомайский полумарафон</option>
              <option value="dostigaya_tseli">Достигая цели</option>
            </select>
          </div>
          <div class="km-select-group">
            <label class="km-label">Год:</label>
            <select id="yearResultsSelector" onchange="switchEventResults()" class="km-select km-select--year">
            </select>
          </div>
        </div>
      </div>

      <div class="km-toolbar">
        <div class="km-filters">
          <div class="km-filter-group">
            <label class="km-label" for="genderFilter">Пол:</label>
            <select id="genderFilter" onchange="onGenderChange()" class="km-select">
              <option value="">Все</option>
            </select>
          </div>
          <div class="km-filter-group" id="ageGroupFilterGroup">
            <label class="km-label" for="ageGroupFilter">Возр. группа:</label>
            <select id="ageGroupFilter" onchange="applyFilters()" class="km-select"></select>
          </div>
          <div class="km-filter-group" id="distanceFilterGroup">
            <label class="km-label" for="distanceFilter">Дистанция:</label>
            <select id="distanceFilter" onchange="applyFilters()" class="km-select"></select>
          </div>
        </div>
        <div class="km-filter-group km-search-group">
          <label class="km-label" for="surnameSearch">Поиск:</label>
          <input type="text" id="surnameSearch" placeholder="Фамилия или номер..."
                 onkeyup="applyFilters()" class="km-input">
        </div>
        <button class="km-btn-export" onclick="exportResultsPdf()">
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
      <h1 id="pageTitle">Результаты забега</h1>

      <div class="km-toolbar">
        <div class="km-filters">
          <div class="km-filter-group">
            <label class="km-label">Событие:</label>
            <select id="eventResultsSelector" onchange="switchEventResults()" class="km-select">
              <option value="night_run">Ночной забег</option>
              <option value="vesna">Весна</option>
              <option value="colorrun">Красочный забег</option>
              <option value="girlseven">Женская семерка</option>
              <option value="zhara">Жара</option>
              <option value="kids">Детский забег</option>
              <option value="xtrailrun">Х Трейл</option>
              <option value="snow7">Снежная семерка</option>
              <option value="pervomay">Первомайский полумарафон</option>
              <option value="dostigaya_tseli">Достигая цели</option>
            </select>
          </div>
          <div class="km-filter-group">
            <label class="km-label">Год:</label>
            <select id="yearResultsSelector" onchange="switchEventResults()" class="km-select km-select--year">
            </select>
          </div>
          <div class="km-filter-group">
            <label class="km-label">Пол:</label>
            <div class="km-pills" id="genderFilter" data-value=""></div>
          </div>
          <div class="km-filter-group" id="ageGroupFilterGroup">
            <label class="km-label" for="ageGroupFilter">Возр. группа:</label>
            <select id="ageGroupFilter" onchange="applyFilters()" class="km-select"></select>
          </div>
          <div class="km-filter-group" id="distanceFilterGroup">
            <label class="km-label" for="distanceFilter">Дистанция:</label>
            <select id="distanceFilter" onchange="applyFilters()" class="km-select"></select>
          </div>
        </div>
        <div class="km-filter-group km-search-group">
          <label class="km-label" for="surnameSearch">Поиск:</label>
          <input type="text" id="surnameSearch" placeholder="Фамилия или номер..."
                 onkeyup="applyFilters()" class="km-input">
        </div>
        <button class="km-btn-export" onclick="exportResultsPdf()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Скачать PDF
        </button>
      </div>
```

(Остальная часть файла — `#loadingIndicator`, `#errorIndicator`, `.km-table-wrap` и всё, что ниже — не меняется.)

- [ ] **Step 2: Commit**

```bash
git add templates/krasmarafon/results.html
git commit -m "feat(krasmarafon): results.html — убрать баннер события, пилюли вместо select для пола"
```

---

### Task 4: CSS — пилюли, плоский хэдер таблицы, плотность, медали

**Files:**
- Modify: `static/css/analytics.css`

- [ ] **Step 1: Добавить стили `.km-pills`/`.km-pill`**

Найти:
```css
.km-input:focus, .km-select:focus { box-shadow: 0 0 0 3px rgba(238,45,98,.12); }

/* ── Toolbar & filters ───────────────────────────── */
```
Заменить на:
```css
.km-input:focus, .km-select:focus { box-shadow: 0 0 0 3px rgba(238,45,98,.12); }

/* ── Gender pill filter ──────────────────────────── */
.km-pills { display: flex; gap: 6px; }
.km-pill {
  padding: 7px 14px;
  border: 2px solid var(--km-primary);
  border-radius: var(--km-radius-btn, 50px);
  background: #fff;
  color: var(--km-primary);
  font-family: var(--km-font-ui);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.km-pill:hover { background: rgba(238,45,98,.08); }
.km-pill.active { background: var(--km-primary); color: #fff; }

/* ── Toolbar & filters ───────────────────────────── */
```

- [ ] **Step 2: Плоский хэдер таблицы вместо градиента**

Найти:
```css
.km-th {
  background: linear-gradient(to bottom, var(--km-primary), #1a1a1a);
  color: #fff;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .4px;
  font-size: 11px;
  padding: 12px 10px;
  white-space: nowrap;
  position: sticky;
  top: 0;
}
.km-th--c { text-align: center; }
.km-th--l { text-align: left; padding-left: 14px; }
.km-th--sort { cursor: pointer; }
.km-th--sort:hover { background: linear-gradient(to bottom, #c0234f, #111); }
```
Заменить на:
```css
.km-th {
  background: var(--km-primary);
  color: #fff;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .4px;
  font-size: 11px;
  padding: 9px 10px;
  white-space: nowrap;
  position: sticky;
  top: 0;
}
.km-th--c { text-align: center; }
.km-th--l { text-align: left; padding-left: 14px; }
.km-th--sort { cursor: pointer; }
.km-th--sort:hover { background: #c0234f; }
```

- [ ] **Step 3: Уплотнить `.km-td`**

Найти:
```css
.km-td {
  padding: 11px 10px;
  border-bottom: 1px solid #eaeaea;
  text-align: center;
}
```
Заменить на:
```css
.km-td {
  padding: 9px 10px;
  border-bottom: 1px solid #eaeaea;
  text-align: center;
}
```

- [ ] **Step 4: Усилить тень медальных бейджей**

Найти:
```css
.km-rank-medal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font-weight: 800;
  font-size: 13px;
  box-shadow: 0 2px 6px rgba(0,0,0,.2);
}
```
Заменить на:
```css
.km-rank-medal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font-weight: 800;
  font-size: 13px;
  box-shadow: 0 2px 8px rgba(0,0,0,.28);
}
```

- [ ] **Step 5: Commit**

```bash
git add static/css/analytics.css
git commit -m "feat(krasmarafon): results.html — плоский хэдер таблицы, плотность, тень медалей"
```

---

### Task 5: Полный прогон тестов + визуальная проверка в браузере

**Files:** нет изменений — только верификация.

- [ ] **Step 1: Прогнать JS-тест ещё раз (после всех правок)**

Run: `node tests/js/test_analytics_results_gender_pills.js`
Expected: `ALL PASSED`

- [ ] **Step 2: Прогнать python-тест-сьют (ничего python не менялось, но по конвенции проекта — перед отчётом о готовности)**

Run: `conda run -n base python -m pytest tests/unit/ tests/integration/ -q --deselect tests/integration/test_api_runners.py`
Expected: все тесты проходят (`test_api_runners.py` исключён — предсуществующе падает без живой БД, не связано с этой задачей)

- [ ] **Step 3: Запустить dev-сервер в фоне**

Run (Windows, использовать `run_in_background: true` для Bash-инструмента):
```bash
conda run -n base python -m uvicorn app:app --host 127.0.0.1 --port 8123
```
Подождать несколько секунд, проверить:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8123/results
```
Expected: `200`

- [ ] **Step 4: Открыть страницу в agent-browser, подставить фиктивные данные (БД не нужна)**

```bash
agent-browser open http://127.0.0.1:8123/results
agent-browser eval "allRunners = [
  { gender: 'Мужчина', surname: 'Иванов', name: 'Иван', start_number: '1', rank_absolute: 1, rank_sex: 1, event: '5 км', time_gun_finish: '00:16:03', time_clear_finish: '00:16:03', status: 'finished' },
  { gender: 'Женщина', surname: 'Петрова', name: 'Анна', start_number: '2', rank_absolute: 2, rank_sex: 1, event: '5 км', time_gun_finish: '00:17:10', time_clear_finish: '00:17:10', status: 'finished' },
  { gender: 'Мужчина', surname: 'Сидоров', name: 'Пётр', start_number: '3', rank_absolute: 3, rank_sex: 2, event: '5 км', time_gun_finish: '00:18:20', time_clear_finish: '00:18:20', status: 'finished' }
]; populateGenderFilter(allRunners); populateAgeGroups(allRunners); populateDistances(allRunners); applyFilters(); document.getElementById('resultsWrapper').style.display='';"
agent-browser screenshot results-redesign-desktop.png
```

Проверить на скриншоте: нет серого блока-баннера, «Пол» отображается пилюлями (Все/Женщина/Мужчина), таблица с плоским (не градиентным) розовым хэдером, у мест 1-2-3 — золотая/серебряная/бронзовая медаль.

- [ ] **Step 5: Клик по пилюле «Мужчина», проверить фильтрацию**

```bash
agent-browser find text "Мужчина" click
agent-browser screenshot results-redesign-filtered.png
```
Проверить: в таблице остались только 2 строки (Иванов, Сидоров), пилюля «Мужчина» подсвечена как активная (розовая заливка).

- [ ] **Step 6: Мобильная ширина**

```bash
agent-browser set viewport 390 700
agent-browser screenshot results-redesign-mobile.png
```
Проверить: таблица не переполняет экран по горизонтали, тулбар фильтров читаемо переносится на мобильном.

- [ ] **Step 7: Закрыть браузер и остановить dev-сервер**

```bash
agent-browser close
```
Затем найти и остановить процесс uvicorn на порту 8123 (Windows: через `Get-NetTCPConnection -LocalPort 8123` → `Stop-Process`, см. пример в сессии `2026-08-12-krasmarafon-hide-athlete-history`).

- [ ] **Step 8: Если найдены визуальные проблемы — завести отдельный fix-шаг, поправить, повторить Step 4-6 заново (не переходить к готово без повторной проверки)**

---

## Self-Review (проведён при написании плана)

- **Spec coverage**: все 3 пункта спеки (карточка события → тулбар, pill-фильтр пола, плоский хэдер+плотность+тень медалей) закрыты задачами 2-4.
- **Type consistency**: `getGenderFilterValue()`/`setGenderFilter()` используются одинаково во всех точках (Task 2 Steps 3-5, тесты Task 1).
- **Verified, not just written**: JS-код и тестовый харнесс (Task 1-2) уже прогнаны вживую при написании этого плана (node:vm, 6/6 `OK`) — не гипотетический код.
