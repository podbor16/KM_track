// Тест для static/js/analytics-results.js: колонки времени в таблице
// результатов показывают статус ("Не стартовал"/DNF/DSQ) вместо пустого
// "—", когда участник не финишировал (запрос пользователя 2026-08-22).
// Заодно покрывает convertRaceStatus() — DNF/DSQ раньше не матчились ни
// одним правилом и молча попадали в дефолт 'notstarted'.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_no_time_status.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeRowStub() {
    return {
        className: '',
        _innerHTML: '',
        dataset: {},
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
function makeSimpleElement() {
    return { value: '', dataset: {}, style: {} };
}

const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) {
        elementsById[id] = id === 'resultsTableBody' ? makeTbodyStub() : makeSimpleElement();
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

check('convertRaceStatus("DNF") — теперь "dnf", не проваливается в дефолт "notstarted"', () => {
    assert.strictEqual(sandbox.convertRaceStatus('DNF'), 'dnf');
});
check('convertRaceStatus("DSQ") — теперь "dsq", не проваливается в дефолт "notstarted"', () => {
    assert.strictEqual(sandbox.convertRaceStatus('DSQ'), 'dsq');
});
check('convertRaceStatus("Not started") — по-прежнему "notstarted"', () => {
    assert.strictEqual(sandbox.convertRaceStatus('Not started'), 'notstarted');
});
check('convertRaceStatus("Finished") — по-прежнему "finished"', () => {
    assert.strictEqual(sandbox.convertRaceStatus('Finished'), 'finished');
});

const RUNNERS = [
    { status: 'notstarted', surname: 'Иванов', name: 'Пётр', start_number: '1', rank_absolute: null,
      time_gun_finish: null, time_clear_finish: null },
    { status: 'dnf', surname: 'Петров', name: 'Олег', start_number: '2', rank_absolute: null,
      time_gun_finish: null, time_clear_finish: null },
    { status: 'dsq', surname: 'Сидоров', name: 'Илья', start_number: '3', rank_absolute: null,
      time_gun_finish: null, time_clear_finish: null },
    { status: 'finished', surname: 'Кузнецов', name: 'Артём', start_number: '4', rank_absolute: 1,
      time_gun_finish: '3:22', time_clear_finish: '3:22' },
];

check('renderResultsTable() — "Не стартовал" вместо времени для notstarted', () => {
    domStub('ageGroupFilter').value = '';
    sandbox.renderResultsTable(RUNNERS);
    const rows = domStub('resultsTableBody')._rows;
    assert.ok(rows[0].innerHTML.includes('Не стартовал'), rows[0].innerHTML);
    assert.ok(!rows[0].innerHTML.includes('—</span>') || rows[0].innerHTML.includes('Не стартовал'));
});

check('renderResultsTable() — "DNF" вместо времени для dnf', () => {
    sandbox.renderResultsTable(RUNNERS);
    const rows = domStub('resultsTableBody')._rows;
    assert.ok(rows[1].innerHTML.includes('DNF'), rows[1].innerHTML);
});

check('renderResultsTable() — "DSQ" вместо времени для dsq', () => {
    sandbox.renderResultsTable(RUNNERS);
    const rows = domStub('resultsTableBody')._rows;
    assert.ok(rows[2].innerHTML.includes('DSQ'), rows[2].innerHTML);
});

check('renderResultsTable() — финишировавший участник по-прежнему показывает реальное время, не статус', () => {
    sandbox.renderResultsTable(RUNNERS);
    const rows = domStub('resultsTableBody')._rows;
    assert.ok(rows[3].innerHTML.includes('3:22'), rows[3].innerHTML);
    assert.ok(!rows[3].innerHTML.includes('km-time-status'), rows[3].innerHTML);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
