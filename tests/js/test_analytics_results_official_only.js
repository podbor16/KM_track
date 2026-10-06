// Тест для static/js/analytics-results.js: протокол с одной колонкой времени
// (большинство 2024) — чистого времени нет, на странице только официальное
// (решение пользователя 2026-10-06): колонка «Чистое время» скрыта, у Жары
// основное время и места — официальные.
// Запуск: node tests/js/test_analytics_results_official_only.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeRowStub() {
    return {
        className: '', _innerHTML: '', dataset: {},
        set innerHTML(v) { this._innerHTML = v; },
        get innerHTML() { return this._innerHTML; },
        addEventListener() {},
    };
}
function makeTbodyStub() {
    const rows = [];
    return {
        _rows: rows,
        set innerHTML(v) { if (v === '') rows.length = 0; },
        get innerHTML() { return ''; },
        appendChild(row) { rows.push(row); return row; },
    };
}
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) {
        elementsById[id] = id === 'resultsTableBody' ? makeTbodyStub()
            : { value: '', dataset: {}, style: {}, textContent: '', setAttribute() {} };
    }
    return elementsById[id];
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: domStub,
        createElement: () => makeRowStub(),
        addEventListener: () => {},
        querySelectorAll: () => [],
    },
    URLSearchParams,
    location: { pathname: '/results', search: '', hash: '' },
    history: { replaceState: () => {} },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(utilsJs, sandbox);
vm.runInContext(scriptJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

const OFFICIAL_ONLY = [
    { status: 'finished', surname: 'Тарасов', name: 'Павел', start_number: '1003', rank_absolute: 1,
      time_gun_finish: '00:15:11', time_clear_finish: null },
];
const WITH_CLEAN = [
    { status: 'finished', surname: 'Тарасов', name: 'Павел', start_number: '1003', rank_absolute: 1,
      rank_absolute_clean: 1, time_gun_finish: '00:15:11', time_clear_finish: '00:15:09' },
];
function setRunners(runners) {
    sandbox.__runners = runners;
    vm.runInContext('allRunners = __runners;', sandbox);
}

check('нет чистого времени → колонка скрыта, в строке только официальное', () => {
    vm.runInContext("currentEvent = 'zhara';", sandbox);
    setRunners(OFFICIAL_ONLY);
    domStub('ageGroupFilter').value = 'x';
    assert.strictEqual(sandbox.hasCleanTimes(), false);
    assert.strictEqual(sandbox.cleanIsPrimary(), false);
    sandbox.updateTimeColumnHeaders();
    assert.strictEqual(domStub('thTimeCol1').textContent, 'Офиц. время');
    assert.strictEqual(domStub('thTimeCol2').style.display, 'none');
    sandbox.renderResultsTable(OFFICIAL_ONLY);
    const html = domStub('resultsTableBody')._rows[0].innerHTML;
    assert.ok(html.includes('km-time-gun'), 'официальное время в строке');
    assert.ok(!html.includes('km-time-net'), 'ячейки чистого времени нет');
    assert.strictEqual(sandbox.getActiveRankField(), 'rank_category');
});

check('чистое время есть → у Жары оно первое, колонка видна', () => {
    setRunners(WITH_CLEAN);
    assert.strictEqual(sandbox.cleanIsPrimary(), true);
    sandbox.updateTimeColumnHeaders();
    assert.strictEqual(domStub('thTimeCol1').textContent, 'Чистое время');
    assert.strictEqual(domStub('thTimeCol2').style.display, '');
    sandbox.renderResultsTable(WITH_CLEAN);
    assert.ok(domStub('resultsTableBody')._rows[0].innerHTML.includes('km-time-net'));
});

check('живая гонка до первых финишей — чистое время считается имеющимся', () => {
    setRunners([{ status: 'running', surname: 'А', time_gun_finish: null, time_clear_finish: null }]);
    assert.strictEqual(sandbox.hasCleanTimes(), true);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
