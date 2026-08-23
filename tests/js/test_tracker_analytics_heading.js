// Тест для static/js/tracker-api.js: заголовок секции аналитики. По
// запросу пользователя (2026-08-22) розовая строка (h2) теперь несёт
// событие+год+дистанцию, чёрная строка (h3 внутри блока статистики) —
// только "Общая статистика" (раньше было наоборот, отчасти дублировалось).
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_tracker_analytics_heading.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/tracker-api.js'), 'utf-8');

function makeElement() {
    return { textContent: '', innerHTML: '' };
}
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement();
    return elementsById[id];
}
const h2Stub = makeElement();

const sandbox = {
    console,
    document: {
        getElementById: domStub,
        querySelector: (sel) => sel === '#analyticsPanel h2' ? h2Stub : null,
    },
    localStorage: { getItem: () => null, setItem: () => {} },
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

check('updateAnalyticsHeading() — событие+год+дистанция в h2 (розовая строка)', () => {
    vm.runInContext(`CONFIG.EVENT_DB_NAME = 'Жара'; CONFIG.EVENT_YEAR = 2026; CONFIG.CURRENT_DISTANCE = '5 км';`, sandbox);
    sandbox.updateAnalyticsHeading();
    assert.strictEqual(h2Stub.textContent, 'Жара 2026 | 5 км');
});

check('updateAnalyticsHeading() — без дистанции не добавляет " | "', () => {
    vm.runInContext(`CONFIG.EVENT_DB_NAME = 'Жара'; CONFIG.EVENT_YEAR = 2026; CONFIG.CURRENT_DISTANCE = '';`, sandbox);
    sandbox.updateAnalyticsHeading();
    assert.strictEqual(h2Stub.textContent, 'Жара 2026');
});

check('renderAnalyticsHTML() — h3 содержит только "Общая статистика", без события/года/дистанции', () => {
    const stats = { total: 10, finished: 5, not_started: 5, running: 0, dnf: 0, dsq: 0, male: 5, female: 5 };
    const html = sandbox.renderAnalyticsHTML(stats, [{ distance: '5.0' }]);
    assert.ok(html.includes('<h3>Общая статистика</h3>'), 'h3 должен быть ровно "Общая статистика"');
    assert.ok(!html.includes('Жара'), 'h3 не должен дублировать название события');
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
