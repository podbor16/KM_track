// Тест для static/js/analytics-results.js: пока участник ещё бежит,
// колонки времени показывают дистанцию последней пройденной отметки
// ("10.55 км") вместо пустого "-" (запрос пользователя 2026-08-23).
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_last_checkpoint_label.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeRowStub() {
    return { className: '', _innerHTML: '', dataset: {}, set innerHTML(v) { this._innerHTML = v; }, get innerHTML() { return this._innerHTML; }, addEventListener() {} };
}
function makeTbodyStub() {
    const rows = [];
    return { _rows: rows, set innerHTML(v) { if (v === '') rows.length = 0; }, get innerHTML() { return ''; }, appendChild(row) { rows.push(row); return row; } };
}
function makeSimpleElement() {
    return { value: '', dataset: {}, style: {} };
}
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = id === 'resultsTableBody' ? makeTbodyStub() : makeSimpleElement();
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

// Конфиг активного события — та же форма, что возвращает /api/current-event
// (DistanceInfo: distance/checkpoints[].distance_km).
const DISTANCES_CFG = [
    {
        distance: '21.1 км',
        checkpoints: [
            { name: 'Старт', distance_km: 0 },
            { name: 'КТ1', distance_km: 5.0 },
            { name: 'КТ2', distance_km: 6.0 },
            { name: 'КТ3', distance_km: 10.55 },
            { name: 'КТ4', distance_km: 14.65 },
            { name: 'КТ5', distance_km: 15.65 },
            { name: 'КТ6', distance_km: 20.2 },
            { name: 'Финиш', distance_km: 21.1 },
        ],
    },
];
vm.runInContext('_liveEventDistances = ' + JSON.stringify(DISTANCES_CFG) + ';', sandbox);

check('_lastCheckpointLabel() — берёт дистанцию ПОСЛЕДНЕЙ пройденной отметки (не первой)', () => {
    const runner = {
        distance: '21.1 км', event: '21.1 км',
        checkpoints: {
            kt1: { time: '0:28:00' }, kt2: { time: '0:34:00' }, kt3: { time: '1:02:00' },
            kt4: null, kt5: null, kt6: null, kt7: null,
        },
    };
    assert.strictEqual(sandbox._lastCheckpointLabel(runner), '10.55 км');
});

check('_lastCheckpointLabel() — пропускает КТ без времени (kt4 пуст, но kt3 есть)', () => {
    const runner = {
        distance: '21.1 км', event: '21.1 км',
        checkpoints: { kt1: { time: '0:28:00' }, kt2: null, kt3: null, kt4: null, kt5: null, kt6: null, kt7: null },
    };
    assert.strictEqual(sandbox._lastCheckpointLabel(runner), '5 км');
});

check('_lastCheckpointLabel() — null, если ни одной отметки ещё нет', () => {
    const runner = { distance: '21.1 км', event: '21.1 км', checkpoints: {} };
    assert.strictEqual(sandbox._lastCheckpointLabel(runner), null);
});

check('renderResultsTable() — бегущий с отметкой показывает "10.55 км" вместо "-" в обеих колонках времени', () => {
    domStub('ageGroupFilter').value = '';
    const runner = {
        status: 'running', surname: 'Бегущий', name: 'Иван', start_number: '10',
        distance: '21.1 км', event: '21.1 км', rank_absolute: null,
        time_gun_finish: null, time_clear_finish: null,
        checkpoints: { kt1: { time: '0:28:00' }, kt2: { time: '0:34:00' }, kt3: { time: '1:02:00' } },
    };
    sandbox.renderResultsTable([runner]);
    const html = domStub('resultsTableBody')._rows[0].innerHTML;
    assert.ok(html.includes('10.55 км'), html);
    assert.ok(!html.includes('>-<'), html);
});

check('renderResultsTable() — бегущий БЕЗ отметок по-прежнему показывает "-", не ломается', () => {
    const runner = {
        status: 'running', surname: 'НачалБежать', name: 'Пётр', start_number: '11',
        distance: '21.1 км', event: '21.1 км', rank_absolute: null,
        time_gun_finish: null, time_clear_finish: null, checkpoints: {},
    };
    sandbox.renderResultsTable([runner]);
    const html = domStub('resultsTableBody')._rows[0].innerHTML;
    assert.ok(html.includes('>-<'), html);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
