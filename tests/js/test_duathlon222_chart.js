// Тесты чистых функций static/js/duathlon222-chart.js — те же паттерны
// node:vm/domStub/check(), что и tests/js/test_siberman_results_merge.js
// (см. первые ~90 строк того файла, если нужен более подробный образец).
// Запуск: node tests/js/test_duathlon222_chart.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const html = fs.readFileSync(path.join(ROOT, 'templates/race_triatleta/duathlon_results.html'), 'utf-8');
let inlineScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1])[0];
// Очищаем Jinja2-переменную для тестового контекста (регэксп выше матчит
// только инлайн-скрипт без атрибутов — {{ v }} встречается лишь внутри
// <script src="...?v={{ v }}">, туда этот regex не заходит).
inlineScript = inlineScript.replace(/{{ year\|tojson }}/g, '2026');
const chartJs = fs.readFileSync(path.join(ROOT, 'static/js/duathlon222-chart.js'), 'utf-8');

const elementsById = {};
function domStub(id) {
    if (id && elementsById[id]) return elementsById[id];
    const el = {
        innerHTML: '', style: {}, textContent: '', value: '',
        classList: { toggle() {}, add() {}, remove() {} },
        dataset: {}, addEventListener: () => {}, getContext: () => ({}),
    };
    if (id) elementsById[id] = el;
    return el;
}
class ChartStub {
    constructor(ctx, config) {
        this.config = config; this.options = config.options || {}; this.data = config.data || {};
        this.scales = {
            x: { getValueForPixel: px => px, getPixelForValue: v => v },
            y: { getValueForPixel: px => px, getPixelForValue: v => v },
        };
    }
    destroy() {}
    update() {}
    getDatasetMeta(i) {
        const ds = this.data.datasets?.[i];
        return { data: (ds?.data || []).map(p => ({ x: p.x, y: p.y })) };
    }
}
const sandbox = {
    console,
    document: {
        getElementById: (id) => domStub(id),
        querySelectorAll: () => [],
        querySelector: () => domStub(),
    },
    Chart: ChartStub,
    setInterval: () => 0,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    window: {},
    matchMedia: () => ({ matches: false }),
    getComputedStyle: () => ({ getPropertyValue: () => '#DE0000' }),
    URLSearchParams,
    location: { pathname: '/', search: '', hash: '' },
    history: { replaceState: () => {} },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(inlineScript, sandbox);
vm.runInContext(chartJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('kmToVirtualX: run1 km=0 -> начало сегмента (0)', () => {
    assert.strictEqual(sandbox.kmToVirtualX('run1', 0), 0);
});
check('kmToVirtualX: run1 km=10 (весь этап) -> конец сегмента (25)', () => {
    assert.strictEqual(sandbox.kmToVirtualX('run1', 10), 25);
});
check('kmToVirtualX: bike km=85 (половина 170) -> середина сегмента bike (50)', () => {
    assert.strictEqual(sandbox.kmToVirtualX('bike', 85), 50);
});
check('kmToVirtualX: run2 km=42 (весь этап) -> конец сегмента (100)', () => {
    assert.strictEqual(sandbox.kmToVirtualX('run2', 42), 100);
});
check('kmToVirtualX: км за пределами этапа (баг данных) не вылезает за границу сегмента', () => {
    assert.strictEqual(sandbox.kmToVirtualX('run1', 999), 25);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
