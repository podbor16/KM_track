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

check('computeRanksAtPositions: лидер по elapsedS получает ранг 1 на общей позиции', () => {
    const participants = [
        { bib: 1, points: [{ pos: 1, elapsedS: 100 }, { pos: 2, elapsedS: 210 }] },
        { bib: 2, points: [{ pos: 1, elapsedS: 90 }, { pos: 2, elapsedS: 200 }] },
    ];
    const ranks = sandbox.computeRanksAtPositions(participants);
    // JSON.stringify — не deepStrictEqual: массив создан внутри vm-песочницы,
    // у него другой Array-конструктор (другой "realm"), чем у host-процесса,
    // deepStrictEqual считает их разными объектами при идентичном содержимом.
    assert.strictEqual(JSON.stringify(ranks.get(1)), JSON.stringify([{ x: 1, y: 2 }, { x: 2, y: 2 }]));
    assert.strictEqual(JSON.stringify(ranks.get(2)), JSON.stringify([{ x: 1, y: 1 }, { x: 2, y: 1 }]));
});
check('computeRanksAtPositions: свои точки участника ранжируются по последней известной точке соперника НЕ ПОЗЖЕ этой позиции', () => {
    // Участник 2 ещё не дошёл до pos=2 (у него только pos=1) — на позиции 2
    // участника 1 берётся последнее известное значение участника 2 (100 на pos=1).
    const participants = [
        { bib: 1, points: [{ pos: 1, elapsedS: 150 }, { pos: 2, elapsedS: 260 }] },
        { bib: 2, points: [{ pos: 1, elapsedS: 100 }] },
    ];
    const ranks = sandbox.computeRanksAtPositions(participants);
    // На pos=2 участника 1 сравнение идёт с elapsedS=100 участника 2 (его
    // последняя известная точка) -> участник 1 (260) позади -> ранг 2.
    // JSON.stringify — не deepStrictEqual: см. комментарий выше.
    assert.strictEqual(JSON.stringify(ranks.get(1)), JSON.stringify([{ x: 1, y: 2 }, { x: 2, y: 2 }]));
});
check('computeRanksAtPositions: точка участника без ни одного валидного соперника получает ранг 1 (только он сам)', () => {
    const participants = [
        { bib: 1, points: [{ pos: 5, elapsedS: 500 }] },
    ];
    const ranks = sandbox.computeRanksAtPositions(participants);
    // JSON.stringify — не deepStrictEqual: см. комментарий выше.
    assert.strictEqual(JSON.stringify(ranks.get(1)), JSON.stringify([{ x: 5, y: 1 }]));
});

function mkRow(bib, checkpoints) {
    return { start_number: bib, surname: `Уч${bib}`, name: 'Тест', checkpoints };
}

check('buildPositionDatasetsSingleStage: точки берутся из checkpoints[stage], x=km, y=ранг', () => {
    const rows = [
        mkRow(1, { run1: [{ lap: 0, km: 0, elapsed_s: 0 }, { lap: 1, km: 1.25, elapsed_s: 300 }] }),
        mkRow(2, { run1: [{ lap: 0, km: 0, elapsed_s: 0 }, { lap: 1, km: 1.25, elapsed_s: 280 }] }),
    ];
    const datasets = sandbox.buildPositionDatasetsSingleStage('run1', rows);
    const ds1 = datasets.find(d => d._bib === 1);
    const ds2 = datasets.find(d => d._bib === 2);
    assert.strictEqual(JSON.stringify(ds1.data), JSON.stringify([{ x: 0, y: 1 }, { x: 1.25, y: 2 }]));
    assert.strictEqual(JSON.stringify(ds2.data), JSON.stringify([{ x: 0, y: 2 }, { x: 1.25, y: 1 }]));
});
check('buildPositionDatasetsSingleStage: участник без отметок этого этапа не попадает в датасеты', () => {
    const rows = [mkRow(1, { run1: [] }), mkRow(2, { run1: [{ lap: 0, km: 0, elapsed_s: 0 }] })];
    const datasets = sandbox.buildPositionDatasetsSingleStage('run1', rows);
    assert.strictEqual(datasets.length, 1);
    assert.strictEqual(datasets[0]._bib, 2);
});
check('buildPositionDatasetsWholeRace: км второго/третьего этапа считается от глобального накопления, x — виртуальный', () => {
    const rows = [
        mkRow(1, {
            run1: [{ lap: 0, km: 0, elapsed_s: 0 }, { lap: 8, km: 9.98, elapsed_s: 3000 }],
            bike: [{ lap: 0, km: 0, elapsed_s: 3100 }, { lap: 1, km: 3.4, elapsed_s: 3700 }],
            run2: [],
        }),
    ];
    const datasets = sandbox.buildPositionDatasetsWholeRace(rows);
    const ds = datasets[0];
    // run1: x = kmToVirtualX('run1', km); bike: x = kmToVirtualX('bike', km)
    assert.strictEqual(ds.data[0].x, sandbox.kmToVirtualX('run1', 0));
    assert.strictEqual(ds.data[1].x, sandbox.kmToVirtualX('run1', 9.98));
    assert.strictEqual(ds.data[2].x, sandbox.kmToVirtualX('bike', 0));
    assert.strictEqual(ds.data[3].x, sandbox.kmToVirtualX('bike', 3.4));
    assert.strictEqual(ds.data.length, 4); // run2 пуст — 0 точек оттуда
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
