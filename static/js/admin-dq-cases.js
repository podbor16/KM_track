// static/js/admin-dq-cases.js
// Вкладка /admin → «Качество данных»: очередь дел о людях + дело с вопросами
// (спецификация docs/superpowers/specs/2026-10-28-data-quality-cases-design.md, API — src/krasmarafon/routers/data_quality.py).
// Компьютер — две панели, телефон (< 900 px) — очередь → дело («← К списку»).
// Без alert()/confirm(): опасные кнопки срабатывают со второго нажатия («Точно …?»).

const DQC_API = '/api/admin/data-quality';
const DQC = {
    tab: 'open', lists: null, cases: [], key: null, caseData: null, person: null, done: {}, extra: [],
    moved: new Set(), pos: 0, eventsFilled: false, timers: {}, inited: false,
    seq: 0,             // номер открытия дела: ответ на устаревшее открытие не рисуется
    qseq: 0,            // номер загрузки очереди
    gone: new Set(),    // закрытые дела: другой процесс сервера может отдавать их из кеша до 10 мин
};
const DQC_SITE_NOTE = 'На сайте обновится в течение 5 минут';
const DQC_LEAD_NOTE = 'Повторный импорт файла организатора может перезаписать правку заявки';

function dqEsc(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

async function dqcRequest(url, body) {
    const r = await fetch(url, {
        method: body === undefined ? 'GET' : 'POST',
        headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
        const e = new Error(typeof data.detail === 'string' ? data.detail : `Ошибка сервера (${r.status})`);
        e.status = r.status;
        throw e;
    }
    return data;
}

// ---- Чистые функции (tests/js/test_admin_dq_cases.js) ----

function categoriesFor(options, sex) {
    return options.filter(o => !sex || !o.sex || o.sex === sex).map(o => o.label);
}

function defaultAnswer(q) {
    return (q.answers.find(a => a.recommended) || q.answers[0] || {}).id;
}

function answerBody(q, answerId, values, extraCards) {
    const a = q.answers.find(x => x.id === answerId) || { inputs: [] };
    const inputs = {};
    a.inputs.forEach(i => { if (values[i.name]) inputs[i.name] = values[i.name]; });
    return { question_id: q.id, answer_id: answerId, inputs, extra_cards: extraCards || [] };
}

function isCategoryInput(inp) {
    return Array.isArray(inp.options) && inp.name === 'category';
}

// Пол для списка категорий: поле «Пол» этого же ответа, иначе пол строки (значение поля «Пол» любого ответа вопроса)
function sexFor(q, answer) {
    const own = (answer.inputs || []).find(i => i.name === 'sex');
    if (own) return own.value || '';
    for (const a of q.answers) {
        const s = (a.inputs || []).find(i => i.name === 'sex');
        if (s && s.value) return s.value;
    }
    return '';
}

function selectOptionsHtml(inp, sexValue, current) {
    let opts;
    if (isCategoryInput(inp)) {
        opts = categoriesFor(inp.options, sexValue).map(l => ({ value: l, label: l }));
    } else {
        opts = (inp.options || []).map(o => (typeof o === 'object' ? { value: String(o.value), label: o.label } : { value: o, label: o }));
    }
    const has = opts.some(o => o.value === current);
    const head = has ? '' : (current && !isCategoryInput(inp)
        ? `<option value="${dqEsc(current)}" selected>${dqEsc(current)}</option>`
        : '<option value="">— выберите —</option>');
    return head + opts.map(o => `<option value="${dqEsc(o.value)}"${o.value === current ? ' selected' : ''}>${dqEsc(o.label)}</option>`).join('');
}

function inputHtml(qi, ai, inp, sexValue) {
    const name = `dqc-${qi}-${ai}-${inp.name}`;
    const value = String(inp.value ?? '');
    let el;
    if (inp.type === 'select') {
        const onchange = inp.name === 'sex' ? ` onchange="dqcSexChanged(${qi}, ${ai})"` : '';
        el = `<select class="admin-select" name="${dqEsc(name)}" data-name="${dqEsc(inp.name)}"${onchange}>${selectOptionsHtml(inp, sexValue, value)}</select>`;
    } else {
        const ph = inp.type === 'date' ? ' placeholder="ГГГГ-ММ-ДД" inputmode="numeric"' : '';
        el = `<input class="admin-select" name="${dqEsc(name)}" data-name="${dqEsc(inp.name)}" value="${dqEsc(value)}"${ph} autocomplete="off">`;
    }
    return `<label>${dqEsc(inp.label)}${el}</label>`;
}

function isLeadEdit(q, answerId) {
    return !!q.lead_id && !q.result_id && (answerId === 'birthday' || answerId === 'distance');
}

function questionHtml(q, qi, opts) {
    const o = opts || {};
    const hint = q.hint ? `<div class="dqc-hint">${q.live ? `<b>${dqEsc(q.hint)}</b>` : dqEsc(q.hint)}</div>` : '';
    const head = `<div class="dqc-q-text">${dqEsc(q.text)}</div>${hint}`;
    if (q.state === 'locked') {
        const after = o.after ? `Откроется после ступени «${dqEsc(o.after)}»` : 'Откроется после предыдущих вопросов';
        return `<div class="dqc-q dqc-q--locked" id="dqc-q-${qi}">${head}<div class="dqc-hint">${after}</div></div>`;
    }
    const answers = q.state === 'postponed' ? q.answers.filter(a => a.id !== 'postpone') : q.answers;
    const picked = answers.some(a => a.id === defaultAnswer(q)) ? defaultAnswer(q) : (answers[0] || {}).id;
    const body = answers.map(a => {
        const ai = q.answers.indexOf(a);
        const on = a.id === picked;
        const star = a.recommended ? ' <span class="dqc-star">★ рекомендуем</span>' : '';
        const sex = sexFor(q, a);
        const inputs = (a.inputs || []).length
            ? `<div class="dqc-answer-inputs" id="dqc-in-${qi}-${ai}"${on ? '' : ' hidden'}>${a.inputs.map(i => inputHtml(qi, ai, i, sex)).join('')}</div>`
            : '';
        return `<label class="dqc-answer"><input type="radio" name="dqc-a-${qi}" value="${dqEsc(a.id)}" data-ai="${ai}"${on ? ' checked' : ''}
            onchange="dqcPick(${qi})"> ${dqEsc(a.label)}${star}</label>${inputs}`;
    }).join('');
    const postponed = q.state === 'postponed' ? '<div class="dqc-hint">Отложено</div>' : '';
    const lead = q.lead_id && !q.result_id && q.answers.some(a => isLeadEdit(q, a.id))
        ? `<div class="dqc-hint" id="dqc-lead-${qi}"${isLeadEdit(q, picked) ? '' : ' hidden'}>${DQC_LEAD_NOTE}</div>` : '';
    const apply = answers.length
        ? `<div class="dq-actions"><button class="km-btn km-btn--primary" onclick="dqcApply(${qi}, this)">Применить</button>
            <span class="dq-status" id="dqc-st-${qi}"></span></div>` : '';
    return `<div class="dqc-q dqc-q--${q.state === 'postponed' ? 'postponed' : 'current'}" id="dqc-q-${qi}">
        ${head}${postponed}${body}${lead}${apply}<div id="dqc-conf-${qi}"></div></div>`;
}

function rowHtml(r) {
    const parts = [r.year, r.event, r.start_number ? `№${r.start_number}` : '', r.category, r.status].filter(x => x !== '' && x != null);
    const moved = DQC.moved.has(`${r.table}:${r.id}`) ? ' <small>перенесена</small>' : '';
    return `<div class="dqc-row${r.problem ? ' dqc-row--problem' : ''}">
        <span style="flex:1">${parts.map(dqEsc).join(' · ')}${moved}</span>
        <details class="dqc-menu"><summary title="Действия со строкой" aria-label="Действия со строкой">⋯</summary>
            <div class="dqc-menu-body" data-table="${dqEsc(r.table)}" data-row="${Number(r.id)}">
                <button class="km-btn km-btn--secondary" onclick="dqcRowAction(this, 'move')">Перенести на…</button>
                <button class="km-btn km-btn--secondary" onclick="dqcRowAction(this, 'new')">Новая карточка</button>
                <div class="dqc-menu-form"></div>
            </div>
        </details>
    </div>`;
}

function cardHtml(c) {
    const bd = c.birthday ? dqEsc(c.birthday) : 'ДР не указана';
    const rows = (c.rows || []).length ? c.rows.map(rowHtml).join('') : '<div class="dq-muted">Нет заявок и результатов</div>';
    return `<div class="dqc-card" data-card="${Number(c.id)}">
        <div class="dqc-card-title"><span>${dqEsc(c.surname)} ${dqEsc(c.name)} · ${bd}</span>
            <details class="dqc-menu"><summary title="Действия с карточкой" aria-label="Действия с карточкой">⋯</summary>
                <div class="dqc-menu-body" data-card="${Number(c.id)}">
                    <button class="km-btn km-btn--secondary" onclick="dqcMenu(this, 'merge')">Склеить с…</button>
                    <button class="km-btn km-btn--secondary" onclick="dqcMenu(this, 'edit')">Исправить ФИО/ДР</button>
                    <div class="dqc-menu-form"></div>
                </div>
            </details>
        </div>
        ${rows}
    </div>`;
}

function doneHtml(key) {
    return (DQC.done[key] || []).map((d, i) => `<div class="dqc-done">✓ ${dqEsc(d.text)}${d.ids.length
        ? ` · <button class="km-btn km-btn--secondary" data-ids="${d.ids.map(Number).join(',')}" data-key="${dqEsc(key)}" data-done="${i}" onclick="dqcUndo(this)">Отменить</button>`
        : ''}</div>`).join('');
}

function caseHtml(c) {
    const qs = c.questions || [];
    const titles = c.stage_titles || {};
    const current = qs.find(q => q.state === 'current');
    const after = current ? titles[current.stage] : '';     // серые вопросы ждут ступень текущего
    const open = qs.some(q => q.state === 'current' || q.state === 'locked');
    const postpone = open ? `<div class="dq-actions">
            <input class="admin-select" id="dqc-reason" value="не знаю ДР" placeholder="Причина" aria-label="Причина, почему дело откладывается">
            <button class="km-btn km-btn--secondary" onclick="dqcPostpone(this)">Отложить дело</button></div>` : '';
    const questions = qs.length
        ? qs.map((q, qi) => questionHtml(q, qi, { after })).join('')
        : '<div class="dq-muted">Вопросов нет</div>';
    return `<div class="dqc-head">
            <button class="km-btn km-btn--secondary dqc-back" onclick="dqcBack()">← К списку</button>
            <h3 style="margin:0">${dqEsc(c.title)}</h3>
            <button class="km-btn km-btn--secondary" onclick="dqcNext()">Следующее дело →</button>
        </div>
        <div class="dqc-cards">${(c.cards || []).map(cardHtml).join('')}</div>
        ${doneHtml(c.key)}
        ${questions}
        ${postpone}`;
}

globalThis.dqcTest = { esc: dqEsc, categoriesFor, answerBody, defaultAnswer, questionHtml, cardHtml, outsideClick: dqcOutsideClick };

// ---- Экран ----

function dqcEl(id) { return document.getElementById(id); }

function dqcSay(text, ok) {
    const el = dqcEl('dqc-status');
    if (!el) return;
    el.textContent = text || '';
    el.style.color = ok ? '#155724' : '';
}

// Опасная кнопка: первое нажатие спрашивает, второе выполняет
function dqcArmed(btn, question) {
    if (btn.dataset.armed) return true;
    btn.dataset.armed = '1';
    btn.dataset.label = btn.textContent;
    btn.textContent = question;
    setTimeout(() => {
        if (btn.isConnected && btn.dataset.armed) { delete btn.dataset.armed; btn.textContent = btn.dataset.label; }
    }, 5000);
    return false;
}

function dqcInit() {
    if (DQC.inited) { dqcRenderQueue(); return; }
    DQC.inited = true;
    document.addEventListener('click', dqcOutsideClick);
    dqcLoadQueue();
}

// Клик мимо закрывает список поиска и раскрытые меню «⋯» (открытие одного меню закрывает остальные).
// Цель, которую обработчик клика уже убрал со страницы («Выбрать» → форма склейки), — не «мимо».
function dqcOutsideClick(e) {
    if (!e.target.isConnected) return;
    const box = dqcEl('dqc-search-list');
    if (box && !e.target.closest('.dqc-search')) box.hidden = true;
    document.querySelectorAll('details.dqc-menu[open]').forEach(d => { if (!d.contains(e.target)) d.open = false; });
}

async function dqcLoadQueue() {
    const seq = ++DQC.qseq;
    const queue = dqcEl('dqc-queue');
    if (!DQC.lists) queue.innerHTML = '<div class="admin-loading">Собираю очередь… (до 10 секунд)</div>';
    try {
        const [open, postponed] = await Promise.all(['open', 'postponed'].map(s => dqcRequest(`${DQC_API}/cases?status=${s}`)));
        if (seq !== DQC.qseq) return;
        const alive = c => !DQC.gone.has(c.key);
        DQC.lists = { open: open.cases.filter(alive), postponed: postponed.cases.filter(alive) };
        if (!DQC.eventsFilled) dqcFillEvents();
        dqcRenderQueue();
    } catch (e) {
        if (seq === DQC.qseq) queue.innerHTML = `<div class="admin-error">Не удалось собрать очередь: ${dqEsc(e.message)}</div>`;
    }
}

function dqcFillEvents() {
    DQC.eventsFilled = true;
    const sel = dqcEl('dqc-event');
    const events = [...new Set([...DQC.lists.open, ...DQC.lists.postponed].flatMap(c => c.events || []))]
        .sort((a, b) => a.localeCompare(b, 'ru'));
    sel.innerHTML = '<option value="">Все забеги</option>' + events.map(e => `<option value="${dqEsc(e)}">${dqEsc(e)}</option>`).join('');
    if (typeof adminRestoreValue === 'function') adminRestoreValue('dqc-event');
}

function dqcFiltered(list) {
    const ev = dqcEl('dqc-event').value;
    return list.filter(c => !DQC.gone.has(c.key) && (!ev || (c.events || []).includes(ev)));
}

function dqcRenderQueue() {
    if (!DQC.lists) return;
    ['open', 'postponed'].forEach(s => { dqcEl(`dqc-n-${s}`).textContent = `· ${dqcFiltered(DQC.lists[s]).length}`; });
    if (DQC.tab === 'journal') return;
    DQC.cases = dqcFiltered(DQC.lists[DQC.tab]);
    dqcEl('dqc-queue').innerHTML = DQC.cases.length ? DQC.cases.map(c => `<button class="dqc-qitem${c.key === DQC.key ? ' dqc-qitem--on' : ''}"
            data-key="${dqEsc(c.key)}" onclick="dqcOpen(this.dataset.key, [])">
            <b>${dqEsc(c.title)}</b>
            <small>карточек ${Number(c.cards)} · вопросов ${Number(c.questions_left)}</small>
            ${(c.events || []).length ? `<small>${c.events.map(dqEsc).join('; ')}</small>` : ''}
        </button>`).join('')
        : `<div class="admin-loading">${DQC.tab === 'open' ? 'Дел нет — всё сходится' : 'Отложенных дел нет'}</div>`;
}

// Дело закрыто — убрать из очереди без полного пересчёта очереди на сервере; ключ помнится закрытым
function dqcDropFromQueue(key) {
    DQC.gone.add(key);
    if (!DQC.lists) return;
    const i = DQC.cases.findIndex(c => c.key === key);
    if (i >= 0) DQC.pos = i;
    ['open', 'postponed'].forEach(s => { DQC.lists[s] = DQC.lists[s].filter(c => c.key !== key); });
    dqcRenderQueue();
}

function dqcTab(name) {
    DQC.tab = name;
    document.querySelectorAll('.dqc-tab').forEach(b => {
        b.classList.toggle('dqc-tab--on', b.dataset.tab === name);
        b.setAttribute('aria-selected', String(b.dataset.tab === name));
    });
    const journal = name === 'journal';
    dqcEl('dqc-layout').hidden = journal;
    dqcEl('dqc-journal').hidden = !journal;
    dqcBack();                                  // телефон: сначала список
    if (journal) dqcLoadJournal();
    else dqcRenderQueue();
}

function dqcFetchCase(key) {
    const p = DQC.person && DQC.person.key === key ? DQC.person.id : (/^p(\d+)$/.exec(key) || [])[1];
    return dqcRequest(p ? `${DQC_API}/person/${Number(p)}` : `${DQC_API}/cases/${encodeURIComponent(key)}`);
}

// Ключ дела сменился после действия в нём (склейка убрала наименьшую карточку) — решённое этого дела переезжает
function dqcRekey(fromKey, toKey) {
    if (!fromKey || fromKey === toKey) return;
    if (DQC.done[fromKey]) {
        DQC.done[toKey] = [...(DQC.done[toKey] || []), ...DQC.done[fromKey]];
        delete DQC.done[fromKey];
    }
    if (DQC.person && DQC.person.key === fromKey) DQC.person.key = toKey;
    if (DQC.key === fromKey) DQC.key = toKey;
}

// Дело на экране; fromKey — ключ дела, действием в котором получено c (не задан — просто открыто другое дело)
function dqcShowCase(c, fromKey) {
    dqcRekey(fromKey, c.key);
    DQC.key = c.key;
    DQC.caseData = c;
    dqcEl('dqc-case').innerHTML = caseHtml(c);
    dqcEl('dqc-layout').classList.add('dqc-layout--case');
    dqcSyncQueue(fromKey, c);
}

// Дело после действия в деле key: открыто оно же — перерисовать, открыто другое — только пункт очереди
function dqcCaseResult(key, c) {
    if (!c) {
        if (DQC.key === key) dqcClosed(key);
        else dqcDropFromQueue(key);
        return;
    }
    if (DQC.key === key) dqcShowCase(c, key);
    else { dqcRekey(key, c.key); dqcSyncQueue(key, c); }
}

// Пункт очереди по свежему делу: ключ, число карточек и вопросов; все вопросы отложены — во «Отложено», и обратно;
// дела нет в очереди (вернулось отменой) — пункт добавляется
function dqcSyncQueue(oldKey, c) {
    const qs = c.questions || [];
    if (DQC.lists && qs.length) {
        DQC.gone.delete(c.key);
        const to = qs.some(q => q.state !== 'postponed') ? 'open' : 'postponed';
        const left = qs.filter(q => q.state !== 'postponed').length || qs.length;
        let found = false;
        ['open', 'postponed'].forEach(s => {
            const list = DQC.lists[s];
            const i = list.findIndex(x => x.key === c.key || (oldKey && x.key === oldKey));
            if (i < 0) return;
            found = true;
            const item = { ...list[i], key: c.key, cards: (c.cards || []).length, questions_left: left };
            if (s === to) { list[i] = item; return; }
            const j = DQC.cases.indexOf(list[i]);
            if (j >= 0) DQC.pos = j;                   // «Следующее дело →» — с того же места списка
            list.splice(i, 1);
            DQC.lists[to].push(item);
        });
        if (!found && !/^p\d+$/.test(c.key)) {
            DQC.lists[to].push({ key: c.key, title: c.title, cards: (c.cards || []).length, questions_left: left,
                                 events: [...new Set((c.cards || []).flatMap(k => (k.rows || []).filter(r => r.problem).map(r => r.event)))] });
        }
    }
    dqcRenderQueue();
}

async function dqcOpen(key, extraCards) {
    const seq = ++DQC.seq;
    if (extraCards !== undefined) {           // открыто из очереди — новое дело
        DQC.extra = extraCards;
        DQC.person = null;
    }
    const box = dqcEl('dqc-case');
    if (key !== DQC.key) {
        DQC.key = key;
        DQC.caseData = null;
        box.innerHTML = '<div class="admin-loading">Открываю дело…</div>';
        dqcEl('dqc-layout').classList.add('dqc-layout--case');
    }
    try {
        const c = await dqcFetchCase(key);
        if (seq === DQC.seq) dqcShowCase(c);
    } catch (e) {
        if (seq !== DQC.seq) return;
        const back = '<button class="km-btn km-btn--secondary dqc-back" onclick="dqcBack()">← К списку</button>';
        if (e.status === 404) {
            dqcSay('Дело уже закрыто');
            DQC.caseData = null;
            box.innerHTML = `${back}<div class="admin-loading">Дело закрыто</div>`;
            dqcDropFromQueue(key);
        } else {
            box.innerHTML = `${back}<div class="admin-error">Не удалось открыть дело: ${dqEsc(e.message)}</div>`;
        }
    }
}

function dqcBack() {
    dqcEl('dqc-layout').classList.remove('dqc-layout--case');
}

function dqcNext() {
    const i = DQC.cases.findIndex(c => c.key === DQC.key);
    const next = i >= 0 ? DQC.cases[i + 1] : DQC.cases[Math.min(DQC.pos, DQC.cases.length - 1)];
    if (!next) { dqcSay('Это было последнее дело в списке'); return; }
    dqcOpen(next.key, []);
}

// ---- Вопросы ----

function dqcQuestion(qi) { return DQC.caseData.questions[qi]; }

function dqcPick(qi) {
    const q = dqcQuestion(qi);
    const picked = document.querySelector(`input[name="dqc-a-${qi}"]:checked`);
    q.answers.forEach((a, ai) => {
        const box = dqcEl(`dqc-in-${qi}-${ai}`);
        if (box) box.hidden = !picked || Number(picked.dataset.ai) !== ai;
    });
    const lead = dqcEl(`dqc-lead-${qi}`);
    if (lead) lead.hidden = !picked || !isLeadEdit(q, picked.value);
}

function dqcSexChanged(qi, ai) {
    const box = dqcEl(`dqc-in-${qi}-${ai}`);
    const inp = dqcQuestion(qi).answers[ai].inputs.find(isCategoryInput);
    const sel = box && box.querySelector('[data-name="category"]');
    if (!inp || !sel) return;
    sel.innerHTML = selectOptionsHtml(inp, box.querySelector('[data-name="sex"]').value, sel.value);
}

function dqcValues(qi, ai) {
    const values = {};
    const box = dqcEl(`dqc-in-${qi}-${ai}`);
    if (box) box.querySelectorAll('[data-name]').forEach(el => { values[el.dataset.name] = el.value.trim(); });
    return values;
}

function dqcRecord(key, text, ids) {
    (DQC.done[key] = DQC.done[key] || []).push({ text, ids: (ids || []).filter(Boolean) });
}

function dqcClosed(key) {
    DQC.caseData = null;
    dqcEl('dqc-case').innerHTML = `<div class="dqc-head">
            <button class="km-btn km-btn--secondary dqc-back" onclick="dqcBack()">← К списку</button>
            <h3 style="margin:0">Дело закрыто ✓</h3>
            <button class="km-btn km-btn--primary" onclick="dqcNext()">Следующее дело →</button>
        </div>${doneHtml(key)}`;
    dqcDropFromQueue(key);
}

// statusId — куда писать ход и ошибку: под «Применить» или в блоке конфликта
async function dqcSendAnswer(qi, body, text, btn, statusId) {
    const key = DQC.key;
    const st = dqcEl(statusId || `dqc-st-${qi}`);
    btn.disabled = true;
    if (st) st.textContent = 'Выполняю…';
    try {
        const r = await dqcRequest(`${DQC_API}/cases/${encodeURIComponent(key)}/answer`, body);
        if (r.conflict) {
            if (DQC.key !== key) return;            // открыто другое дело — ничего не записано, показывать некуда
            btn.disabled = false;
            if (st) st.textContent = '';
            DQC.conflict = { key, qi, conflict: r.conflict };
            dqcEl(`dqc-conf-${qi}`).innerHTML = `<div class="dqc-conflict">${dqEsc(r.conflict.message)}
                <div class="dq-actions"><button class="km-btn km-btn--primary" onclick="dqcMergeConflict(${qi}, this)">Склеить</button>
                <span class="dq-status" id="dqc-cst-${qi}"></span></div></div>`;
            return;
        }
        dqcRecord(key, text, r.action_ids);
        dqcSay(r.error ? `Записано частично: ${r.error}` : DQC_SITE_NOTE, !r.error);
        dqcCaseResult(key, r.case);
    } catch (e) {
        btn.disabled = false;
        if (DQC.key !== key) { dqcSay(`Ответ в другом деле не выполнен: ${e.message}`); return; }
        if (e.status === 409) {
            dqcSay('Дело изменилось — обновляю');
            dqcOpen(key);
        } else if (st) {
            st.textContent = e.message;
        }
    }
}

function dqcApply(qi, btn) {
    const q = dqcQuestion(qi);
    const picked = document.querySelector(`input[name="dqc-a-${qi}"]:checked`);
    const st = dqcEl(`dqc-st-${qi}`);
    if (!picked) { st.textContent = 'Выберите ответ'; return; }
    const ai = Number(picked.dataset.ai);
    const a = q.answers[ai];
    const values = dqcValues(qi, ai);
    if (a.inputs.some(isCategoryInput) && !values.category) { st.textContent = 'Выберите категорию'; return; }
    const shown = a.inputs.map(i => values[i.name]).filter(Boolean).join(' ');
    const body = answerBody(q, a.id, values, DQC.extra);
    const reason = dqcEl('dqc-reason');
    if (a.id === 'postpone' && reason && reason.value.trim()) body.inputs.reason = reason.value.trim();
    dqcSendAnswer(qi, body, shown ? `${a.label}: ${shown}` : a.label, btn);
}

function dqcMergeConflict(qi, btn) {
    const k = DQC.conflict;
    if (!k || k.qi !== qi || k.key !== DQC.key) return;
    const c = k.conflict;
    const q = dqcQuestion(qi);
    const body = { question_id: q.id, answer_id: `merge_with:${Number(c.merge_with)}`,
                   inputs: { surname: c.surname, name: c.name, birthday: c.birthday }, extra_cards: DQC.extra };
    dqcSendAnswer(qi, body, `Склеено с карточкой ${c.surname} ${c.name} ${c.birthday}`, btn, `dqc-cst-${qi}`);
}

async function dqcPostpone(btn) {
    const key = DQC.key;
    const reason = (dqcEl('dqc-reason').value || '').trim() || 'не знаю ДР';
    btn.disabled = true;
    try {
        const r = await dqcRequest(`${DQC_API}/cases/${encodeURIComponent(key)}/postpone`, { reason });
        dqcRecord(key, `Дело отложено: ${reason}`, r.action_ids);
        dqcSay('Дело отложено — оно во вкладке «Отложено»', true);
        if (DQC.key === key) dqcOpen(key);
    } catch (e) {
        btn.disabled = false;
        if (DQC.key !== key) return;
        if (e.status === 409) { dqcSay('Дело изменилось — обновляю'); dqcOpen(key); }
        else dqcSay(e.message);
    }
}

// ---- Отмена (строка «✓ … · Отменить» и журнал) ----

async function dqcUndo(btn) {
    if (!dqcArmed(btn, 'Точно отменить?')) return;
    const ids = btn.dataset.ids.split(',').map(Number).filter(Boolean).reverse();   // позднее — первым
    const key = btn.dataset.key;                                // строка «✓ …» — дело, к которому она относится
    const entry = key !== undefined ? (DQC.done[key] || [])[Number(btn.dataset.done)] : null;
    const undone = [];
    btn.disabled = true;
    try {
        for (const id of ids) {
            await dqcRequest(`${DQC_API}/undo`, { action_id: id });
            undone.push(id);
        }
        dqcSay(`Отменено. ${DQC_SITE_NOTE}`, true);
        if (entry) DQC.done[key].splice(DQC.done[key].indexOf(entry), 1);
        if (key !== undefined) DQC.gone.delete(key);            // закрытое дело вернулось
        if (DQC.tab === 'journal') dqcLoadJournal();
        if (DQC.key) dqcOpen(DQC.key);                          // дело и его пункт очереди — по свежим данным
        if (key === undefined) dqcLoadQueue();                  // из журнала: какое дело вернулось — неизвестно
    } catch (e) {
        // частичная отмена: отменённое не предлагать снова
        const left = ids.filter(id => !undone.includes(id)).reverse();
        btn.dataset.ids = left.join(',');
        if (entry) entry.ids = left;
        btn.disabled = false;
        delete btn.dataset.armed;
        btn.textContent = btn.dataset.label || 'Отменить';
        dqcSay(`Не удалось отменить${undone.length ? ' до конца' : ''}: ${e.message}`);
    }
}

async function dqcLoadJournal() {
    const box = dqcEl('dqc-journal');
    if (!box.innerHTML.trim()) box.innerHTML = '<div class="admin-loading">Загрузка…</div>';
    try {
        const { actions } = await dqcRequest(`${DQC_API}/actions?limit=50`);
        box.innerHTML = actions.length ? actions.map(a => {
            const state = a.undone ? '<span class="dq-muted">отменено</span>'
                : a.can_undo ? `<button class="km-btn km-btn--secondary" data-ids="${Number(a.id)}" onclick="dqcUndo(this)">Отменить</button>`
                : `<span class="dq-muted">нельзя отменить: ${dqEsc(a.why_not)}</span>`;
            return `<div class="dq-journal-row${a.undone ? ' dq-journal-row--undone' : ''}">
                <span class="dq-muted">${dqEsc(a.done_at)} · ${dqEsc(a.done_by)}</span>
                <span class="dq-journal-text">${dqEsc(a.text)}</span>${state}</div>`;
        }).join('') : '<div class="admin-loading">Действий пока нет</div>';
    } catch (e) {
        box.innerHTML = `<div class="admin-error">Ошибка: ${dqEsc(e.message)}</div>`;
    }
}

async function dqcApplyAuto(btn) {
    if (!dqcArmed(btn, 'Точно применить очевидное?')) return;
    btn.disabled = true;
    dqcSay('Применяю очевидное…');
    try {
        const r = await dqcRequest(`${DQC_API}/apply-auto`, {});
        dqcSay(`Удалено результатов: ${r.deleted.length}, склеено групп: ${r.merged.length}`
            + (r.skipped.length ? `, пропущено: ${r.skipped.length}` : '') + `. ${DQC_SITE_NOTE}`, true);
        dqcLoadQueue();
        if (DQC.key) dqcOpen(DQC.key);
    } catch (e) {
        dqcSay(`Ошибка: ${e.message}`);
    } finally {
        btn.disabled = false;
        delete btn.dataset.armed;
        btn.textContent = btn.dataset.label || 'Применить очевидное';
    }
}

// ---- Поиск человека ----

function dqcCardLine(c) {
    return `<b>${dqEsc(c.surname)} ${dqEsc(c.name)}</b>, ${c.birthday ? dqEsc(c.birthday) : 'ДР не указана'}
        <small class="dq-muted" style="display:block">${dqEsc((c.events || []).join('; ') || 'без забегов')}</small>`;
}

// Поиск карточек с задержкой 300 мс; ответ на устаревший ввод не показывается
function dqcFindCards(timerKey, input, list, render) {
    clearTimeout(DQC.timers[timerKey]);
    DQC.timers[timerKey] = setTimeout(async () => {
        const q = input.value.trim();
        if (q.length < 2) { list.innerHTML = ''; list.hidden = true; return; }
        list.hidden = false;
        list.innerHTML = '<div class="dq-muted" style="padding:8px">Поиск…</div>';
        try {
            const { cards } = await dqcRequest(`${DQC_API}/cards?q=${encodeURIComponent(q)}`);
            if (input.value.trim() !== q) return;
            list.innerHTML = cards.length ? cards.map(render).join('') : '<div class="dq-muted" style="padding:8px">Ничего не найдено</div>';
        } catch (e) {
            list.innerHTML = `<div class="dq-status" style="padding:8px">${dqEsc(e.message)}</div>`;
        }
    }, 300);
}

function dqcSearch() {
    dqcFindCards('search', dqcEl('dqc-q'), dqcEl('dqc-search-list'), c =>
        `<button class="dqc-search-item" data-id="${Number(c.id)}" onclick="dqcOpenPerson(Number(this.dataset.id))">${dqcCardLine(c)}</button>`);
}

async function dqcOpenPerson(id) {
    const seq = ++DQC.seq;
    dqcEl('dqc-search-list').hidden = true;
    DQC.extra = [id];
    DQC.key = `p${id}`;                 // до ответа: действия прежнего дела не перерисуют экран
    DQC.caseData = null;
    DQC.person = null;
    const box = dqcEl('dqc-case');
    box.innerHTML = '<div class="admin-loading">Открываю дело…</div>';
    dqcEl('dqc-layout').classList.add('dqc-layout--case');
    try {
        const c = await dqcRequest(`${DQC_API}/person/${Number(id)}`);
        if (seq !== DQC.seq) return;
        DQC.person = { id, key: c.key };
        dqcShowCase(c);
    } catch (e) {
        if (seq !== DQC.seq) return;
        box.innerHTML = `<button class="km-btn km-btn--secondary dqc-back" onclick="dqcBack()">← К списку</button>
            <div class="admin-error">Не удалось открыть: ${dqEsc(e.message)}</div>`;
    }
}

// ---- Ручные действия «⋯» ----

function dqcCaseCard(cid) {
    return ((DQC.caseData || {}).cards || []).find(c => c.id === cid) || {};
}

function dqcFioForm(c, button, onclick) {
    return `<div class="dqc-answer-inputs" style="margin-left:0">
            <label>Фамилия<input class="admin-select" data-f="surname" value="${dqEsc(c.surname)}"></label>
            <label>Имя<input class="admin-select" data-f="name" value="${dqEsc(c.name)}"></label>
            <label>ДР<input class="admin-select" data-f="birthday" value="${dqEsc(c.birthday)}" placeholder="ГГГГ-ММ-ДД"></label>
        </div>
        <div class="dq-actions"><button class="km-btn km-btn--primary" onclick="${onclick}">${button}</button>
            <span class="dq-status"></span></div>`;
}

function dqcFio(box) {
    const v = {};
    box.querySelectorAll('[data-f]').forEach(el => { v[el.dataset.f] = el.value.trim(); });
    return v;
}

function dqcSearchForm(timerKey, value, renderName) {
    return `<input class="admin-select" style="width:100%;margin-top:6px" placeholder="Поиск карточки: фамилия имя" value="${dqEsc(value)}"
            data-timer="${dqEsc(timerKey)}" oninput="dqcMenuSearch(this, '${renderName}')">
        <div class="dqc-menu-list" style="max-height:240px;overflow-y:auto"></div>`;
}

function dqcMenuSearch(input, mode) {
    const body = input.closest('.dqc-menu-body');
    const list = body.querySelector('.dqc-menu-list');
    list.hidden = false;
    dqcFindCards(input.dataset.timer, input, list, c => {
        const own = Number(body.closest('.dqc-card').dataset.card) === c.id;
        return `<div class="dqc-search-item" style="cursor:default">${dqcCardLine(c)}${own ? '<span class="dq-muted">текущая карточка</span>'
            : `<button class="km-btn km-btn--secondary" data-id="${Number(c.id)}" onclick="dqcPicked(this, '${mode}')">${mode === 'merge' ? 'Выбрать' : 'Сюда'}</button>`}</div>`;
    });
}

function dqcMenu(btn, kind) {
    const body = btn.closest('.dqc-menu-body');
    const c = dqcCaseCard(Number(body.dataset.card));
    const form = body.querySelector('.dqc-menu-form');
    form.innerHTML = kind === 'edit'
        ? dqcFioForm(c, 'Сохранить', 'dqcEditCard(this)')
        : dqcSearchForm(`merge-${c.id}`, c.surname, 'merge');
    if (kind === 'merge') dqcMenuSearch(form.querySelector('input'), 'merge');
}

function dqcRowAction(btn, kind) {
    const body = btn.closest('.dqc-menu-body');
    const card = dqcCaseCard(Number(btn.closest('.dqc-card').dataset.card));
    const form = body.querySelector('.dqc-menu-form');
    if (kind === 'new') {
        const row = (card.rows || []).find(r => r.table === body.dataset.table && r.id === Number(body.dataset.row)) || {};
        form.innerHTML = dqcFioForm({ surname: card.surname, name: card.name, birthday: row.birthday || '' },
            'Создать и перенести', 'dqcMoveNew(this)');
    } else {
        form.innerHTML = dqcSearchForm(`move-${body.dataset.table}-${body.dataset.row}`, card.surname, 'move');
        dqcMenuSearch(form.querySelector('input'), 'move');
    }
}

function dqcPicked(btn, mode) {
    const body = btn.closest('.dqc-menu-body');
    const other = Number(btn.dataset.id);
    if (mode === 'move') {
        if (!dqcArmed(btn, 'Точно сюда?')) return;
        dqcManual(btn, 'move', { table: body.dataset.table, row_id: Number(body.dataset.row), to_client_id: other },
            'Строка перенесена на другую карточку', other);
        return;
    }
    const c = dqcCaseCard(Number(body.dataset.card));
    body.dataset.other = other;
    body.querySelector('.dqc-menu-form').innerHTML = '<div class="dq-muted" style="margin-top:6px">Итоговые ФИО и ДР склеенной карточки:</div>'
        + dqcFioForm(c, 'Склеить', 'dqcMergeCards(this)');
}

function dqcMergeCards(btn) {
    const body = btn.closest('.dqc-menu-body');
    const fio = dqcFio(body);
    dqcManual(btn, 'merge', { client_ids: [Number(body.dataset.card), Number(body.dataset.other)], ...fio },
        `Карточки склеены: ${fio.surname} ${fio.name} ${fio.birthday}`, Number(body.dataset.other));
}

function dqcEditCard(btn) {
    const body = btn.closest('.dqc-menu-body');
    const cid = Number(body.dataset.card);
    const c = dqcCaseCard(cid);
    const fio = dqcFio(body);
    const fields = {};
    Object.entries(fio).forEach(([k, v]) => { if (v !== String(c[k] ?? '')) fields[k] = v; });
    if (!Object.keys(fields).length) { btn.parentElement.querySelector('.dq-status').textContent = 'Ничего не изменено'; return; }
    dqcManual(btn, 'edit', { table: 'clients', id: cid, fields }, `Карточка исправлена: ${Object.values(fields).join(' ')}`, null);
}

function dqcMoveNew(btn) {
    const body = btn.closest('.dqc-menu-body');
    const fio = dqcFio(body);
    if (!dqcArmed(btn, 'Точно создать?')) return;
    dqcManual(btn, 'move', { table: body.dataset.table, row_id: Number(body.dataset.row), new_card: fio },
        `Строка перенесена на новую карточку ${fio.surname} ${fio.name} ${fio.birthday}`, null);
}

// Ручное действие → запись «✓ … · Отменить», дело перечитывается (с карточкой, куда ушла строка)
async function dqcManual(btn, action, body, text, otherCard) {
    const key = DQC.key;
    const st = btn.parentElement.querySelector('.dq-status') || btn.closest('.dqc-menu-body').querySelector('.dq-status');
    btn.disabled = true;
    let r;
    try {
        r = await dqcRequest(`${DQC_API}/${action}`, { ...body, key: key || '' });
    } catch (e) {
        btn.disabled = false;
        if (DQC.key !== key) dqcSay(`Действие в другом деле не выполнено: ${e.message}`);
        else if (st) st.textContent = e.message;
        else dqcSay(e.message);
        return;
    }
    if (action === 'move') DQC.moved.add(`${body.table}:${body.row_id}`);
    dqcRecord(key, text, [r.action_id]);
    dqcSay(DQC_SITE_NOTE, true);
    if (DQC.key !== key) return;                     // открыто другое дело — его не трогаем
    const target = r.client_id || otherCard;
    if (target && !DQC.extra.includes(target)) DQC.extra.push(target);
    try {
        await dqcReopen(key, target);
    } catch (e) {
        if (DQC.key === key) dqcSay(`Выполнено, но дело не перечитано: ${e.message}`);
    }
}

// Дело key после ручного действия; ключ пропал (склейка/перенос) — дело карточки, на которую ушли данные
async function dqcReopen(key, cid) {
    const seq = ++DQC.seq;
    let c;
    try {
        c = await dqcFetchCase(key);
    } catch (e) {
        if (e.status !== 404 || !cid) throw e;
        c = await dqcRequest(`${DQC_API}/person/${Number(cid)}`);
        if (seq === DQC.seq) DQC.person = { id: cid, key: c.key };
    }
    if (seq === DQC.seq) dqcShowCase(c, key);
}
