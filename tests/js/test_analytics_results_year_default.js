// Тесты для static/js/analytics-results.js:
// latestConfiguredYearForEvent() + switchEventResults(trigger) — год
// автоматически переключается на последний год, для которого у события
// есть настроенный event_id (eventYearToIdMap, прокси "есть данные в БД"),
// но ТОЛЬКО при смене события (trigger==='event'), не при ручном выборе
// года (trigger==='year').
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_year_default.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeElement(tag) {
    return {
        tagName: (tag || 'DIV').toUpperCase(), style: {}, value: '', textContent: '', dataset: {},
        appendChild() {}, addEventListener() {}, querySelectorAll() { return []; }, setAttribute() {},
    };
}
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement('DIV');
    return elementsById[id];
}
function resetDom() {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
}

class FakeImage {
    set src(_url) { if (this.onerror) this.onerror(); }
    get src() { return this._url; }
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ results: [] }) }),
    document: {
        getElementById: domStub,
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
        querySelectorAll: () => [],
        querySelector: () => null,
        documentElement: { style: { setProperty: () => {} } },
    },
    Image: FakeImage,
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
async function checkAsync(name, fn) {
    try { await fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('latestConfiguredYearForEvent() — возвращает максимальный год из eventYearToIdMap для события', () => {
    // zhara_2025 и zhara_2026 оба заданы в eventYearToIdMap
    assert.strictEqual(sandbox.latestConfiguredYearForEvent('zhara'), 2026);
});

check('latestConfiguredYearForEvent() — событие без записей в eventYearToIdMap возвращает null', () => {
    assert.strictEqual(sandbox.latestConfiguredYearForEvent('несуществующее_событие'), null);
});

(async () => {
    await checkAsync('switchEventResults("event") — переключает год на последний сконфигурированный для нового события', async () => {
        resetDom();
        domStub('eventResultsSelector').value = 'kids'; // kids_2025 и kids_2026 в eventYearToIdMap
        domStub('yearResultsSelector').value = '2024';
        await sandbox.switchEventResults('event');
        assert.strictEqual(domStub('yearResultsSelector').value, 2026);
    });

    await checkAsync('switchEventResults("year") — год берётся из селектора как есть, без автопереключения', async () => {
        resetDom();
        domStub('eventResultsSelector').value = 'kids';
        domStub('yearResultsSelector').value = '2024';
        await sandbox.switchEventResults('year');
        assert.strictEqual(domStub('yearResultsSelector').value, '2024');
    });

    console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
    process.exit(failures === 0 ? 0 : 1);
})();
