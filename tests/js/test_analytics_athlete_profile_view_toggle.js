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
