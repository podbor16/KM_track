// static/js/admin-medals.js
// Вкладка "Сертификаты" в /admin — статистика страницы сертификата «Забега Единства»
// (/medals/): открыли страницу, скачали, поделились — всего, по рамкам и по часам; выгрузка в Excel.
// API: src/krasmarafon/routers/medals.py, данные — лог nginx (src/analytics/medals_stats.py)

function mdEsc(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

async function loadMedalsTab() {
    const box = document.getElementById('medals-content');
    box.innerHTML = '<div class="admin-loading">Загрузка…</div>';
    try {
        const r = await fetch('/api/admin/medals-stats');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        box.innerHTML = medalsHtml(await r.json());
    } catch (e) {
        box.innerHTML = `<div class="admin-error">Ошибка: ${mdEsc(e.message)}</div>`;
    }
}

function medalsHtml(s) {
    const ev = s.events;
    const card = (title, value) => `<div class="md-card"><div class="md-card-value">${mdEsc(value)}</div>
        <div class="md-card-title">${mdEsc(title)}</div></div>`;
    const cards = Object.keys(ev).map(e => card(ev[e], s.totals[e]))
        .concat([card('Уникальных посетителей', s.visitors),
                 card('Посетителей скачали', s.conversion === null ? '—' : `${s.conversion}%`)]).join('');
    const frames = s.by_frame.map(r => `<tr><td>${mdEsc(r.label)}</td><td>${r.download}</td><td>${r.share}</td></tr>`).join('');
    const hours = s.by_hour.map(r => `<tr><td>${mdEsc(r.hour)}</td>${Object.keys(ev).map(e => `<td>${r[e]}</td>`).join('')}</tr>`).join('');
    const when = iso => mdEsc(iso.slice(0, 16).replace('T', ' '));      // время Красноярска, без «+07:00»
    const period = s.first ? `События с ${when(s.first)} по ${when(s.last)}` : 'Событий пока нет';
    return `<div class="dq-summary">${period}</div>
        <div class="md-cards">${cards}</div>
        <h3>По рамкам</h3>
        <div class="admin-table-scroll"><table class="admin-alerts-table">
            <thead><tr><th>Рамка</th><th>Скачали</th><th>Поделились</th></tr></thead><tbody>${frames}</tbody></table></div>
        <h3>По часам</h3>
        <div class="admin-table-scroll"><table class="admin-alerts-table">
            <thead><tr><th>Час</th>${Object.values(ev).map(t => `<th>${mdEsc(t)}</th>`).join('')}</tr></thead>
            <tbody>${hours || `<tr><td colspan="${Object.keys(ev).length + 1}">Нет данных</td></tr>`}</tbody></table></div>`;
}
