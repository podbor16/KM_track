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

// ---- Chart.js стаб ----
class FakeChart {
    constructor(canvas, config) { this.canvas = canvas; this.config = config; this._destroyed = false; }
    destroy() { this._destroyed = true; }
}
sandbox.Chart = FakeChart;

check('renderHistoryCharts() — пустой массив точек прячет canvas и показывает "Нет данных", не удаляя canvas из DOM', () => {
    resetDom();
    const box = makeElement('DIV');
    const canvas = makeElement('CANVAS');
    box.appendChild(canvas);
    elementsById['mon-chart-cpu'] = canvas;
    sandbox.renderHistoryCharts([]);
    assert.strictEqual(canvas.style.display, 'none');
    const msg = box._children.find(c => c !== canvas);
    assert.ok(msg && msg.textContent.includes('Нет данных'), 'должен быть добавлен отдельный элемент с текстом, а не заменён canvas');
});

check('renderHistoryCharts() — переход от пустой истории к данным возвращает canvas и рисует график (canvas не был удалён)', () => {
    resetDom();
    const box = makeElement('DIV');
    const canvas = makeElement('CANVAS');
    box.appendChild(canvas);
    elementsById['mon-chart-cpu'] = canvas;
    elementsById['mon-chart-ram'] = makeElement('CANVAS');
    elementsById['mon-chart-response'] = makeElement('CANVAS');
    elementsById['mon-chart-errors'] = makeElement('CANVAS');

    sandbox.renderHistoryCharts([]); // пусто — canvas прячется
    assert.strictEqual(canvas.style.display, 'none');

    sandbox.renderHistoryCharts([
        { ts: 1755000000, cpu_percent: 10, ram_used_mb: 100, ram_total_mb: 200, avg_response_ms: 50, http_errors: 0 },
    ]); // данные появились — canvas должен снова стать видимым и получить график
    assert.notStrictEqual(canvas.style.display, 'none');
    const cpuChart = vm.runInContext('monCharts["mon-chart-cpu"]', sandbox);
    assert.ok(cpuChart, 'график должен быть отрисован — canvas не должен был быть удалён из DOM');
});

vm.runInContext('void 0', sandbox); // no-op — Chart уже доступен глобально в sandbox без повторной загрузки скрипта

check('hoursForRange() — маппит ключ диапазона на часы для API', () => {
    assert.strictEqual(sandbox.hoursForRange('1h'), 1);
    assert.strictEqual(sandbox.hoursForRange('6h'), 6);
    assert.strictEqual(sandbox.hoursForRange('24h'), 24);
    assert.strictEqual(sandbox.hoursForRange('7d'), 168);
    assert.strictEqual(sandbox.hoursForRange('30d'), 720);
    assert.strictEqual(sandbox.hoursForRange('90d'), 2160);
    assert.strictEqual(sandbox.hoursForRange('6m'), 4320);
    assert.strictEqual(sandbox.hoursForRange('1y'), 8760);
});

check('hoursForRange() — неизвестный ключ по умолчанию 24 часа', () => {
    assert.strictEqual(sandbox.hoursForRange('bogus'), 24);
});

check('renderHistoryCharts() — строит 4 графика с данными из точек истории', () => {
    resetDom();
    const points = [
        { ts: 1755000000, cpu_percent: 10, ram_used_mb: 1000, ram_total_mb: 2000, avg_response_ms: 200, http_errors: 1 },
        { ts: 1755003600, cpu_percent: 20, ram_used_mb: 1500, ram_total_mb: 2000, avg_response_ms: 300, http_errors: 2 },
    ];
    sandbox.renderHistoryCharts(points);
    const cpuChart = vm.runInContext('monCharts["mon-chart-cpu"]', sandbox);
    const ramChart = vm.runInContext('monCharts["mon-chart-ram"]', sandbox);
    assert.deepStrictEqual(cpuChart.config.data.datasets[0].data, [10, 20]);
    assert.deepStrictEqual(ramChart.config.data.datasets[0].data, [50, 75]); // RAM% = used/total*100
});

check('renderHistoryCharts() — второй вызов уничтожает предыдущие графики (нет утечки)', () => {
    resetDom();
    sandbox.renderHistoryCharts([{ ts: 1755000000, cpu_percent: 5, ram_used_mb: 100, ram_total_mb: 200, avg_response_ms: 50, http_errors: 0 }]);
    const first = vm.runInContext('monCharts["mon-chart-cpu"]', sandbox);
    sandbox.renderHistoryCharts([{ ts: 1755000000, cpu_percent: 5, ram_used_mb: 100, ram_total_mb: 200, avg_response_ms: 50, http_errors: 0 }]);
    assert.strictEqual(first._destroyed, true);
});

check('renderAlertsTable() — пустой список показывает заглушку', () => {
    resetDom();
    sandbox.renderAlertsTable([]);
    assert.ok(domStub('mon-alerts-body').innerHTML.includes('Алертов нет'));
});

check('renderAlertsTable() — строит строки с бейджем и советами', () => {
    resetDom();
    const alerts = [
        {
            datetime: '2026-08-19 16:49:02', load_label: 'Критическая',
            cpu_pct: '2.4', ram_pct: '80.8', avg_ms: '17991.2',
            suggestions: ['RAM 80% ...', 'Среднее время ответа 17991 мс ...'],
        },
    ];
    sandbox.renderAlertsTable(alerts);
    const html = domStub('mon-alerts-body').innerHTML;
    assert.ok(html.includes('2026-08-19 16:49:02'));
    assert.ok(html.includes('Критическая'));
    assert.ok(html.includes('admin-badge--load-critical'));
    assert.ok(html.includes('RAM 80%'));
    assert.ok(html.includes('Среднее время ответа 17991 мс'));
});

check('renderAlertsTable() — алерт без советов показывает прочерк, не пустой <ul>', () => {
    resetDom();
    sandbox.renderAlertsTable([{ datetime: '2026-08-19 16:49:02', load_label: 'Высокая', cpu_pct: '90', ram_pct: '10', avg_ms: '100', suggestions: [] }]);
    const html = domStub('mon-alerts-body').innerHTML;
    assert.ok(html.includes('—'));
    assert.ok(!html.includes('<ul'));
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
