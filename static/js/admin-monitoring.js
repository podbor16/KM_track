// static/js/admin-monitoring.js
// Вкладка "Мониторинг" в /admin — живой снимок состояния сервера, графики
// истории и таблица последних алертов. Backend полностью готов и уже
// активно собирает данные в проде — src/monitoring/collector.py
// (MetricsCollector) + src/krasmarafon/routers/api.py (/api/admin/metrics,
// /api/admin/metrics/live, /api/admin/metrics/alerts).
// Дизайн: docs/superpowers/specs/2026-08-20-krasmarafon-admin-monitoring-dashboard-design.md
//
// Живой поток — сырой EventSource, НЕ через SSEClient (static/js/realtime.js):
// SSEClient диспетчеризует сообщения по полю msg.type, а
// /api/admin/metrics/live шлёт голый dict точки метрик без этого поля —
// с SSEClient ни один обработчик никогда бы не сработал. Тот же приём, что
// уже использует tracker-api.js для /api/sse/tracker (тоже нетипизированный
// одноцелевой поток).

// ---- Русские метки нагрузки → CSS-модификатор бейджа ----
const MON_LOAD_BADGE_CLASS = {
    'Низкая': 'admin-badge--load-low',
    'Умеренная': 'admin-badge--load-medium',
    'Высокая': 'admin-badge--load-high',
    'Критическая': 'admin-badge--load-critical',
};
function loadLabelBadgeClass(label) {
    return MON_LOAD_BADGE_CLASS[label] || 'admin-badge--inactive';
}

// ---- Форматирование ----
function formatRamLabel(usedMb, totalMb) {
    if (!totalMb) return '—';
    const pct = Math.round((usedMb / totalMb) * 100);
    return `${usedMb} / ${totalMb} MB (${pct}%)`;
}

function formatUptime(secs) {
    if (!secs) return '—';
    const days = Math.floor(secs / 86400);
    const hours = Math.floor((secs % 86400) / 3600);
    return days > 0 ? `${days} д ${hours} ч` : `${hours} ч`;
}

// ---- Живые плитки ----
function renderLiveTiles(point) {
    domSet('mon-tile-cpu', `${point.cpu_percent ?? 0}%`);
    domSet('mon-tile-ram', formatRamLabel(point.ram_used_mb, point.ram_total_mb));
    domSet('mon-tile-response', `${point.avg_response_ms ?? 0} мс`);
    domSet('mon-tile-requests', `${point.total_requests ?? 0} (ошибок: ${point.http_errors ?? 0})`);
    domSet('mon-tile-sse', `${point.sse_connections ?? 0}`);
    domSet('mon-tile-ips', `${point.unique_ips ?? 0}`);
    domSet('mon-tile-load-score', `${point.load_score ?? 0} / 100`);

    const badgeEl = document.getElementById('mon-tile-load-badge');
    if (badgeEl) {
        badgeEl.textContent = point.load_label || '—';
        badgeEl.className = 'admin-badge ' + loadLabelBadgeClass(point.load_label);
    }
}

function domSet(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ---- Живой SSE-поток ----
let monSSE = null;
let monLastLoadLabel = null;
const MON_HIGH_LOAD_LABELS = ['Высокая', 'Критическая'];

function monOnLivePoint(point) {
    renderLiveTiles(point);
    // Новый алерт (метка стала "Высокая"/"Критическая", раньше не была) —
    // обновляем таблицу последних алертов, не дожидаясь ручного обновления.
    if (MON_HIGH_LOAD_LABELS.includes(point.load_label) && point.load_label !== monLastLoadLabel) {
        monLoadAlerts();
    }
    monLastLoadLabel = point.load_label;
}

function monSubscribeLive() {
    if (monSSE) return;
    monSSE = new EventSource('/api/admin/metrics/live');
    monSSE.onmessage = (e) => {
        try {
            monOnLivePoint(JSON.parse(e.data));
        } catch (err) {
            console.error('Ошибка SSE-данных мониторинга:', err);
        }
    };
}

// ---- Диапазон графиков истории: ключ UI → часы для /api/admin/metrics ----
const MON_RANGE_HOURS = {
    '1h': 1, '6h': 6, '24h': 24, '7d': 168, '30d': 720,
    '90d': 2160, '6m': 4320, '1y': 8760,
};
function hoursForRange(rangeKey) {
    return MON_RANGE_HOURS[rangeKey] || 24;
}

// ---- Графики истории (Chart.js v4, static/lib/chart4/) ----
const MON_CHART_CANVAS_IDS = ['mon-chart-cpu', 'mon-chart-ram', 'mon-chart-response', 'mon-chart-errors'];
let monCharts = {}; // canvasId → Chart instance, для destroy() перед перерисовкой
const monEmptyEls = {}; // canvasId → элемент-заглушка "Нет данных"

function renderHistoryCharts(points) {
    if (!points.length) {
        // Пустая история (свежий деплой, БД метрик ещё не наполнилась) —
        // явное сообщение вместо графика. Canvas прячем через style.display,
        // НЕ через box.textContent — замена textContent удалила бы canvas
        // из DOM безвозвратно, и переключение на диапазон с данными больше
        // никогда бы его не нарисовало.
        MON_CHART_CANVAS_IDS.forEach(canvasId => monShowEmptyChart(canvasId));
        return;
    }

    MON_CHART_CANVAS_IDS.forEach(canvasId => monHideEmptyChart(canvasId));

    const labels = points.map(p => new Date(p.ts * 1000).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    }));

    monRenderLineChart('mon-chart-cpu', labels, points.map(p => p.cpu_percent), 'CPU %', 'rgba(238,45,98,0.9)');
    monRenderLineChart('mon-chart-ram', labels, points.map(p => p.ram_total_mb ? Math.round(p.ram_used_mb / p.ram_total_mb * 100) : 0), 'RAM %', 'rgba(39,174,96,0.9)');
    monRenderLineChart('mon-chart-response', labels, points.map(p => p.avg_response_ms), 'Время ответа, мс', 'rgba(52,152,219,0.9)');
    monRenderLineChart('mon-chart-errors', labels, points.map(p => p.http_errors), 'Ошибки', 'rgba(230,126,34,0.9)');
}

function monShowEmptyChart(canvasId) {
    if (monCharts[canvasId]) { monCharts[canvasId].destroy(); monCharts[canvasId] = null; }
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    canvas.style.display = 'none';
    let msg = monEmptyEls[canvasId];
    if (!msg && canvas.parentElement) {
        msg = document.createElement('div');
        msg.textContent = 'Нет данных за выбранный период';
        canvas.parentElement.appendChild(msg);
        monEmptyEls[canvasId] = msg;
    }
    if (msg) msg.style.display = '';
}

function monHideEmptyChart(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (canvas) canvas.style.display = '';
    if (monEmptyEls[canvasId]) monEmptyEls[canvasId].style.display = 'none';
}

function monRenderLineChart(canvasId, labels, data, label, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (monCharts[canvasId]) monCharts[canvasId].destroy();
    monCharts[canvasId] = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{ label, data, borderColor: color, backgroundColor: color, tension: 0.2, pointRadius: 0 }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { x: { ticks: { maxTicksLimit: 8 } } },
            plugins: { legend: { display: true } },
        },
    });
}

async function monLoadHistory(hours) {
    const resp = await fetch(`/api/admin/metrics?hours=${hours}`);
    if (!resp.ok) {
        console.error('Ошибка загрузки истории метрик:', resp.status);
        return;
    }
    const data = await resp.json();
    renderHistoryCharts(data.points || []);
    domSet('mon-tile-uptime', formatUptime(data.meta && data.meta.uptime_secs));
}

function monOnRangeChange() {
    const sel = document.getElementById('mon-range');
    monLoadHistory(hoursForRange(sel.value));
}

// ---- Таблица последних алертов ----
function renderAlertsTable(alerts) {
    const tbody = document.getElementById('mon-alerts-body');
    if (!tbody) return;
    if (!alerts.length) {
        tbody.innerHTML = '<tr><td colspan="5">Алертов нет</td></tr>';
        return;
    }
    tbody.innerHTML = alerts.map(a => {
        const suggestionsHtml = (a.suggestions && a.suggestions.length)
            ? `<ul class="admin-alerts-suggestions">${a.suggestions.map(s => `<li>${s}</li>`).join('')}</ul>`
            : '—';
        return `
            <tr>
                <td>${a.datetime || ''}</td>
                <td><span class="admin-badge ${loadLabelBadgeClass(a.load_label)}">${a.load_label || ''}</span></td>
                <td>CPU ${a.cpu_pct || 0}% / RAM ${a.ram_pct || 0}%</td>
                <td>${a.avg_ms || 0} мс</td>
                <td>${suggestionsHtml}</td>
            </tr>
        `;
    }).join('');
}

async function monLoadAlerts() {
    const resp = await fetch('/api/admin/metrics/alerts?limit=50');
    if (!resp.ok) {
        console.error('Ошибка загрузки алертов:', resp.status);
        return;
    }
    const data = await resp.json();
    renderAlertsTable(data.alerts || []);
}

// ---- Инициализация вкладки (вызывается из switchTab() в admin.html) ----
function loadMonitoringTab() {
    monLoadHistory(24);
    monLoadAlerts();
    monSubscribeLive();
}
