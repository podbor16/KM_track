// Тесты для static/js/analytics-results.js: селектор года на /results —
// только годы, в которых у события есть результаты (/api/results-years);
// при смене события (trigger==='event') год переключается на последний
// такой, при ручном выборе года (trigger==='year') — не перебивается.
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
    const children = [];
    return {
        tagName: (tag || 'DIV').toUpperCase(), style: {}, value: '', textContent: '', dataset: {},
        _children: children,
        get options() { return children.filter(c => c.tagName === 'OPTION'); },
        appendChild(child) { children.push(child); return child; },
        addEventListener() {}, querySelectorAll() { return []; }, setAttribute() {},
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
    fetch: (url) => {
        const body = String(url).includes('/api/results-years')
            ? (String(url).includes(encodeURIComponent('Детский забег'))
                ? { years: [{ year: 2026, event_ids: [113] }] }
                : { years: [{ year: 2026, event_ids: [115, 116] }, { year: 2024, event_ids: [134] }] })
            : { results: [] };
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    },
    document: {
        getElementById: domStub,
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
        querySelectorAll: () => [],
        querySelector: () => null,
        documentElement: { style: { setProperty: () => {} } },
    },
    Image: FakeImage,
    URLSearchParams,
    location: { pathname: '/results', search: '', hash: '' },
    history: { replaceState: (_s, _t, url) => { sandbox.location.search = (url.split('?')[1] ? '?' + url.split('?')[1] : ''); } },
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

(async () => {
    await checkAsync('fetchResultsYears() + eventIdsFor() — годы и event_id из API', async () => {
        const years = await sandbox.fetchResultsYears('zhara');
        assert.deepStrictEqual(years.map(y => y.year), [2026, 2024]);
        assert.deepStrictEqual(Array.from(sandbox.eventIdsFor('zhara', 2026)), [115, 116]);
        assert.deepStrictEqual(Array.from(sandbox.eventIdsFor('zhara', 2025)), []);   // года без результатов нет
        assert.strictEqual(sandbox.latestResultsYearForEvent('zhara'), 2026);
        assert.strictEqual(sandbox.latestResultsYearForEvent('несуществующее_событие'), null);
    });

    await checkAsync('switchEventResults("event") — в селекторе только годы с результатами, выбран последний', async () => {
        resetDom();
        domStub('eventResultsSelector').value = 'kids';
        domStub('yearResultsSelector').value = '2024';
        await sandbox.switchEventResults('event');
        assert.strictEqual(domStub('yearResultsSelector').value, 2026);
        assert.deepStrictEqual(domStub('yearResultsSelector').options.map(o => o.value), [2026]);
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
