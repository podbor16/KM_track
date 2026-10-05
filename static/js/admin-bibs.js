// static/js/admin-bibs.js
// /admin → «Стартовый список» → «Присвоить номера». Правила — src/analytics/bibs.py:
// диапазон на дистанцию (Детский — на год рождения, 500 м без номеров), уже присвоенные
// номера не трогаются, номер — самой ранней заявке человека, не хватает номеров — ничего
// не записывается. Диапазоны запоминаются для события. API: src/krasmarafon/routers/bibs.py

let bibsState = null;          // {event_name, event_year, groups}
let bibsPreviewKey = '';       // диапазоны, по которым прошёл предпросмотр без ошибок

function bibsEsc(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

async function bibsRequest(url, body) {
    const r = await fetch(url, {
        method: body === undefined ? 'GET' : 'POST',
        headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
        const d = data.detail;
        const err = new Error(typeof d === 'string' ? d : (d && d.message) || `HTTP ${r.status}`);
        err.payload = d && typeof d === 'object' ? d : null;
        throw err;
    }
    return data;
}

async function openBibsPanel() {
    const panel = document.getElementById('bibs-panel');
    const eventName = document.getElementById('leads-event-name').value;
    const year = document.getElementById('leads-year-filter').value;
    if (!eventName || !year) {
        panel.style.display = '';
        panel.innerHTML = '<div class="admin-error">Выберите мероприятие и год в фильтрах выше</div>';
        return;
    }
    panel.style.display = '';
    panel.innerHTML = '<div class="admin-loading">Загрузка…</div>';
    try {
        const data = await bibsRequest(`/api/admin/bibs?event_name=${encodeURIComponent(eventName)}&event_year=${year}`);
        bibsState = { event_name: eventName, event_year: Number(year), groups: data.groups };
        bibsPreviewKey = '';
        renderBibsForm(data);
    } catch (e) {
        panel.innerHTML = `<div class="admin-error">Ошибка: ${bibsEsc(e.message)}</div>`;
    }
}

function renderBibsForm(data) {
    const panel = document.getElementById('bibs-panel');
    const rows = data.groups.map((g, i) => `
        <tr>
            <td>${bibsEsc(g.label)}</td>
            <td class="bibs-num">${g.need}</td>
            <td class="bibs-num">${g.with_bib}</td>
            <td class="bibs-num">${g.duplicates || ''}</td>
            <td><input type="number" min="1" class="admin-select bibs-start" data-i="${i}" value="${g.range ? g.range[0] : ''}" oninput="bibsChanged()"></td>
            <td><input type="number" min="1" class="admin-select bibs-end" data-i="${i}" value="${g.range ? g.range[1] : ''}" oninput="bibsChanged()"></td>
            <td class="bibs-result" id="bibs-result-${i}"></td>
        </tr>`).join('');
    const skipped = data.skipped.length ? `<div class="dq-muted">Без номеров: ${data.skipped.map(bibsEsc).join(', ')}</div>` : '';
    panel.innerHTML = `
        <div class="bibs-head"><b>Присвоение номеров — ${bibsEsc(bibsState.event_name)} ${bibsState.event_year}</b>
            <button class="km-btn km-btn--secondary" onclick="closeBibsPanel()">Закрыть</button></div>
        <div class="dq-muted">Номер получает самая ранняя заявка человека; уже присвоенные номера не меняются и не выдаются повторно.
            Диапазоны запоминаются для события. Если где-то не хватает номеров — ничего не записывается.</div>
        ${skipped}
        ${data.groups.length ? `
        <div class="bibs-table-wrap"><table class="admin-alerts-table bibs-table">
            <thead><tr><th>Группа</th><th>Без номера</th><th>С номером</th><th>Дубли</th><th>С</th><th>По</th><th>Предпросмотр</th></tr></thead>
            <tbody>${rows}</tbody>
        </table></div>
        <div class="dq-actions">
            <button class="km-btn km-btn--secondary" onclick="previewBibs(this)">Предпросмотр</button>
            <button class="km-btn km-btn--primary" id="bibs-assign-btn" onclick="assignBibs(this)" disabled>Присвоить номера</button>
            <span class="dq-status" id="bibs-status"></span>
        </div>` : '<div class="admin-loading">Заявок нет</div>'}`;
}

function bibsRanges() {
    return bibsState.groups.map((g, i) => {
        const s = document.querySelector(`.bibs-start[data-i="${i}"]`).value;
        const e = document.querySelector(`.bibs-end[data-i="${i}"]`).value;
        return { distance: g.distance, key: g.key, start: s === '' ? null : Number(s), end: e === '' ? null : Number(e) };
    });
}

function bibsChanged() {
    bibsPreviewKey = '';
    document.getElementById('bibs-assign-btn').disabled = true;
}

function renderBibsResult(groups) {
    groups.forEach((g, i) => {
        const cell = document.getElementById(`bibs-result-${i}`);
        if (!cell) return;
        if (g.error) cell.innerHTML = `<span class="dq-status">${bibsEsc(g.error)}</span>`;
        else if (!g.need) cell.innerHTML = '<span class="dq-muted">всем уже присвоено</span>';
        else cell.innerHTML = `<span class="dq-status--ok">${g.need} ${bibsPlural(g.need)}: ${g.first}–${g.last}${g.last - g.first + 1 > g.need ? ' (с пропусками занятых)' : ''}</span>`;
    });
}

function bibsPlural(n) {
    const d = n % 10, dd = n % 100;
    if (d === 1 && dd !== 11) return 'номер';
    if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return 'номера';
    return 'номеров';
}

async function previewBibs(btn) {
    const ranges = bibsRanges();
    btn.disabled = true;
    const status = document.getElementById('bibs-status');
    try {
        const r = await bibsRequest('/api/admin/bibs/preview', { ...bibsState, ranges });
        renderBibsResult(r.groups);
        bibsPreviewKey = r.ok && r.to_assign ? JSON.stringify(ranges) : '';
        document.getElementById('bibs-assign-btn').disabled = !bibsPreviewKey;
        status.className = r.ok ? 'dq-status dq-status--ok' : 'dq-status';
        status.textContent = r.ok ? (r.to_assign ? `Будет присвоено: ${r.to_assign}` : 'Присваивать некому') : 'Есть ошибки — номера не будут присвоены';
    } catch (e) {
        status.className = 'dq-status';
        status.textContent = e.message;
    } finally {
        btn.disabled = false;
    }
}

async function assignBibs(btn) {
    const ranges = bibsRanges();
    if (JSON.stringify(ranges) !== bibsPreviewKey) return;
    if (!confirm('Присвоить номера по предпросмотру? Уже присвоенные номера не изменятся.')) return;
    btn.disabled = true;
    const status = document.getElementById('bibs-status');
    try {
        const r = await bibsRequest('/api/admin/bibs/assign', { ...bibsState, ranges });
        renderBibsResult(r.groups);
        status.className = 'dq-status dq-status--ok';
        status.textContent = `Присвоено номеров: ${r.assigned}`;
        bibsPreviewKey = '';
        if (typeof loadLeads === 'function') loadLeads(true);
    } catch (e) {
        if (e.payload && e.payload.groups) renderBibsResult(e.payload.groups);
        status.className = 'dq-status';
        status.textContent = e.message;
    }
}

function closeBibsPanel() {
    const panel = document.getElementById('bibs-panel');
    panel.style.display = 'none';
    panel.innerHTML = '';
    bibsState = null;
}
