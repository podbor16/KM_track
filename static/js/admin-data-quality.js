// static/js/admin-data-quality.js
// Вкладка "Качество данных" в /admin — находки проверок привязки заявок и
// результатов к карточкам клиентов (src/analytics/data_quality.py) и действия
// по ним: склеить карточки, удалить «Not started» со старым номером, исправить ФИО
// не в каноническом виде, поправить поля результата / заявки / карточки, запомнить
// решение «разные люди»/«оставить как есть» (больше не показывается); отменить
// любое из этих действий («Отменить» сразу после него или в «Последних действиях»).
// API: src/krasmarafon/routers/data_quality.py

const DQ_CODES = {
    'R-LEAD': 'Заявка на этот забег у другой карточки',
    'R-FOREIGN': 'Похоже, чужая строка (тёзка)',
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
        actions += dqQuickFixHtml(f, idx)
            + `<button class="km-btn km-btn--secondary" onclick="dqDismiss(${idx}, 'keep', this)">Оставить как есть</button>`;
    }
    if (f.record) actions += `<button class="km-btn km-btn--secondary" onclick="dqToggleEdit(${idx})">Исправить…</button>`;
    if (f.record)
        actions += `<button class="km-btn km-btn--secondary" onclick="dqToggleMove(${idx})">Перенести на карточку…</button>`;
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
        ${f.record ? dqEditHtml(f, idx) : ''}
        ${f.record ? dqMoveHtml(f, idx) : ''}
    </div>`;
}

// ---- Правка полей строки находки (результат / заявка / карточка) ----

const DQ_EDIT_FIELDS = {
    results: [['surname', 'Фамилия'], ['name', 'Имя'], ['birthday', 'ДР'], ['sex', 'Пол'], ['category', 'Категория']],
    leads: [['surname', 'Фамилия'], ['name', 'Имя'], ['birthday', 'ДР'], ['event_distance', 'Дистанция']],
};
const DQ_SEXES = ['Мужчина', 'Женщина'];
const DQ_WHAT = { results: 'результат', leads: 'заявку', clients: 'карточку' };

function dqEditHtml(f, idx) {
    const rec = f.record;
    const input = ([k, label]) => {
        const v = rec[k] ?? '';
        let el;
        if (k === 'sex') {
            el = `<select class="admin-select" data-field="sex" onchange="dqFillCategories(${idx})">${DQ_SEXES.map(o =>
                `<option${o === v ? ' selected' : ''}>${dqEsc(o)}</option>`).join('')}</select>`;
        } else if (k === 'category' && rec.category_options) {
            el = `<select class="admin-select dq-in-category" data-field="category"></select>`;
        } else if (k === 'event_distance' && (rec.distance_options || []).length) {
            const opts = rec.distance_options.includes(v) ? rec.distance_options : [v, ...rec.distance_options];
            el = `<select class="admin-select" data-field="event_distance">${opts.map(o =>
                `<option${o === v ? ' selected' : ''}>${dqEsc(o)}</option>`).join('')}</select>`;
        } else {
            el = `<input class="admin-select" data-field="${k}" value="${dqEsc(v)}"${k === 'birthday' ? ' placeholder="ГГГГ-ММ-ДД"' : ''}>`;
        }
        return `<label class="dq-edit-field"><span>${label}</span>${el}</label>`;
    };
    return `<div class="dq-edit" id="dq-edit-${idx}" hidden>
        <div class="dq-muted">Правка: ${DQ_WHAT[rec.table]} #${Number(rec.id)}</div>
        <div class="dq-merge">${DQ_EDIT_FIELDS[rec.table].map(input).join('')}
            <button class="km-btn km-btn--primary" onclick="dqSaveEdit(${idx}, this)">Сохранить</button>
        </div>
    </div>`;
}

function dqToggleEdit(idx) {
    const box = document.getElementById(`dq-edit-${idx}`);
    if (!box) return;
    box.hidden = !box.hidden;
    if (!box.hidden) dqFillCategories(idx);
}

// Категории протокола этого забега — только подходящие выбранному полу («» у категории — любой пол)
function dqFillCategories(idx) {
    const rec = dqFindings[idx].record;
    const sel = document.querySelector(`#dq-edit-${idx} .dq-in-category`);
    if (!sel || !rec.category_options) return;
    const sex = document.querySelector(`#dq-edit-${idx} [data-field="sex"]`).value;
    const current = sel.options.length ? sel.value : rec.category;
    const opts = rec.category_options.filter(o => !o.sex || o.sex === sex).map(o => o.label);
    const keep = opts.includes(current) ? current : '';
    sel.innerHTML = (keep ? '' : '<option value="">— выберите категорию —</option>')
        + opts.map(o => `<option${o === keep ? ' selected' : ''}>${dqEsc(o)}</option>`).join('');
}

// R-CARD: две очевидные правки — строку результата под карточку или карточку под результат
function dqQuickFixHtml(f, idx) {
    const rec = f.record, c = (f.cards || [])[0];
    if (f.code !== 'R-CARD' || !rec || rec.table !== 'results' || !c) return '';
    const diff = ['surname', 'name', 'birthday'].filter(k => String(rec[k]) !== String(c[k]));
    if (!diff.length) return '';
    const show = o => diff.map(k => o[k]).join(' ');
    return `<button class="km-btn km-btn--primary" onclick="dqQuickFix(${idx}, 'results', this)">В результат — как в карточке (${dqEsc(show(c))})</button>
        <button class="km-btn km-btn--secondary" onclick="dqQuickFix(${idx}, 'clients', this)">В карточку — как в результате (${dqEsc(show(rec))})</button>`;
}

async function dqSendEdit(idx, table, id, fields, btn) {
    const f = dqFindings[idx];
    btn.disabled = true;
    try {
        const r = await dqRequest('/api/admin/data-quality/edit', { table, id, fields, key: f.key });
        const text = Object.entries(fields).map(([k, v]) => v).join(' ');
        dqDone(idx, `Исправлено (${DQ_WHAT[table]}): ${text}`, r.action_id);
        const box = document.getElementById(`dq-edit-${idx}`);
        if (box) box.hidden = true;
    } catch (e) {
        btn.disabled = false;
        const st = document.querySelector(`#dq-item-${idx} .dq-status`);
        if (st) st.textContent = e.message;
    }
}

function dqQuickFix(idx, table, btn) {
    const f = dqFindings[idx], rec = f.record, c = f.cards[0];
    const [src, id] = table === 'results' ? [c, rec.id] : [rec, c.id];
    const fields = {};
    ['surname', 'name', 'birthday'].forEach(k => { if (String(rec[k]) !== String(c[k])) fields[k] = String(src[k]); });
    dqSendEdit(idx, table, id, fields, btn);
}

function dqSaveEdit(idx, btn) {
    const f = dqFindings[idx];
    const fields = {};
    document.querySelectorAll(`#dq-edit-${idx} [data-field]`).forEach(el => {
        const v = el.value.trim();
        if (v !== String(f.record[el.dataset.field] ?? '')) fields[el.dataset.field] = v;
    });
    if (fields.category === '') {
        document.querySelector(`#dq-item-${idx} .dq-status`).textContent = 'Выберите категорию';
        return;
    }
    if (!Object.keys(fields).length) {
        document.querySelector(`#dq-item-${idx} .dq-status`).textContent = 'Ничего не изменено';
        return;
    }
    dqSendEdit(idx, f.record.table, f.record.id, fields, btn);
}

function dqDone(idx, text, actionId) {
    const el = document.getElementById(`dq-item-${idx}`);
    el.classList.add('dq-item--done');
    const undo = actionId
        ? ` <button class="km-btn km-btn--secondary" onclick="dqUndo(${Number(actionId)}, this)">Отменить</button>` : '';
    el.querySelector('.dq-actions').innerHTML = `<span class="dq-status dq-status--ok">${dqEsc(text)}</span>${undo}`;
    dqRefreshJournal();
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
        dqDone(idx, `Склеено в карточку #${r.client_id}: ${body.surname} ${body.name} ${body.birthday}`, r.action_id);
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
        dqDone(idx, `ФИО исправлено: ${body.surname} ${body.name} (карточка #${r.client_id})`, r.action_id);
    } catch (e) { dqFail(btn, e); }
}

async function dqDeleteResult(idx, btn) {
    const f = dqFindings[idx];
    btn.disabled = true;
    try {
        const r = await dqRequest('/api/admin/data-quality/delete-result', { result_id: f.result_id, key: f.key });
        dqDone(idx, 'Результат удалён', r.action_id);
    } catch (e) { dqFail(btn, e); }
}

async function dqDismiss(idx, decision, btn) {
    const f = dqFindings[idx];
    btn.disabled = true;
    try {
        const r = await dqRequest('/api/admin/data-quality/dismiss', { key: f.key, decision });
        dqDone(idx, decision === 'different_people' ? 'Запомнено: разные люди' : 'Запомнено: оставить как есть',
               r.action_id);
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

// ---- Отмена действий (журнал dq_actions) ----

async function dqUndo(actionId, btn) {
    if (!confirm('Отменить это действие и вернуть данные как было до него?')) return;
    btn.disabled = true;
    try {
        await dqRequest('/api/admin/data-quality/undo', { action_id: actionId });
        const box = btn.parentElement;
        btn.remove();
        box.insertAdjacentHTML('beforeend',
            ' <span class="dq-status dq-status--ok">Отменено — находка вернётся после «Проверить заново»</span>');
        dqRefreshJournal();
    } catch (e) {
        btn.disabled = false;
        alert(`Не удалось отменить: ${e.message}`);
    }
}

function dqRefreshJournal() {
    if (document.getElementById('dq-journal')?.open) dqLoadJournal();
}

async function dqLoadJournal() {
    const box = document.getElementById('dq-journal-list');
    try {
        const { actions } = await dqRequest('/api/admin/data-quality/actions?limit=50');
        box.innerHTML = actions.length ? actions.map(a => {
            const state = a.undone ? '<span class="dq-muted">отменено</span>'
                : a.can_undo ? `<button class="km-btn km-btn--secondary" onclick="dqUndo(${Number(a.id)}, this)">Отменить</button>`
                : `<span class="dq-muted" title="${dqEsc(a.why_not)}">нельзя отменить: ${dqEsc(a.why_not)}</span>`;
            return `<div class="dq-journal-row${a.undone ? ' dq-journal-row--undone' : ''}">
                <span class="dq-muted">#${Number(a.id)} · ${dqEsc(a.done_at)} · ${dqEsc(a.done_by)}</span>
                <span class="dq-journal-text">${dqEsc(a.text)}</span>${state}</div>`;
        }).join('') : '<div class="admin-loading">Действий пока нет</div>';
    } catch (e) {
        box.innerHTML = `<div class="admin-error">Ошибка: ${dqEsc(e.message)}</div>`;
    }
}

// ---- Перенос результата на другую карточку (поиск по ФИО) ----

function dqCardLine(c) {
    return `<span class="dq-move-card">#${Number(c.id)} ${dqEsc(c.surname)} ${dqEsc(c.name)} <b>${dqEsc(c.birthday)}</b></span>`;
}

function dqMoveHtml(f, idx) {
    const rec = f.record;
    const cur = (f.cards || [])[0];                     // у находок со строкой первая карточка — карточка строки
    // подсказки: R-LEAD — карточка заявки, R-FOREIGN — тёзки, к которым строка подходит по возрасту
    const label = { 'R-LEAD': 'На карточку заявки', 'R-FOREIGN': 'Подходящий тёзка' }[f.code];
    const hint = label ? f.cards.slice(1).map(c => `<div class="dq-move-row"><span>${label}: ${dqCardLine(c)}</span>
        <button class="km-btn km-btn--primary" onclick="dqMove(${idx}, ${Number(c.id)}, this)">Сюда</button></div>`).join('') : '';
    const what = rec.table === 'leads' ? 'заявки' : 'результата';
    return `<div class="dq-edit dq-move" id="dq-move-${idx}" hidden>
        <div class="dq-muted">Перенос ${what} #${Number(rec.id)} (${dqEsc(rec.surname)} ${dqEsc(rec.name)} ${dqEsc(rec.birthday)})
            ${cur ? ` с карточки #${Number(cur.id)}` : ''}. ФИО и ДР в строке не меняются.</div>
        ${hint}
        <input class="admin-select dq-move-q" placeholder="Поиск карточки: фамилия имя" value="${dqEsc(rec.surname)}"
               oninput="dqSearchCards(${idx})">
        <div class="dq-move-list"></div>
        <details class="dq-move-new"><summary>Новая карточка</summary>
            <div class="dq-merge">
                <input class="admin-select" data-new="surname" value="${dqEsc(rec.surname)}" placeholder="Фамилия">
                <input class="admin-select" data-new="name" value="${dqEsc(rec.name)}" placeholder="Имя">
                <input class="admin-select" data-new="birthday" value="${dqEsc(rec.birthday)}" placeholder="ГГГГ-ММ-ДД">
                <button class="km-btn km-btn--primary" onclick="dqMoveNew(${idx}, this)">Создать и перенести</button>
            </div>
        </details>
    </div>`;
}

function dqToggleMove(idx) {
    const box = document.getElementById(`dq-move-${idx}`);
    if (!box) return;
    box.hidden = !box.hidden;
    if (!box.hidden) dqSearchCards(idx);
}

const dqSearchTimers = {};
function dqSearchCards(idx) {
    clearTimeout(dqSearchTimers[idx]);
    dqSearchTimers[idx] = setTimeout(async () => {
        const box = document.getElementById(`dq-move-${idx}`);
        const q = box.querySelector('.dq-move-q').value.trim();
        const list = box.querySelector('.dq-move-list');
        if (q.length < 2) { list.innerHTML = ''; return; }
        list.innerHTML = '<div class="dq-muted">Поиск…</div>';
        try {
            const { cards } = await dqRequest('/api/admin/data-quality/cards?q=' + encodeURIComponent(q));
            if (box.querySelector('.dq-move-q').value.trim() !== q) return;      // ввод изменился — ждём свежий ответ
            const own = new Set((dqFindings[idx].cards || []).slice(0, 1).map(c => c.id));
            list.innerHTML = cards.length ? cards.map(c => `<div class="dq-move-row">
                <span>${dqCardLine(c)} <span class="dq-muted">${dqEsc((c.events || []).join('; ') || 'без забегов')}</span></span>
                ${own.has(c.id) ? '<span class="dq-muted">текущая</span>'
                    : `<button class="km-btn km-btn--secondary" onclick="dqMove(${idx}, ${Number(c.id)}, this)">Сюда</button>`}
            </div>`).join('') : '<div class="dq-muted">Ничего не найдено</div>';
        } catch (e) {
            list.innerHTML = `<div class="dq-status">${dqEsc(e.message)}</div>`;
        }
    }, 300);
}

async function dqSendMove(idx, body, text, btn) {
    const f = dqFindings[idx];
    btn.disabled = true;
    try {
        const r = await dqRequest('/api/admin/data-quality/move',
            { table: f.record.table, row_id: f.record.id, key: f.key, ...body });
        dqDone(idx, `${text} #${r.client_id}`, r.action_id);
        document.getElementById(`dq-move-${idx}`).hidden = true;
    } catch (e) {
        btn.disabled = false;
        const st = document.querySelector(`#dq-item-${idx} .dq-status`);
        if (st) st.textContent = e.message;
        alert(e.message);
    }
}

// [что, «перенесён/перенесена»] — для подтверждений и статуса
function dqRowWords(idx) {
    return dqFindings[idx].record.table === 'leads' ? ['заявку', 'Заявка перенесена'] : ['результат', 'Результат перенесён'];
}

function dqMove(idx, clientId, btn) {
    const card = btn.closest('.dq-move-row')?.querySelector('.dq-move-card')?.innerText || `#${clientId}`;
    const [what, done] = dqRowWords(idx);
    if (!confirm(`Перенести ${what} на карточку ${card}?`)) return;
    dqSendMove(idx, { to_client_id: clientId }, `${done} на карточку`, btn);
}

function dqMoveNew(idx, btn) {
    const box = document.getElementById(`dq-move-${idx}`);
    const card = {};
    box.querySelectorAll('[data-new]').forEach(el => { card[el.dataset.new] = el.value.trim(); });
    const [what, done] = dqRowWords(idx);
    if (!confirm(`Создать карточку ${card.surname} ${card.name} ${card.birthday} и перенести на неё ${what}?`)) return;
    dqSendMove(idx, { new_card: card }, `${done} на новую карточку`, btn);
}
