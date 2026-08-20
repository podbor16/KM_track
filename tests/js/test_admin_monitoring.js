// Тесты для static/js/admin-monitoring.js — вкладка «Мониторинг» в /admin.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_admin_monitoring.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/admin-monitoring.js'), 'utf-8');

function makeElement(tag) {
    const children = [];
    const classes = new Set();
    const el = {
        tagName: (tag || 'DIV').toUpperCase(),
        value: '', textContent: '', innerHTML: '',
        style: {},
        dataset: {},
        parentElement: null,
        _children: children,
        appendChild(child) { children.push(child); child.parentElement = el; return child; },
        get className() { return Array.from(classes).join(' '); },
        set className(v) { classes.clear(); String(v).split(/\s+/).filter(Boolean).forEach(c => classes.add(c)); },
        classList: {
            add: (c) => classes.add(c),
            remove: (c) => classes.delete(c),
            contains: (c) => classes.has(c),
        },
    };
    return el;
}

const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement('DIV');
    return elementsById[id];
}
function resetDom() {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
}

class FakeEventSource {
    constructor(url) { this.url = url; this.onmessage = null; }
    close() {}
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    document: { getElementById: domStub, createElement: (tag) => makeElement(tag) },
    EventSource: FakeEventSource,
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

check('loadLabelBadgeClass() — маппит русские метки на CSS-классы', () => {
    assert.strictEqual(sandbox.loadLabelBadgeClass('Низкая'), 'admin-badge--load-low');
    assert.strictEqual(sandbox.loadLabelBadgeClass('Умеренная'), 'admin-badge--load-medium');
    assert.strictEqual(sandbox.loadLabelBadgeClass('Высокая'), 'admin-badge--load-high');
    assert.strictEqual(sandbox.loadLabelBadgeClass('Критическая'), 'admin-badge--load-critical');
});

check('loadLabelBadgeClass() — неизвестная метка не падает, возвращает дефолт', () => {
    assert.strictEqual(sandbox.loadLabelBadgeClass('бред'), 'admin-badge--inactive');
    assert.strictEqual(sandbox.loadLabelBadgeClass(undefined), 'admin-badge--inactive');
});

check('formatRamLabel() — форматирует used/total MB с процентом', () => {
    assert.strictEqual(sandbox.formatRamLabel(1755, 2972), '1755 / 2972 MB (59%)');
});

check('formatRamLabel() — total=0 не делит на ноль', () => {
    assert.strictEqual(sandbox.formatRamLabel(0, 0), '—');
});

check('formatUptime() — дни+часы при аптайме больше суток', () => {
    assert.strictEqual(sandbox.formatUptime(90000), '1 д 1 ч'); // 25ч = 1д1ч
});

check('formatUptime() — только часы, если меньше суток', () => {
    assert.strictEqual(sandbox.formatUptime(7200), '2 ч');
});

check('renderLiveTiles() — заполняет все плитки из точки метрик', () => {
    resetDom();
    const point = {
        cpu_percent: 42.5, ram_used_mb: 1755, ram_total_mb: 2972,
        avg_response_ms: 320, total_requests: 500, http_errors: 3,
        sse_connections: 12, unique_ips: 80,
        load_score: 55.2, load_label: 'Умеренная',
    };
    sandbox.renderLiveTiles(point);
    assert.strictEqual(domStub('mon-tile-cpu').textContent, '42.5%');
    assert.strictEqual(domStub('mon-tile-ram').textContent, '1755 / 2972 MB (59%)');
    assert.strictEqual(domStub('mon-tile-response').textContent, '320 мс');
    assert.strictEqual(domStub('mon-tile-requests').textContent, '500 (ошибок: 3)');
    assert.strictEqual(domStub('mon-tile-sse').textContent, '12');
    assert.strictEqual(domStub('mon-tile-ips').textContent, '80');
    assert.strictEqual(domStub('mon-tile-load-score').textContent, '55.2 / 100');
    assert.strictEqual(domStub('mon-tile-load-badge').textContent, 'Умеренная');
    assert.ok(domStub('mon-tile-load-badge').classList.contains('admin-badge--load-medium'));
});

check('monSubscribeLive() — создаёт EventSource на правильный URL, повторный вызов не пересоздаёт', () => {
    resetDom();
    vm.runInContext('monSSE = null;', sandbox); // сброс между тестами — модуль хранит состояние в замыкании sandbox
    sandbox.monSubscribeLive();
    const first = vm.runInContext('monSSE', sandbox);
    assert.strictEqual(first.url, '/api/admin/metrics/live');
    sandbox.monSubscribeLive();
    const second = vm.runInContext('monSSE', sandbox);
    assert.strictEqual(first, second, 'повторный вызов не должен создавать новый EventSource');
});

check('monOnLivePoint() — рендерит плитки при каждой точке', () => {
    resetDom();
    vm.runInContext('monLastLoadLabel = null;', sandbox);
    const point = {
        cpu_percent: 10, ram_used_mb: 100, ram_total_mb: 2000,
        avg_response_ms: 50, total_requests: 10, http_errors: 0,
        sse_connections: 1, unique_ips: 1, load_score: 5, load_label: 'Низкая',
    };
    sandbox.monOnLivePoint(point);
    assert.strictEqual(domStub('mon-tile-cpu').textContent, '10%');
});

check('monOnLivePoint() — переход в "Критическая" вызывает monLoadAlerts() один раз', () => {
    resetDom();
    vm.runInContext('monLastLoadLabel = null;', sandbox);
    let calls = 0;
    sandbox.monLoadAlerts = () => { calls++; };
    sandbox.monOnLivePoint({ load_label: 'Критическая' });
    assert.strictEqual(calls, 1);
    // Повторная точка с той же меткой — НЕ должна вызывать снова (дедуп по "раньше не была")
    sandbox.monOnLivePoint({ load_label: 'Критическая' });
    assert.strictEqual(calls, 1, 'повторная точка с той же высокой меткой не должна повторно дёргать monLoadAlerts()');
});

check('monOnLivePoint() — переход из "Критическая" обратно в "Низкая" и снова в "Критическая" вызывает monLoadAlerts() дважды', () => {
    resetDom();
    vm.runInContext('monLastLoadLabel = null;', sandbox);
    let calls = 0;
    sandbox.monLoadAlerts = () => { calls++; };
    sandbox.monOnLivePoint({ load_label: 'Критическая' });
    sandbox.monOnLivePoint({ load_label: 'Низкая' });
    sandbox.monOnLivePoint({ load_label: 'Критическая' });
    assert.strictEqual(calls, 2);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
