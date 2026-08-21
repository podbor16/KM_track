// Тест для static/js/utils.js: KMUtils.fetchFresh() — обёртка над fetch()
// с явным cache:'no-store'. Найдено 2026-08-21: пользователь не находил
// участников полумарафона через встроенный браузер Telegram, хотя сервер
// корректно отдаёт Cache-Control: no-store и данные (проверено live) — и
// даже эндпоинт с ручным cache-busting (?v=Date.now()) не спасал. Explicit
// cache:'no-store' в самом fetch() — дополнительный уровень защиты для
// WebView, которые не всегда честно ревалидируют по одним заголовкам
// ответа. См. sessions/2026-05-23-telegram-cache-fix (тот фикс закрыл
// HTML/статику, не fetch()-запросы за данными).
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_utils_fetch_fresh.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');

let lastFetchArgs = null;
const sandbox = {
    console,
    fetch: (url, options) => { lastFetchArgs = { url, options }; return Promise.resolve({ ok: true }); },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(utilsJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('fetchFresh() — вызывает fetch с cache: "no-store"', () => {
    lastFetchArgs = null;
    sandbox.KMUtils.fetchFresh('/api/current-event');
    assert.strictEqual(lastFetchArgs.url, '/api/current-event');
    assert.strictEqual(lastFetchArgs.options.cache, 'no-store');
});

check('fetchFresh() — сохраняет прочие переданные опции, не только добавляет cache', () => {
    lastFetchArgs = null;
    sandbox.KMUtils.fetchFresh('/api/event-results?event_id=116', { method: 'POST' });
    assert.strictEqual(lastFetchArgs.options.method, 'POST');
    assert.strictEqual(lastFetchArgs.options.cache, 'no-store');
});

check('fetchFresh() — cache:"no-store" нельзя случайно перебить вызывающим кодом', () => {
    lastFetchArgs = null;
    sandbox.KMUtils.fetchFresh('/api/current-event', { cache: 'force-cache' });
    assert.strictEqual(lastFetchArgs.options.cache, 'no-store');
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
