// static/js/admin-state.js
// /admin: после F5, «Обновить» и сохранений пользователь остаётся там же (решение 2026-10-05):
//   - вкладка и фильтры — в адресе (?tab=leads&event=…&year=…) — ссылкой можно поделиться;
//   - фильтры каждой вкладки, прокрутка, число подгруженных заявок — в браузере (localStorage);
//   - несохранённый ввод (поля с data-draft) — черновик, очищается после успешного сохранения.
// Фильтры с подгружаемыми вариантами (мероприятие → год → дистанция) восстанавливают сами
// загрузчики вкладок: adminRestoreValue(id) — когда варианты уже в списке.

const ADMIN_STATE_KEY = 'krasmarafon_admin_state';
const ADMIN_LEGACY_TAB_KEY = 'krasmarafon_admin_active_tab';

// id поля → имя параметра в адресе
const ADMIN_TAB_FIELDS = {
    leads: {
        'leads-event-name': 'event', 'leads-year-filter': 'year', 'leads-distance-filter': 'distance',
        'leads-dup-filter': 'dup', 'leads-suspicious-filter': 'suspicious', 'leads-search': 'q',
    },
    'age-groups': { 'ag-event-name': 'event', 'ag-distance': 'distance' },
    photos: { 'ph-event': 'event' },
    broadcast: { 'bcp-distance': 'distance', 'bcp-checkpoint': 'checkpoint' },
    monitoring: { 'mon-range': 'range' },
    'data-quality': { 'dq-event': 'event', 'dq-severity': 'severity' },
};

// варианты этих списков приходят с сервера — восстанавливают загрузчики вкладок
const ADMIN_LOADED_FIELDS = new Set([
    'leads-event-name', 'leads-year-filter', 'leads-distance-filter', 'ag-event-name', 'ag-distance',
    'ph-event', 'bcp-checkpoint', 'dq-event',
]);

const adminState = (() => {
    let s = {};
    try { s = JSON.parse(localStorage.getItem(ADMIN_STATE_KEY)) || {}; } catch (e) { /* приватный режим */ }
    return { tab: s.tab || null, filters: s.filters || {}, scroll: s.scroll || {}, drafts: s.drafts || {}, extra: s.extra || {} };
})();
const adminPending = {};          // id → значение, ждущее своих вариантов в списке
let adminScrollRestoring = false;

function adminPersist() {
    try { localStorage.setItem(ADMIN_STATE_KEY, JSON.stringify(adminState)); } catch (e) { /* квота/приватный режим */ }
}

function adminFieldValue(el) {
    return el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value;
}

function adminSetField(el, value) {
    if (el.type === 'checkbox') { el.checked = value === '1'; return true; }
    if (el.tagName === 'SELECT' && ![...el.options].some(o => o.value === value)) return false;
    el.value = value;
    return true;
}

function adminTabOf(id) {
    return Object.keys(ADMIN_TAB_FIELDS).find(tab => id in ADMIN_TAB_FIELDS[tab]) || null;
}

// Вернуть сохранённое значение полю, если оно ждёт восстановления. true — значение выставлено.
// Сохранённое значение используется один раз: дальше поле живёт обычной жизнью.
function adminRestoreValue(id) {
    if (!(id in adminPending)) return false;
    const value = adminPending[id];
    delete adminPending[id];
    const el = document.getElementById(id);
    return !!el && adminSetField(el, value);
}

function adminSaveFilters(tab) {
    const fields = ADMIN_TAB_FIELDS[tab];
    if (!fields) return;
    const f = {};
    for (const id of Object.keys(fields)) {
        const el = document.getElementById(id);
        if (id in adminPending) f[id] = adminPending[id];   // ещё не восстановлено — не затираем
        else if (el) f[id] = adminFieldValue(el);
    }
    adminState.filters[tab] = f;
    adminPersist();
    if (adminState.tab === tab) adminWriteUrl(tab);
}

function adminWriteUrl(tab) {
    const params = new URLSearchParams({ tab });
    const fields = ADMIN_TAB_FIELDS[tab] || {};
    const f = adminState.filters[tab] || {};
    for (const [id, param] of Object.entries(fields)) {
        if (f[id]) params.set(param, f[id]);
    }
    history.replaceState(history.state, '', `${location.pathname}?${params}`);
}

// Вкладка при открытии страницы: из адреса, иначе последняя открытая. Фильтры из адреса
// заменяют сохранённые для этой вкладки. Поля со статичными вариантами выставляются сразу.
function adminInitialTab() {
    const params = new URLSearchParams(location.search);
    let tab = params.get('tab');
    if (tab && ADMIN_TAB_FIELDS[tab]) {
        const f = {};
        for (const [id, param] of Object.entries(ADMIN_TAB_FIELDS[tab])) {
            if (params.has(param)) f[id] = params.get(param);
        }
        adminState.filters[tab] = f;
    }
    if (!tab) {
        tab = adminState.tab;
        try { tab = tab || localStorage.getItem(ADMIN_LEGACY_TAB_KEY); } catch (e) { /* нет хранилища */ }
    }
    for (const f of Object.values(adminState.filters)) Object.assign(adminPending, f);
    Object.keys(adminPending).filter(id => !ADMIN_LOADED_FIELDS.has(id)).forEach(adminRestoreValue);
    return tab;
}

function adminOnTabSwitch(tab) {
    if (adminState.tab && adminState.tab !== tab) adminState.scroll[adminState.tab] = window.scrollY;
    adminState.tab = tab;
    adminPersist();
    if (ADMIN_TAB_FIELDS[tab]) adminSaveFilters(tab);
    else history.replaceState(history.state, '', `${location.pathname}?tab=${encodeURIComponent(tab)}`);
    adminRestoreScroll(adminState.scroll[tab] || 0);
}

// Прокрутка: содержимое вкладки догружается — ждём, пока страница вырастет до сохранённой
// позиции. Пользователь сам крутит/кликает — восстановление отменяется.
function adminRestoreScroll(y) {
    if (!y) { window.scrollTo(0, 0); return; }
    adminScrollRestoring = true;
    let observer = null, timer = null;
    const stop = () => {
        adminScrollRestoring = false;
        if (observer) observer.disconnect();
        clearTimeout(timer);
        ['wheel', 'touchstart', 'keydown', 'mousedown'].forEach(ev => window.removeEventListener(ev, stop));
    };
    const attempt = () => {
        if (document.documentElement.scrollHeight - window.innerHeight >= y) {
            window.scrollTo(0, y);
            stop();
        }
    };
    ['wheel', 'touchstart', 'keydown', 'mousedown'].forEach(ev => window.addEventListener(ev, stop, { passive: true }));
    timer = setTimeout(stop, 15000);
    if (typeof ResizeObserver === 'function') {
        observer = new ResizeObserver(attempt);
        observer.observe(document.body);
    }
    attempt();
}

// Перезагрузка списка после сохранения не должна схлопывать страницу (и сбрасывать прокрутку),
// пока вместо списка висит «Загрузка…»: держим прежнюю высоту до отрисовки.
function adminHoldHeight(el) {
    if (!el) return () => {};
    el.style.minHeight = `${el.offsetHeight}px`;
    return () => { el.style.minHeight = ''; };
}

// ---- Черновики: поля с data-draft="ключ" ----

// Исходное значение поля из разметки — с ним черновик не нужен
function adminDefaultValue(el) {
    return el.type === 'checkbox' ? (el.defaultChecked ? '1' : '') : el.defaultValue;
}

function adminApplyDrafts(root) {
    (root || document).querySelectorAll('[data-draft]').forEach(el => {
        const key = el.dataset.draft;
        if (!(key in adminState.drafts)) return;
        if (adminState.drafts[key] === adminDefaultValue(el)) {
            delete adminState.drafts[key];
            return;
        }
        adminSetField(el, adminState.drafts[key]);
        el.classList.add('admin-draft');
    });
    adminPersist();
}

function adminSetDraft(key, value) {
    adminState.drafts[key] = value;
    adminPersist();
}

function adminGetDraft(key) {
    return key in adminState.drafts ? adminState.drafts[key] : null;
}

function adminClearDrafts(prefix) {
    for (const key of Object.keys(adminState.drafts)) {
        if (key.startsWith(prefix)) delete adminState.drafts[key];
    }
    adminPersist();
}

function adminSetExtra(key, value) {
    adminState.extra[key] = value;
    adminPersist();
}

document.addEventListener('input', e => {
    const el = e.target;
    if (!el || !el.dataset || !el.dataset.draft) return;
    const value = adminFieldValue(el);
    // стёрли ввод / вернули как было — это уже не несохранённая правка
    // (YAML-редактор заполняется из JS, его исходное значение в разметке пустое)
    const unchanged = value === adminDefaultValue(el) && el.tagName !== 'TEXTAREA';
    if (unchanged) {
        adminClearDrafts(el.dataset.draft);
        el.classList.remove('admin-draft');
    } else {
        adminSetDraft(el.dataset.draft, value);
        el.classList.add('admin-draft');
    }
});

document.addEventListener('change', e => {
    const tab = e.target && e.target.id ? adminTabOf(e.target.id) : null;
    if (!tab) return;
    // выбор пользователя важнее ещё не восстановленных значений этой вкладки
    Object.keys(ADMIN_TAB_FIELDS[tab]).forEach(id => { delete adminPending[id]; });
    // после синхронной части inline-обработчика (сброс зависимых списков)
    setTimeout(() => adminSaveFilters(tab), 0);
});

window.addEventListener('scroll', () => {
    if (adminScrollRestoring || !adminState.tab) return;
    adminState.scroll[adminState.tab] = window.scrollY;
}, { passive: true });

window.addEventListener('pagehide', () => {
    if (adminState.tab && !adminScrollRestoring) adminState.scroll[adminState.tab] = window.scrollY;
    adminPersist();
});

if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
