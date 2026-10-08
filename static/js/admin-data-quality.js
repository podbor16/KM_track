// static/js/admin-data-quality.js
// Вкладка "Качество данных" в /admin — находки проверок привязки заявок и
// результатов к карточкам клиентов (src/analytics/data_quality.py) и действия
// по ним: склеить карточки, удалить «Not started» со старым номером, исправить ФИО
// не в каноническом виде, запомнить
// решение «разные люди»/«оставить как есть» (больше не показывается).
// API: src/krasmarafon/routers/data_quality.py

const DQ_CODES = {
    'R-LEAD': 'Заявка на этот забег у другой карточки',
    'R-DUP': 'Два результата в одном забеге',
    'R-CARD': 'Результат расходится с карточкой',
    'R-CAT': 'ДР или пол не подходят к категории',
    'C-TWIN': 'Похоже на одного человека',
    'HYG': 'ФИО в протоколе не в каноническом виде',
    'L-KID': 'Детский забег: возраст или дистанция не сходятся',
};
const DQ_SEVERITY = { high: 'важно', medium: 'проверить', low: 'скорее норма' };
const DQ_RENDER_LIMIT = 200;    // после большого импорта находок могут быть сотни — DOM не раздуваем

let dqFindings = [];

function dqEsc(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

async function dqRequest(url, body) {
    const r = await fetch(url, {
        method: body === undefined ? 'GET' : 'POST',
        headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${r.status}`);
    return data;
}

async function loadDataQualityTab() {
    const box = document.getElementById('dq-content');
    const release = adminHoldHeight(box);
    box.innerHTML = '<div class="admin-loading">Проверка базы…</div>';
    try {
        dqFindings = (await dqRequest('/api/admin/data-quality')).findings;
        dqFillEventFilter();
        dqRender();
    } catch (e) {
        box.innerHTML = `<div class="admin-error">Ошибка проверки: ${dqEsc(e.message)}</div>`;
    } finally {
        release();
    }
}

function dqFillEventFilter() {
    const sel = document.getElementById('dq-event');
    const current = sel.value;
    const events = [...new Set(dqFindings.map(f => f.event).filter(Boolean))].sort();
    sel.innerHTML = '<option value="">Все забеги</option>'
        + events.map(e => `<option value="${dqEsc(e)}">${dqEsc(e)}</option>`).join('');
    if (!adminRestoreValue('dq-event') && events.includes(current)) sel.value = current;
}

function dqVisible() {
    const ev = document.getElementById('dq-event').value;
    const sev = document.getElementById('dq-severity').value;
    return dqFindings.filter(f => (!ev || f.event === ev) && (!sev || f.severity === sev));
}

function dqRender() {
    const box = document.getElementById('dq-content');
    const items = dqVisible();
    const counts = {};
    dqFindings.forEach(f => { counts[f.code] = (counts[f.code] || 0) + 1; });
    const summary = Object.keys(counts).length
        ? Object.entries(counts).map(([c, n]) => `${dqEsc(DQ_CODES[c] || c)}: <b>${n}</b>`).join(' · ')
        : 'Проблем не найдено';
    document.getElementById('dq-summary').innerHTML = summary;
    const more = items.length > DQ_RENDER_LIMIT
        ? `<div class="admin-loading">Показаны ${DQ_RENDER_LIMIT} из ${items.length} — уточните фильтр</div>` : '';
    box.innerHTML = items.length
        ? items.slice(0, DQ_RENDER_LIMIT).map(dqItemHtml).join('') + more
        : '<div class="admin-loading">Нет находок по фильтру</div>';
}

function dqCardHtml(c) {
    const list = (title, arr) => arr.length
        ? `<div class="dq-card-list"><span>${title}:</span> ${arr.map(dqEsc).join('; ')}</div>` : '';
    return `<div class="dq-card">
        <div class="dq-card-title">#${c.id} ${dqEsc(c.surname)} ${dqEsc(c.name)} <span class="dq-muted">${dqEsc(c.birthday)}</span></div>
        ${list('Результаты', c.results)}${list('Заявки', c.leads)}
    </div>`;
}

function dqItemHtml(f) {
    const idx = dqFindings.indexOf(f);
    const blockers = (f.blockers || []).length
        ? `<div class="dq-blockers">Не склеивать автоматически: ${f.blockers.map(dqEsc).join('; ')}</div>` : '';
    let actions = '';
    if (f.proposal) {
        actions += `<div class="dq-merge">
            <input class="admin-select dq-in-surname" value="${dqEsc(f.proposal.surname)}" placeholder="Фамилия">
            <input class="admin-select dq-in-name" value="${dqEsc(f.proposal.name)}" placeholder="Имя">
            <input class="admin-select dq-in-bd" value="${dqEsc(f.proposal.birthday)}" placeholder="ГГГГ-ММ-ДД">
            <button class="km-btn km-btn--primary" onclick="dqMerge(${idx}, this)">Склеить</button>
            <button class="km-btn km-btn--secondary" onclick="dqDismiss(${idx}, 'different_people', this)">Разные люди</button>
        </div>`;
    } else if (f.code === 'HYG' && (f.fix || []).length === 2) {
        actions += `<div class="dq-merge">
            <input class="admin-select dq-in-surname" value="${dqEsc(f.fix[0])}" placeholder="Фамилия">
            <input class="admin-select dq-in-name" value="${dqEsc(f.fix[1])}" placeholder="Имя">
            <button class="km-btn km-btn--primary" onclick="dqFixFio(${idx}, this)">Исправить ФИО</button>
            <button class="km-btn km-btn--secondary" onclick="dqDismiss(${idx}, 'keep', this)">Оставить как есть</button>
        </div>`;
    } else if (f.code === 'R-DUP' && f.auto) {
        actions += `<button class="km-btn km-btn--primary" onclick="dqDeleteResult(${idx}, this)">Удалить «Not started»</button>
            <button class="km-btn km-btn--secondary" onclick="dqDismiss(${idx}, 'keep', this)">Оставить</button>`;
    } else {
        actions += `<button class="km-btn km-btn--secondary" onclick="dqDismiss(${idx}, 'keep', this)">Оставить как есть</button>`;
    }
    return `<div class="dq-item dq-item--${dqEsc(f.severity)}" id="dq-item-${idx}">
        <div class="dq-item-head">
            <span class="admin-badge dq-sev--${dqEsc(f.severity)}">${dqEsc(DQ_SEVERITY[f.severity] || f.severity)}</span>
            <span class="dq-code">${dqEsc(DQ_CODES[f.code] || f.code)}</span>
            ${f.event ? `<span class="dq-muted">${dqEsc(f.event)}</span>` : ''}
        </div>
        <div class="dq-message">${dqEsc(f.message)}</div>
        <div class="dq-cards">${f.cards.map(dqCardHtml).join('')}</div>
        ${blockers}
        <div class="dq-actions">${actions}<span class="dq-status"></span></div>
    </div>`;
}

function dqDone(idx, text) {
    const el = document.getElementById(`dq-item-${idx}`);
    el.classList.add('dq-item--done');
    el.querySelector('.dq-actions').innerHTML = `<span class="dq-status dq-status--ok">${dqEsc(text)}</span>`;
}

function dqFail(btn, e) {
    btn.disabled = false;
    btn.closest('.dq-actions').querySelector('.dq-status').textContent = e.message;
}

async function dqMerge(idx, btn) {
    const f = dqFindings[idx];
    const item = document.getElementById(`dq-item-${idx}`);
    const body = {
        client_ids: f.cards.map(c => c.id), key: f.key,
        surname: item.querySelector('.dq-in-surname').value.trim(),
        name: item.querySelector('.dq-in-name').value.trim(),
        birthday: item.querySelector('.dq-in-bd').value.trim(),
    };
    if ((f.blockers || []).length && !confirm(`Предохранители против склейки:\n${f.blockers.join('\n')}\n\nВсё равно склеить?`)) return;
    btn.disabled = true;
    try {
        const r = await dqRequest('/api/admin/data-quality/merge', body);
        dqDone(idx, `Склеено в карточку #${r.client_id}: ${body.surname} ${body.name} ${body.birthday}`);
    } catch (e) { dqFail(btn, e); }
}

async function dqFixFio(idx, btn) {
    const f = dqFindings[idx];
    const item = document.getElementById(`dq-item-${idx}`);
    const body = {
        result_id: f.result_id, key: f.key,
        surname: item.querySelector('.dq-in-surname').value.trim(),
        name: item.querySelector('.dq-in-name').value.trim(),
    };
    btn.disabled = true;
    try {
        const r = await dqRequest('/api/admin/data-quality/fix-fio', body);
        dqDone(idx, `ФИО исправлено: ${body.surname} ${body.name} (карточка #${r.client_id})`);
    } catch (e) { dqFail(btn, e); }
}

async function dqDeleteResult(idx, btn) {
    const f = dqFindings[idx];
    btn.disabled = true;
    try {
        await dqRequest('/api/admin/data-quality/delete-result', { result_id: f.result_id, key: f.key });
        dqDone(idx, 'Результат удалён');
    } catch (e) { dqFail(btn, e); }
}

async function dqDismiss(idx, decision, btn) {
    const f = dqFindings[idx];
    btn.disabled = true;
    try {
        await dqRequest('/api/admin/data-quality/dismiss', { key: f.key, decision });
        dqDone(idx, decision === 'different_people' ? 'Запомнено: разные люди' : 'Запомнено: оставить как есть');
    } catch (e) { dqFail(btn, e); }
}

async function dqApplyAuto(btn) {
    if (!confirm('Удалить «Not started» со старыми номерами и склеить карточки, где нет ни одного предохранителя?')) return;
    btn.disabled = true;
    const box = document.getElementById('dq-auto-result');
    box.textContent = 'Применяю…';
    try {
        const r = await dqRequest('/api/admin/data-quality/apply-auto', {});
        box.innerHTML = `Удалено результатов: <b>${r.deleted.length}</b>, склеено групп: <b>${r.merged.length}</b>`
            + (r.skipped.length ? `, пропущено: <b>${r.skipped.length}</b>` : '');
        await loadDataQualityTab();
    } catch (e) {
        box.textContent = `Ошибка: ${e.message}`;
    } finally {
        btn.disabled = false;
    }
}
