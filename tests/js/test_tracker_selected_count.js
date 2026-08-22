// Тест для static/js/tracker-search.js: updateSelectedList() — счётчик
// "Отслеживаемые участники (N/5)" в шапке панели не обновлялся вообще
// (обновлялась только кнопка "Очистить (N/5)" рядом) — реальный баг,
// найден пользователем по скриншоту 2026-08-22: список показывал 1
// отслеживаемого участника, а счётчик в шапке оставался на "0". Заодно
// кнопка переименована в "Очистить всех" (без дублирующего счётчика).
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_tracker_selected_count.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/tracker-search.js'), 'utf-8');

function makeElement() {
    return { textContent: '', innerHTML: '' };
}

const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement();
    return elementsById[id];
}
function resetDom() {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
}

const RUNNERS = [
    { id: 4291, start_number: 4291, full_name: 'Подборский Иван', category: 'М14-15' },
    { id: 4292, start_number: 4292, full_name: 'Иванов Пётр', category: 'М18-24' },
];

const sandbox = {
    console,
    document: { getElementById: domStub },
    CONFIG: { MAX_SELECTED: 5 },
    allRunners: RUNNERS,
    activeRunnerId: null,
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(scriptJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('updateSelectedList() — обновляет #selectedCount при одном выбранном участнике', () => {
    resetDom();
    vm.runInContext(`selectedRunnerIds = new Set(['4291']);`, sandbox);
    sandbox.updateSelectedList();
    assert.strictEqual(domStub('selectedCount').textContent, 1);
});

check('updateSelectedList() — обновляет #selectedCount при нескольких выбранных', () => {
    resetDom();
    vm.runInContext(`selectedRunnerIds = new Set(['4291', '4292']);`, sandbox);
    sandbox.updateSelectedList();
    assert.strictEqual(domStub('selectedCount').textContent, 2);
});

check('updateSelectedList() — обновляет #selectedCount до 0 при пустом выборе', () => {
    resetDom();
    vm.runInContext(`selectedRunnerIds = new Set();`, sandbox);
    sandbox.updateSelectedList();
    assert.strictEqual(domStub('selectedCount').textContent, 0);
});

check('updateSelectedList() — кнопка "Очистить всех" без дублирующего счётчика', () => {
    resetDom();
    vm.runInContext(`selectedRunnerIds = new Set(['4291']);`, sandbox);
    sandbox.updateSelectedList();
    const html = domStub('selectedList').innerHTML;
    assert.ok(html.includes('Очистить всех'), 'кнопка должна содержать текст "Очистить всех"');
    assert.ok(!/Очистить \(\d/.test(html), 'кнопка не должна дублировать счётчик в своём тексте');
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
