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
