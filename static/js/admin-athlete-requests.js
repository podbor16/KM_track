// static/js/admin-athlete-requests.js
// Вкладка /admin → «Обращения»: обращения личного кабинета (спор, «не мой забег», «не могу найти себя»).
// API — src/krasmarafon/routers/admin.py (/api/admin/athlete-requests). Данные вставляются только через textContent.

const AR_KINDS = {
    dispute: 'Спор: «это моя карточка»',
    wrong_row: 'Это не мой забег',
    not_found: 'Не могу найти себя',
};
const AR_ACTIONS = { dispute: ['transfer', 'reject'], wrong_row: ['close'], not_found: ['close', 'attach'] };
const AR_BUTTONS = { transfer: 'Передать заявителю', reject: 'Отклонить', close: 'Закрыть', attach: 'Привязать' };
const AR_RESOLUTIONS = { transfer: 'Передано заявителю', attach: 'Карточка привязана', reject: 'Отклонено', close: 'Закрыто' };
const AR_PAYLOAD_KEYS = { surname: 'Фамилия', name: 'Имя', birthday: 'Дата рождения', bib: 'Номер' };
const AR_ROWS = { results: 'Результат', leads: 'Заявка' };
const AR_ERRORS = {
    closed: 'Обращение уже рассмотрено', not_found: 'Обращения нет', bad_action: 'Это действие не подходит к обращению',
    no_card: 'Карточка не найдена: укажите её номер', taken: 'Карточка уже привязана к другому аккаунту',
    no_birthday: 'У карточки нет даты рождения',
    other_person: 'У заявителя уже есть своя карточка с другой датой рождения — это другой человек (можно выдать доступ представителя через кабинет)',
};
const AR = { status: 'new', seq: 0 };

function arKindLabel(kind) { return AR_KINDS[kind] || kind; }
function arActionsFor(kind) { return AR_ACTIONS[kind] || ['close']; }
function arResolutionLabel(r) { return AR_RESOLUTIONS[r] || r || ''; }
function arRowLabel(table, id) { return table && id ? `${AR_ROWS[table] || table} №${id}` : ''; }
function arErrorText(code) { return AR_ERRORS[code] || `Ошибка: ${code}`; }
function arPayloadLines(payload) {
    if (!payload) return [];
    const keys = Object.keys(payload).filter(k => payload[k] !== '' && payload[k] != null);
    const known = Object.keys(AR_PAYLOAD_KEYS).filter(k => keys.includes(k));
    return known.concat(keys.filter(k => !known.includes(k))).map(k => `${AR_PAYLOAD_KEYS[k] || k}: ${payload[k]}`);
}

function arEl(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
}

function arOpenCard(id) {
    switchTab('data-quality', document.querySelector(`.admin-tab[onclick*="'data-quality'"]`));
    dqcOpenPerson(id);
}

async function arCall(url, body) {
    const r = await fetch(url, {
        method: body === undefined ? 'GET' : 'POST',
        headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${r.status}`);
    return data;
}

async function arRefreshCount() {
    const n = document.getElementById('ar-count');
    if (!n) return;
    try { n.textContent = `(${(await arCall('/api/admin/athlete-requests/count')).count})`; }
    catch (e) { console.error('arRefreshCount error:', e); }
}

function arSetStatus(s) {
    AR.status = s;
    document.querySelectorAll('#tab-requests .dqc-tab').forEach(b => {
        const on = b.dataset.status === s;
        b.classList.toggle('dqc-tab--on', on);
        b.setAttribute('aria-selected', String(on));
    });
    arLoad();
}

async function arLoad() {
    const box = document.getElementById('ar-list');
    const seq = ++AR.seq;
    box.replaceChildren(arEl('div', 'admin-loading', 'Загрузка…'));
    arRefreshCount();
    try {
        const data = await arCall('/api/admin/athlete-requests?status=' + encodeURIComponent(AR.status));
        if (seq !== AR.seq) return;
        box.replaceChildren();
        if (!data.requests.length) box.appendChild(arEl('div', 'dqc-status', AR.status === 'new' ? 'Новых обращений нет' : 'Закрытых обращений нет'));
        data.requests.forEach(r => box.appendChild(arRender(r)));
    } catch (e) {
        if (seq === AR.seq) box.replaceChildren(arEl('div', 'dqc-status', 'Не удалось загрузить'));
        console.error('arLoad error:', e);
    }
}

function arStamp(v) { return String(v || '').replace('T', ' ').slice(0, 16); }

function arRender(r) {
    const card = arEl('div', 'dqc-card ar-card');
    const title = arEl('div', 'dqc-card-title');
    title.append(arEl('span', null, arKindLabel(r.kind)), arEl('small', null, arStamp(r.created_at)));
    card.appendChild(title);
    card.appendChild(arEl('div', null, 'Почта: ' + r.email));
    if (r.client_id) {
        const line = arEl('div', null, 'Карточка: ');
        const link = arEl('a', null, `№${r.client_id}${r.card ? ' ' + r.card : ''}`);
        link.href = '#';
        link.addEventListener('click', ev => { ev.preventDefault(); arOpenCard(r.client_id); });
        line.appendChild(link);
        card.appendChild(line);
    }
    const row = arRowLabel(r.row_table, r.row_id);
    if (row) card.appendChild(arEl('div', null, 'Строка: ' + row));
    arPayloadLines(r.payload).forEach(t => card.appendChild(arEl('div', null, t)));
    if (r.comment) card.appendChild(arEl('div', 'ar-comment', 'Комментарий: ' + r.comment));
    if (r.status !== 'new') {
        card.appendChild(arEl('div', null, `${arResolutionLabel(r.resolution)} · ${r.resolved_by || ''} · ${arStamp(r.resolved_at)}`));
        if (r.answer) card.appendChild(arEl('div', 'ar-comment', 'Ответ: ' + r.answer));
        return card;
    }
    const answer = arEl('textarea', 'admin-select ar-answer');
    answer.rows = 2; answer.maxLength = 1000; answer.placeholder = 'Ответ заявителю (необязательно)';
    answer.setAttribute('aria-label', 'Ответ заявителю');
    const cardNo = arEl('input', 'admin-select ar-cardno');
    cardNo.type = 'number'; cardNo.min = '1'; cardNo.placeholder = '№ карточки';
    cardNo.setAttribute('aria-label', '№ карточки для привязки');
    const status = arEl('div', 'dqc-status');
    status.setAttribute('aria-live', 'polite');
    const bar = arEl('div', 'dqc-toolbar');
    card.appendChild(answer);
    arActionsFor(r.kind).forEach(action => {
        if (action === 'attach') bar.appendChild(cardNo);
        const btn = arEl('button', action === 'reject' || action === 'close' ? 'km-btn km-btn--secondary' : 'km-btn', AR_BUTTONS[action]);
        btn.addEventListener('click', async () => {
            if (action === 'transfer' && !confirm('Передать карточку заявителю? Прежний владелец потеряет привязку и получит письмо.')) return;
            const body = { action, answer: answer.value.trim() };
            if (action === 'attach') body.client_id = Number(cardNo.value) || null;
            bar.querySelectorAll('button').forEach(b => { b.disabled = true; });
            try {
                await arCall(`/api/admin/athlete-requests/${Number(r.id)}/resolve`, body);
                arLoad();
            } catch (e) {
                status.textContent = arErrorText(e.message);
                bar.querySelectorAll('button').forEach(b => { b.disabled = false; });
            }
        });
        bar.appendChild(btn);
    });
    card.append(bar, status);
    return card;
}

globalThis.arTest = { kindLabel: arKindLabel, actionsFor: arActionsFor, payloadLines: arPayloadLines, rowLabel: arRowLabel,
    resolutionLabel: arResolutionLabel, errorText: arErrorText };
