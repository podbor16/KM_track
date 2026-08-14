# Редизайн athlete-profile.html — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Привести `athlete-profile.html` к единому `km-*` дизайн-языку (тот же, что уже задеплоен на `results.html`/`start_list.html`/`race-analysis.html`) — плоская шапка профиля с акцентной полосой, спокойные карточки забегов без hover-подъёма, фильтры и переключатель вида в стандартных `.km-toolbar`/`.km-pill` компонентах.

**Architecture:** Четвёртый под-проект программы редизайна Красмарафона. В отличие от предыдущих трёх страниц, JS этой страницы встроен прямо в Jinja-шаблон (`templates/krasmarafon/athlete-profile.html`, два `<script>`-блока), а не вынесен в отдельный `static/js/*.js` — тесты извлекают inline-скрипт регулярным выражением, тот же приём, что уже используется в `tests/js/test_siberman_participant.js` для `templates/siberman/participant.html`. Переключатель Сетка/Таблица получает ту же pill-логику (`getX()`/`_setXActivePill()`/`setX()`), что уже есть у фильтра пола на `results.html`/`start_list.html` (`static/js/analytics-start-list.js`). Страница остаётся скрыта флагом `history_enabled` на проде — эта задача не трогает флаг.

**Tech Stack:** Jinja2 HTML, ванильный JS (без фреймворка), CSS. Тесты — `node:vm` (в проекте нет JS-тест-фреймворка), pytest для бэкенда (не меняется в этой задаче, но полный прогон обязателен для проверки регрессии по общим CSS-файлам).

**Полная спека:** `docs/superpowers/specs/2026-08-14-krasmarafon-athlete-profile-redesign-design.md`

---

## Task 1: Failing-тест pill-логики переключателя вида

**Files:**
- Create: `tests/js/test_analytics_athlete_profile_view_toggle.js`

Функции `getViewMode`/`_setViewModeActivePill`/`setViewMode` в
`templates/krasmarafon/athlete-profile.html` не существуют — тест должен
упасть при запуске.

- [ ] **Step 1: Написать тестовый файл ровно с этим содержимым**

```javascript
// Тест pill-логики переключателя вида (Сетка/Таблица) в
// templates/krasmarafon/athlete-profile.html — замена кнопок
// .view-toggle-btn на статичные .km-pill (часть редизайна, см.
// docs/superpowers/specs/2026-08-14-krasmarafon-athlete-profile-redesign-design.md).
// JS этой страницы встроен прямо в шаблон (не отдельный static/js/*.js
// файл, в отличие от results.html/start_list.html) — извлекаем ВТОРОЙ
// <script>-блок (первый — только Jinja DIPLOMA_EVENT_IDS/raceHasDiploma/
// diplomaLinkHtml, к переключателю вида отношения не имеет), тот же приём,
// что в tests/js/test_siberman_participant.js.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_athlete_profile_view_toggle.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const html = fs.readFileSync(path.join(ROOT, 'templates/krasmarafon/athlete-profile.html'), 'utf-8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const inlineScript = scripts[1];

// DOM-стаб с рабочим classList (Set поверх _classes) — та же схема, что в
// tests/js/test_analytics_start_list_gender_pills.js: разметка
// переключателя (2 статичных .km-pill внутри #racesViewToggle) не
// пересобирается на каждый рендер, JS только переключает .active класс.
function makeElement(tag) {
    const children = [];
    const classes = new Set();
    return {
        tagName: (tag || 'DIV').toUpperCase(),
        style: {},
        dataset: {},
        _children: children,
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

const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement('DIV');
    return elementsById[id];
}
// Пересобирает статичную разметку переключателя + грид/таблицу заново
// перед каждой проверкой — как реальный HTML при загрузке страницы
// (грид виден по умолчанию, таблица скрыта, пилюля "Сетка" активна).
function resetDom() {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
    const container = domStub('racesViewToggle');
    container.dataset.value = 'grid';
    [['grid', true], ['table', false]].forEach(([value, active]) => {
        const pill = makeElement('BUTTON');
        pill.dataset.value = value;
        pill._classes.add('km-pill');
        if (active) pill._classes.add('active');
        container.appendChild(pill);
    });
    domStub('racesGrid').style.display = 'grid';
    domStub('racesTableWrapper').style.display = 'none';
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: domStub,
        addEventListener: () => {},
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(inlineScript, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('getViewMode() — "grid" по умолчанию', () => {
    resetDom();
    assert.strictEqual(sandbox.getViewMode(), 'grid');
});

check('_setViewModeActivePill() — переключает data-value и .active класс, НЕ трогает display', () => {
    resetDom();
    sandbox._setViewModeActivePill('table');

    assert.strictEqual(sandbox.getViewMode(), 'table');
    const container = domStub('racesViewToggle');
    const activePill = container._children.find(c => c._classes.has('active'));
    assert.strictEqual(activePill.dataset.value, 'table');
    assert.strictEqual(domStub('racesGrid').style.display, 'grid', 'display не должен был поменяться');
});

check('setViewMode("table") — переключает пилюлю И показывает таблицу/прячет сетку', () => {
    resetDom();
    sandbox.setViewMode('table');

    assert.strictEqual(sandbox.getViewMode(), 'table');
    assert.strictEqual(domStub('racesGrid').style.display, 'none');
    assert.strictEqual(domStub('racesTableWrapper').style.display, 'block');
});

check('setViewMode("grid") после setViewMode("table") возвращает исходное состояние', () => {
    resetDom();
    sandbox.setViewMode('table');
    sandbox.setViewMode('grid');

    assert.strictEqual(sandbox.getViewMode(), 'grid');
    assert.strictEqual(domStub('racesGrid').style.display, 'grid');
    assert.strictEqual(domStub('racesTableWrapper').style.display, 'none');
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
```

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `node tests/js/test_analytics_athlete_profile_view_toggle.js`
Expected: `TypeError: sandbox.getViewMode is not a function` (или аналогично
для `_setViewModeActivePill`/`setViewMode`) — RED-состояние, реализации
ещё нет. Не пытаться чинить `athlete-profile.html` — это Task 2.

- [ ] **Step 3: Commit**

```bash
git add tests/js/test_analytics_athlete_profile_view_toggle.js
git commit -m "test(krasmarafon): failing-тест pill-логики переключателя вида athlete-profile.html"
```

---

## Task 2: JS-логика пилюль переключателя вида + попутный фикс

**Files:**
- Modify: `templates/krasmarafon/athlete-profile.html` (2 правки во втором `<script>`-блоке + 1 правка — дублирующийся тег)

### Правка 1: Новые функции переключателя вида

Найти (непосредственно перед функцией `renderResults`):

```javascript
        // Отрисовать результаты
        function renderResults() {
```

Заменить на:

```javascript
        // Текущий режим отображения истории забегов: 'grid' | 'table'
        function getViewMode() {
            return document.getElementById('racesViewToggle').dataset.value || 'grid';
        }

        // Устанавливает активную пилюлю вида БЕЗ переключения видимости
        // блоков — используется только внутри setViewMode().
        function _setViewModeActivePill(value) {
            const container = document.getElementById('racesViewToggle');
            container.dataset.value = value;
            container.querySelectorAll('.km-pill').forEach(pill => {
                pill.classList.toggle('active', pill.dataset.value === value);
            });
        }

        // Переключает пилюлю вида и показывает соответствующий блок
        // (Сетка/Таблица) — вызывается по клику, эквивалент прежних
        // gridViewBtn.onclick/tableViewBtn.onclick.
        function setViewMode(value) {
            _setViewModeActivePill(value);
            document.getElementById('racesGrid').style.display = value === 'grid' ? 'grid' : 'none';
            document.getElementById('racesTableWrapper').style.display = value === 'table' ? 'block' : 'none';
        }

        // Отрисовать результаты
        function renderResults() {
```

### Правка 2: Убрать динамическое назначение onclick в `renderResults()`

Найти:

```javascript
            document.getElementById('noRaces').style.display = 'none';
            
            renderGridView();
            renderTableView();

            document.getElementById('gridViewBtn').onclick = () => {
                document.getElementById('racesGrid').style.display = 'grid';
                document.getElementById('racesTableWrapper').style.display = 'none';
                document.getElementById('gridViewBtn').classList.add('view-toggle-btn--active');
                document.getElementById('tableViewBtn').classList.remove('view-toggle-btn--active');
            };

            document.getElementById('tableViewBtn').onclick = () => {
                document.getElementById('racesGrid').style.display = 'none';
                document.getElementById('racesTableWrapper').style.display = 'block';
                document.getElementById('tableViewBtn').classList.add('view-toggle-btn--active');
                document.getElementById('gridViewBtn').classList.remove('view-toggle-btn--active');
            };
        }
```

Заменить на:

```javascript
            document.getElementById('noRaces').style.display = 'none';
            
            renderGridView();
            renderTableView();
        }
```

(Переключение теперь происходит через статичные `onclick="setViewMode(...)"`
в HTML — Task 3 — а не через динамическое назначение здесь.)

### Правка 3: Убрать дублирующийся `</script>`

Найти (самый конец файла):

```javascript
    </script>
    </script>
</body>
</html>
```

Заменить на:

```javascript
    </script>
</body>
</html>
```

- [ ] **Step 4: Запустить тест из Task 1 и убедиться, что он проходит**

Run: `node tests/js/test_analytics_athlete_profile_view_toggle.js`
Expected: `ALL PASSED` (все 4 проверки `OK`)

- [ ] **Step 5: Commit**

```bash
git add templates/krasmarafon/athlete-profile.html
git commit -m "feat(krasmarafon): pill-логика переключателя вида + фикс дублирующегося </script> (athlete-profile.html)"
```

---

## Task 3: Разметка — фильтры в km-toolbar, переключатель вида в km-pill

**Files:**
- Modify: `templates/krasmarafon/athlete-profile.html`

### Правка 1: Фильтры (Событие/Дистанция/Год)

Найти:

```html
                <div class="filters-container" id="filtersContainer" style="display: none;">
                    <div class="filter-group">
                        <label for="eventNameFilter">Название забега:</label>
                        <select id="eventNameFilter" class="filter-select">
                            <option value="">Все забеги</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="distanceFilter">Дистанция:</label>
                        <select id="distanceFilter" class="filter-select">
                            <option value="">Все дистанции</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label for="yearFilter">Год:</label>
                        <select id="yearFilter" class="filter-select">
                            <option value="">Все годы</option>
                        </select>
                    </div>
                    <button id="clearFiltersBtn" class="btn-filter-clear">Очистить фильтры</button>
                </div>
```

Заменить на:

```html
                <div class="km-toolbar" id="filtersContainer" style="display: none;">
                    <div class="km-filter-group">
                        <label class="km-label" for="eventNameFilter">Название забега:</label>
                        <select id="eventNameFilter" class="km-select">
                            <option value="">Все забеги</option>
                        </select>
                    </div>
                    <div class="km-filter-group">
                        <label class="km-label" for="distanceFilter">Дистанция:</label>
                        <select id="distanceFilter" class="km-select">
                            <option value="">Все дистанции</option>
                        </select>
                    </div>
                    <div class="km-filter-group">
                        <label class="km-label" for="yearFilter">Год:</label>
                        <select id="yearFilter" class="km-select">
                            <option value="">Все годы</option>
                        </select>
                    </div>
                    <button id="clearFiltersBtn" class="btn-filter-clear">Очистить фильтры</button>
                </div>
```

(`id`-ы не меняются — `renderFilters()`/`applyFilters()`/`clearFilters()` в
JS ничего не читают/пишут по классам этих элементов, только по `id`, так
что JS в этой правке не меняется.)

### Правка 2: Переключатель вида Сетка/Таблица

Найти:

```html
                <div id="racesViewToggle" style="margin-bottom: 20px;">
                    <button id="gridViewBtn" class="view-toggle-btn view-toggle-btn--active">Сетка</button>
                    <button id="tableViewBtn" class="view-toggle-btn">Таблица</button>
                </div>
```

Заменить на:

```html
                <div class="km-pills" id="racesViewToggle" data-value="grid" style="margin-bottom: 20px;" role="group" aria-label="Вид отображения">
                    <button type="button" class="km-pill active" data-value="grid" onclick="setViewMode('grid')">Сетка</button>
                    <button type="button" class="km-pill" data-value="table" onclick="setViewMode('table')">Таблица</button>
                </div>
```

- [ ] **Step 3: Запустить тест из Task 1 ещё раз (регрессия)**

Run: `node tests/js/test_analytics_athlete_profile_view_toggle.js`
Expected: `ALL PASSED` (разметка теста — DOM-стаб, реальный HTML этот тест
не читает, но прогон подтверждает, что JS-логика не пострадала)

- [ ] **Step 4: Commit**

```bash
git add templates/krasmarafon/athlete-profile.html
git commit -m "feat(krasmarafon): athlete-profile.html — фильтры в km-toolbar, переключатель вида в km-pill"
```

---

## Task 4: CSS — новый вид шапки, спокойные карточки, плоские блоки, удаление мёртвого CSS

**Files:**
- Modify: `static/css/athlete-profile.css`

### Правка 1: Шапка профиля (`.profile-header` → вариант C)

Найти:

```css
.profile-header {
    background: linear-gradient(135deg, #EE2D62 0%, #d41451 100%);
    color: #fff;
    padding: 40px;
    border-radius: 12px;
    margin-bottom: 40px;
    box-shadow: var(--km-shadow-hover, 0 4px 12px rgba(0,0,0,0.15));
}

.profile-header h1 {
    margin: 0 0 20px 0;
    font-size: 42px;
    font-weight: 700;
    letter-spacing: -0.5px;
    font-family: var(--km-font-brand, Arial, sans-serif);
}
```

Заменить на:

```css
.profile-header {
    background: #fff;
    border-left: 4px solid var(--km-primary, #EE2D62);
    padding: 24px 28px;
    border-radius: 0 12px 12px 0;
    margin-bottom: 40px;
    box-shadow: var(--km-shadow, 0 2px 8px rgba(0,0,0,0.1));
}

.profile-header h1 {
    margin: 0 0 14px 0;
    font-size: 32px;
    font-weight: 700;
    letter-spacing: -0.5px;
    color: var(--km-text-body, #333);
    font-family: var(--km-font-brand, Arial, sans-serif);
}
```

### Правка 2: Инфо-плашки шапки (`.info-item`/`.info-label`/`.info-value`)

Найти:

```css
.info-item {
    background: rgba(255, 255, 255, 0.15);
    padding: 18px;
    border-radius: 8px;
    border-left: 4px solid rgba(255, 255, 255, 0.8);
    transition: all 0.3s ease;
}

.info-item:hover {
    background: rgba(255, 255, 255, 0.25);
}

.info-label {
    font-size: 12px;
    text-transform: uppercase;
    opacity: 0.8;
    margin-bottom: 8px;
    letter-spacing: 0.5px;
    font-weight: 600;
}

.info-value {
    font-size: 20px;
    font-weight: 700;
}
```

Заменить на:

```css
.info-item {
    background: transparent;
    padding: 0;
    border-radius: 0;
    border-left: none;
}

.info-label {
    font-size: 11px;
    text-transform: uppercase;
    color: var(--km-text-muted, #aaa);
    margin-bottom: 6px;
    letter-spacing: 0.5px;
    font-weight: 600;
}

.info-value {
    font-size: 18px;
    font-weight: 700;
    color: var(--km-text-body, #333);
}
```

### Правка 3: Карточка забега — убрать hover-подъём (вариант B)

Найти:

```css
.race-card {
    background: #fff;
    border: 2px solid #f0f0f0;
    border-radius: 12px;
    padding: 24px;
    transition: all 0.3s ease;
    box-shadow: var(--km-shadow, 0 2px 8px rgba(0,0,0,0.1));
}

.race-card:hover {
    transform: translateY(-6px);
    box-shadow: 0 8px 24px rgba(238, 45, 98, 0.15);
    border-color: var(--km-primary, #EE2D62);
}
```

Заменить на:

```css
.race-card {
    background: #fff;
    border: 1px solid #f0f0f0;
    border-radius: 12px;
    padding: 22px;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
    box-shadow: 0 2px 6px rgba(0,0,0,.06);
}

.race-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,.1);
    border-color: var(--km-primary, #EE2D62);
}
```

### Правка 4: Расширенная статистика — убрать градиентный контейнер

Найти:

```css
.extended-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 20px;
    margin: 30px 0 50px 0;
    padding: 30px;
    background: linear-gradient(135deg, #f5f5f5 0%, #fafafa 100%);
    border-radius: 12px;
    border-left: 4px solid var(--km-primary, #EE2D62);
}

.extended-stat-item {
    background: #fff;
    padding: 20px;
    border-radius: 10px;
    box-shadow: var(--km-shadow, 0 2px 8px rgba(0,0,0,0.1));
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: all 0.3s ease;
}

.extended-stat-item:hover {
    transform: translateY(-3px);
    box-shadow: var(--km-shadow-hover, 0 4px 12px rgba(0,0,0,0.15));
}
```

Заменить на:

```css
.extended-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 20px;
    margin: 30px 0 50px 0;
}

.extended-stat-item {
    background: #fff;
    border: 1px solid var(--km-border-light, #e0e0e0);
    padding: 20px;
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: box-shadow 0.2s ease;
}

.extended-stat-item:hover {
    box-shadow: var(--km-shadow, 0 2px 8px rgba(0,0,0,0.1));
}
```

### Правка 5: Таблица истории — плоский `<thead>`

Найти:

```css
.races-table thead {
    background: linear-gradient(135deg, var(--km-primary, #EE2D62) 0%, #d41451 100%);
    color: #fff;
}
```

Заменить на:

```css
.races-table thead {
    background: var(--km-primary, #EE2D62);
    color: #fff;
}
```

### Правка 6: `.stat-card` — убрать hover-подъём

Найти:

```css
.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--km-shadow-hover, 0 4px 12px rgba(0,0,0,0.15));
}
```

Заменить на:

```css
.stat-card:hover {
  box-shadow: var(--km-shadow-hover, 0 4px 12px rgba(0,0,0,0.15));
}
```

### Правка 7: Удалить мёртвый CSS фильтров (заменены на `.km-toolbar`/`.km-select` в Task 3)

Найти:

```css
.filters-container {
    background: linear-gradient(135deg, #f9f9f9 0%, #fafafa 100%);
    padding: 20px;
    border-radius: 10px;
    margin-bottom: 25px;
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    align-items: flex-start;
    border-left: 4px solid var(--km-primary, #EE2D62);
}

.filter-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.filter-group label {
    font-size: 12px;
    font-weight: 700;
    color: #333;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

.filter-select {
    padding: 10px 14px;
    border: 2px solid #e0e0e0;
    border-radius: 6px;
    background: #fff;
    color: #333;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.3s ease;
    min-width: 150px;
}

.filter-select:hover,
.filter-select:focus {
    border-color: var(--km-primary, #EE2D62);
    outline: none;
    box-shadow: 0 0 0 3px rgba(238, 45, 98, 0.1);
}

.btn-filter-clear {
```

Заменить на:

```css
.btn-filter-clear {
```

(Оставляем только `.btn-filter-clear` — эта кнопка используется как есть,
см. спеку п.3. `.filters-container`/`.filter-group`/`.filter-select` были
только у старой панели фильтров.)

### Правка 8: Убрать ссылки на удалённые классы в мобильном media query

Найти:

```css
@media (max-width: 768px) {
    .charts-grid {
        grid-template-columns: 1fr;
    }
    
    .extended-stats {
        grid-template-columns: repeat(2, 1fr);
    }
    
    .filters-container {
        flex-direction: column;
        align-items: stretch;
    }
    
    .filter-select {
        min-width: 100%;
    }
}
```

Заменить на:

```css
@media (max-width: 768px) {
    .charts-grid {
        grid-template-columns: 1fr;
    }
    
    .extended-stats {
        grid-template-columns: repeat(2, 1fr);
    }
}
```

(Мобильное поведение `.km-toolbar`/`.km-select` уже покрыто их
собственными правилами в `analytics.css`.)

### Правка 9: Удалить мёртвый CSS переключателя вида (заменён на `.km-pill` в Task 3)

Найти (самый конец файла):

```css
/* ── View toggle buttons ─────────────────────────── */
.view-toggle-btn {
  padding: 8px 20px;
  border: 2px solid var(--km-primary, #EE2D62);
  border-radius: 20px;
  background: #fff;
  color: var(--km-primary, #EE2D62);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  font-family: var(--km-font-ui, Arial, sans-serif);
  transition: all .15s;
}
.view-toggle-btn + .view-toggle-btn { margin-left: 8px; }
.view-toggle-btn--active {
  background: var(--km-primary, #EE2D62);
  color: #fff;
}
```

Заменить на: (пусто — удалить блок целиком, файл заканчивается на
предыдущем правиле)

- [ ] **Step 10: Проверить, что CSS валиден (нет незакрытых скобок)**

Открыть `static/css/athlete-profile.css` и убедиться, что число `{`
равно числу `}` (визуально — файл заканчивается на правиле
`.races-table tbody tr:last-child td { border-bottom: none; }` / мобильном
блоке `.profile-header`/`.races-grid`, `.view-toggle-btn*` в конце
отсутствует).

- [ ] **Step 11: Commit**

```bash
git add static/css/athlete-profile.css
git commit -m "chore(krasmarafon): athlete-profile.css — плоская шапка/карточки/таблица, удалён мёртвый CSS фильтров и переключателя вида"
```

---

## Task 5: Полный прогон тестов + визуальная проверка

**Files:** нет изменений кода — только верификация.

- [ ] **Step 1: Запустить JS-тест из Task 1**

Run: `node tests/js/test_analytics_athlete_profile_view_toggle.js`
Expected: `ALL PASSED`

- [ ] **Step 2: Запустить остальные JS-тесты проекта (регрессия по общим паттернам)**

Run:
```bash
node tests/js/test_analytics_results_gender_pills.js
node tests/js/test_analytics_start_list_gender_pills.js
node tests/js/test_siberman_participant.js
```
Expected: `ALL PASSED` для каждого

- [ ] **Step 3: Запустить полный Python test suite**

Run: `conda run -n base python -m pytest tests/unit/ -q`
Expected: все тесты passed (страница не завязана на backend-логику
напрямую, но общие CSS/шаблонные файлы могли задеть другие роуты —
полный прогон исключает регресс)

- [ ] **Step 4: Визуальная проверка в браузере (agent-browser)**

Локально `history_enabled` включён по умолчанию (файл
`config/history_enabled.local` отсутствует в репозитории — читай
`src/config/event_loader.py:184-192`), так что `/athlete-profile` доступна
без дополнительных манипуляций с флагом.

Запустить dev-сервер:
```bash
conda run -n base python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Открыть через `agent-browser open http://127.0.0.1:8000/athlete-profile?surname=Иванов&name=Иван`.

Без живой БД `loadAthleteProfile()` получит ошибку `fetch` — подставить
фикстуру напрямую через `agent-browser eval`, вызвав тот же путь
рендера, что использует реальная загрузка:

```javascript
currentAthlete = { surname: 'Иванов', name: 'Иван', birthday: '1990-05-01', sex: 'мужчина', category: 'мужчины 35-39 (1990)' };
currentResults = [
  { event_name: 'Весна', event_year: 2026, event_distance: '10 км', event_date: '2026-05-15',
    race_status: 'Finished', time_clear_finish: '2538000', finish_pace_avg_clean: '4:13',
    rank_absolute: 12, event_id: 71, start_number: '145' },
  { event_name: 'Жара', event_year: 2026, event_distance: '21.1 км', event_date: '2026-08-24',
    race_status: 'Finished', time_clear_finish: '6120000', finish_pace_avg_clean: '4:50',
    rank_absolute: 34, event_id: 104, start_number: '882' }
];
filteredResults = [...currentResults];
document.getElementById('loadingContainer').style.display = 'none';
document.getElementById('profileContainer').style.display = 'block';
renderProfile();
```

Проверить на скриншоте (десктоп `1280x800` и мобильная ширина `390x700`,
через `agent-browser set viewport <w> <h>`):
- Шапка профиля — белая карточка с акцентной розовой полосой слева, БЕЗ
  сплошной розовой заливки/градиента
- Карточки забегов в сетке — тонкая рамка, при наведении курсора нет
  подъёма (`translateY`), только лёгкое усиление тени
- Фильтры (Название забега/Дистанция/Год) — обычный ряд `.km-select` без
  цветной панели-подложки
- Переключатель Сетка/Таблица — розовые pill-кнопки (не кнопки с толстой
  обводкой), клик по «Таблица» переключает и подсвечивает активную
  пилюлю
- Расширенная статистика — плоские карточки с тонкой рамкой, без серого
  градиентного контейнера вокруг
- Таблица истории (переключить на «Таблица») — сплошная розовая заливка
  заголовка, без диагонального градиента
- Мобильная ширина — ничего не переполняет экран горизонтально,
  фильтры/карточки читаемы

Если найдены визуальные баги — исправить и повторить проверку.

- [ ] **Step 5: Закрыть браузер и остановить dev-сервер**

```bash
agent-browser close
```
Остановить процесс uvicorn (найти PID по занятому порту 8000, завершить).

- [ ] **Step 6: Финальный коммит (если были правки по итогам визуальной проверки)**

Если Step 4 потребовал исправлений — закоммитить их отдельным коммитом с
понятным сообщением (`fix(krasmarafon): athlete-profile.html — <что
именно поправлено по итогам визуальной проверки>`). Если правок не
было — этот шаг пропускается, Task 4 уже финальный коммит.

---

## Self-Review (для исполнителя плана)

- **Покрытие спеки:** п.1 (шапка, вариант C) — Task 4 правка 1-2; п.2
  (карточка забега, вариант B) — Task 4 правка 3; п.3 (фильтры →
  km-toolbar) — Task 3 правка 1 + Task 4 правка 7-8; п.4 (переключатель
  вида → km-pill) — Task 1+2+3 правка 2 + Task 4 правка 9; п.5
  (расширенная статистика) — Task 4 правка 4; п.6 (таблица) — Task 4
  правка 5; п.7 (`.stat-card`/`.chart-card` смягчение) — Task 4 правка 6
  (`.chart-card:hover` у же не содержит `transform`, правки не требует —
  проверено при чтении исходного CSS); п.8 (дублирующийся `</script>`) —
  Task 2 правка 3; п.9 (флаг не трогаем) — ни один task не касается
  `config/history_enabled.local`/`get_history_enabled()`/`set_history_enabled()`.
- **Сигнатуры функций согласованы:** `getViewMode()`,
  `_setViewModeActivePill(value)`, `setViewMode(value)` — одинаковые имена
  в Task 1 (тест), Task 2 (реализация), Task 3 (HTML `onclick`).
- **Плейсхолдеров нет** — каждый шаг содержит точный код/точные CSS-блоки
  для find/replace.
