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
    URLSearchParams,
    location: { pathname: '/results', search: '', hash: '' },
    history: { replaceState: (_s, _t, url) => { sandbox.location.search = (url.split('?')[1] ? '?' + url.split('?')[1] : ''); } },
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

check('populateGenderFilter() — рендерит "Все" + пилюли по факту встречающихся полов (текст во множественном числе), женщины раньше мужчин', () => {
    resetDom();
    sandbox.populateGenderFilter(RUNNERS_MIXED);
    const container = domStub('genderFilter');
    const labels = container._children.map(c => c.textContent);
    assert.deepStrictEqual(labels, ['Все', 'Женщины', 'Мужчины']);
    assert.strictEqual(container.dataset.value, '');
    assert.strictEqual(container._children[0].className, 'km-pill active');
});

check('populateGenderFilter() — не показывает пол, которого нет в данных', () => {
    resetDom();
    sandbox.populateGenderFilter(RUNNERS_FEMALE_ONLY);
    const labels = domStub('genderFilter')._children.map(c => c.textContent);
    assert.deepStrictEqual(labels, ['Все', 'Женщины']);
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
