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

// ---- Инициализация вкладки (вызывается из switchTab() в admin.html) ----
function loadMonitoringTab() {
    monLoadHistory(24);
    monLoadAlerts();
    monSubscribeLive();
}
