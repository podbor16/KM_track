// Тест updateEventBanner() из static/js/analytics-results.js — баннер
// события над тулбаром показывается ТОЛЬКО если для события реально есть
// фото в static/images/events/ (проверено загрузкой картинки в браузере,
// не хардкод-списком). Найдено пользователем на живом сайте: после
// редизайна баннер пропал даже у событий, у которых фото реально есть.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_event_banner.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeElement(tag) {
    return {
        tagName: (tag || 'DIV').toUpperCase(), style: {}, value: '', textContent: '', dataset: {},
        appendChild() {}, addEventListener() {}, querySelectorAll() { return []; },
    };
}
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement('DIV');
    return elementsById[id];
}

// Image-стаб: .src устанавливается синхронно и триггерит onload/onerror в
// зависимости от того, есть ли этот URL в SUCCESS_URLS (тестовый контроль
// "какие картинки реально существуют" без обращения к сети/диску).
let SUCCESS_URLS = new Set();
class FakeImage {
    set src(url) {
        this._url = url;
        if (SUCCESS_URLS.has(url)) { if (this.onload) this.onload(); }
        else { if (this.onerror) this.onerror(); }
    }
    get src() { return this._url; }
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: domStub,
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
        querySelectorAll: () => [],
        documentElement: { style: { setProperty: () => {} } },
    },
    Image: FakeImage,
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(utilsJs, sandbox);
vm.runInContext(scriptJs, sandbox);

// currentEvent — module-level `let`: недоступен как sandbox.currentEvent
// напрямую (vm не экспонирует let-биндинги наружу), но присваивание кодом
// внутри того же контекста видит существующий биндинг.
function setCurrentEvent(code) {
    vm.runInContext(`currentEvent = ${JSON.stringify(code)};`, sandbox);
}

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('updateEventBanner() — показывает баннер, если фото реально загружается (onload)', () => {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
    setCurrentEvent('vesna');
    SUCCESS_URLS = new Set([`/static/images/events/${encodeURIComponent('Весна')}.png`]);
    sandbox.updateEventBanner();
    const banner = domStub('eventBanner');
    assert.strictEqual(banner.style.display, '');
    assert.ok(banner.style.backgroundImage.includes(encodeURIComponent('Весна')));
});

check('updateEventBanner() — прячет баннер, если фото не загрузилось (onerror)', () => {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
    setCurrentEvent('dostigaya_tseli');
    SUCCESS_URLS = new Set(); // ничего "не существует"
    sandbox.updateEventBanner();
    const banner = domStub('eventBanner');
    assert.strictEqual(banner.style.display, 'none');
});

check('updateEventBanner() — не падает, если #eventBanner отсутствует в DOM', () => {
    const original = sandbox.document.getElementById;
    sandbox.document.getElementById = (id) => id === 'eventBanner' ? null : domStub(id);
    assert.doesNotThrow(() => sandbox.updateEventBanner());
    sandbox.document.getElementById = original;
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
