// Тесты для static/js/analytics-results.js: сохранение фильтров в URL
// (readStateFromUrl()/syncUrlFromState()) — прямая ссылка на конкретный
// событие+год+дистанцию+фильтры результатов (напр. чтобы прислать ссылку
// на нужный забег с уже выбранными фильтрами). Тот же паттерн, что уже на
// /start_list, см. tests/js/test_analytics_start_list_url_state.js.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_url_state.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeElement(tag) {
    const children = [];
    const classes = new Set();
    return {
        tagName: (tag || 'DIV').toUpperCase(),
        value: '',
        textContent: '',
        style: {},
        dataset: {},
        _children: children,
        get options() { return children.filter(c => c.tagName === 'OPTION'); },
        set innerHTML(v) { if (v === '') children.length = 0; },
        get innerHTML() { return ''; },
        appendChild(child) { children.push(child); return child; },
        addEventListener() {},
        setAttribute() {},
        querySelectorAll(sel) {
            if (sel === '.km-pill') return children.filter(c => c._classes && c._classes.has('km-pill'));
            return [];
        },
        classList: {
            add: (c) => classes.add(c),
            remove: (c) => classes.delete(c),
            toggle: (c, force) => {
                if (force === undefined) { classes.has(c) ? classes.delete(c) : classes.add(c); }
                else if (force) classes.add(c); else classes.delete(c);
            },
            contains: (c) => classes.has(c),
        },
        _classes: classes,
    };
}

const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement('DIV');
    return elementsById[id];
}
function resetDom() {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
    const container = domStub('genderFilter');
    container.dataset.value = '';
}

class FakeImage {
    set src(_url) { if (this.onerror) this.onerror(); }
    get src() { return this._url; }
}

class FakeSSEClient {
    constructor() {}
    close() {}
}

let fetchMock = () => Promise.resolve({ json: () => Promise.resolve({}) });

const sandbox = {
    console,
    fetch: (url) => fetchMock(url),
    document: {
        getElementById: domStub,
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
        querySelectorAll: () => [],
        querySelector: () => null,
        documentElement: { style: { setProperty: () => {} } },
    },
    Image: FakeImage,
    SSEClient: FakeSSEClient,
    URLSearchParams,
    location: { pathname: '/results', search: '', hash: '' },
    history: { replaceState: (_s, _t, url) => { sandbox.location.search = (url.split('?')[1] ? '?' + url.split('?')[1] : ''); } },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(utilsJs, sandbox);
vm.runInContext(scriptJs, sandbox);

function setAllRunners(fixture) {
    vm.runInContext(`allRunners = ${JSON.stringify(fixture)};`, sandbox);
}

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}
async function checkAsync(name, fn) {
    try { await fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

const ZHARA_RUNNERS = [
    { gender: 'Мужчина', surname: 'Иванов', name: 'Иван', category: 'M18-49', event: '5 км' },
    { gender: 'Женщина', surname: 'Петрова', name: 'Анна', category: 'Ж18-49', event: '5 км' },
];

check('readStateFromUrl() — распознаёт event/year/distance/ageGroup из query', () => {
    resetDom();
    sandbox.location.search = '?event=zhara&year=2026&distance=5%20%D0%BA%D0%BC&ageGroup=M18-49';
    sandbox.readStateFromUrl();
    assert.strictEqual(vm.runInContext('_urlEvent', sandbox), 'zhara');
    assert.strictEqual(vm.runInContext('_urlYear', sandbox), 2026);
    assert.strictEqual(vm.runInContext('_urlDistance', sandbox), '5 км');
    assert.strictEqual(vm.runInContext('_urlAgeGroup', sandbox), 'M18-49');
});

check('readStateFromUrl() — неизвестное событие в URL игнорируется (не ломает дефолт)', () => {
    resetDom();
    sandbox.location.search = '?event=не_существует';
    sandbox.readStateFromUrl();
    assert.strictEqual(vm.runInContext('_urlEvent', sandbox), null);
});

check('readStateFromUrl() — некорректный пол в URL игнорируется', () => {
    resetDom();
    sandbox.location.search = '?gender=bogus';
    sandbox.readStateFromUrl();
    assert.strictEqual(sandbox.getGenderFilterValue(), '');
});

check('readStateFromUrl() — валидный пол применяется сразу (dataset.value)', () => {
    resetDom();
    sandbox.location.search = '?gender=' + encodeURIComponent('Женщина');
    sandbox.readStateFromUrl();
    assert.strictEqual(sandbox.getGenderFilterValue(), 'Женщина');
});

check('readStateFromUrl() — search применяется в поле поиска сразу', () => {
    resetDom();
    sandbox.location.search = '?search=' + encodeURIComponent('Иванов');
    sandbox.readStateFromUrl();
    assert.strictEqual(domStub('surnameSearch').value, 'Иванов');
});

check('_urlDistance/_urlAgeGroup применяются к select после applyFilters() и "потребляются" один раз', () => {
    resetDom();
    sandbox.location.search = '?distance=' + encodeURIComponent('5 км') + '&ageGroup=' + encodeURIComponent('Ж18-49');
    sandbox.readStateFromUrl();
    setAllRunners(ZHARA_RUNNERS);
    vm.runInContext('applyFilters()', sandbox);

    assert.strictEqual(domStub('distanceFilter').value, '5 км');
    assert.strictEqual(domStub('ageGroupFilter').value, 'Ж18-49');
    // "Потреблены" — второй applyFilters() с изменённым выбором пользователя
    // не должен снова принудительно ставить старое значение из URL
    domStub('ageGroupFilter').value = '';
    vm.runInContext('applyFilters()', sandbox);
    assert.strictEqual(domStub('ageGroupFilter').value, '', 'ручной выбор не должен перебиваться повторно применённым URL-значением');
});

check('syncUrlFromState() — пишет event/year/distance/gender/ageGroup/search в URL через replaceState', () => {
    resetDom();
    setAllRunners(ZHARA_RUNNERS);
    vm.runInContext(`currentEvent = 'zhara'; currentYear = 2026;`, sandbox);
    domStub('distanceFilter').value = '5 км';
    sandbox.setGenderFilter('Мужчина');
    domStub('ageGroupFilter').value = 'M18-49';
    domStub('surnameSearch').value = 'Иванов';

    vm.runInContext('applyFilters()', sandbox);

    const params = new URLSearchParams(sandbox.location.search);
    assert.strictEqual(params.get('event'), 'zhara');
    assert.strictEqual(params.get('year'), '2026');
    assert.strictEqual(params.get('distance'), '5 км');
    assert.strictEqual(params.get('gender'), 'Мужчина');
    assert.strictEqual(params.get('ageGroup'), 'M18-49');
    assert.strictEqual(params.get('search'), 'Иванов');
});

check('syncUrlFromState() — не пишет gender/ageGroup/search в URL, если они пустые ("Все")', () => {
    resetDom();
    setAllRunners(ZHARA_RUNNERS);
    vm.runInContext(`currentEvent = 'zhara'; currentYear = 2026;`, sandbox);
    domStub('distanceFilter').value = '5 км';

    vm.runInContext('applyFilters()', sandbox);

    const params = new URLSearchParams(sandbox.location.search);
    assert.strictEqual(params.has('gender'), false);
    assert.strictEqual(params.has('ageGroup'), false);
    assert.strictEqual(params.has('search'), false);
});

(async () => {
    await checkAsync('initResultsPage() — параметры URL переопределяют дефолт события/года', async () => {
        resetDom();
        sandbox.location.search = '?event=zhara&year=2025';
        fetchMock = (url) => {
            if (String(url).includes('/api/current-event')) {
                return Promise.resolve({ json: () => Promise.resolve({ event: 'kids', year: 2026 }) });
            }
            return Promise.resolve({ json: () => Promise.resolve({ results: [] }) });
        };

        await sandbox.initResultsPage();

        assert.strictEqual(domStub('eventResultsSelector').value, 'zhara');
        assert.strictEqual(domStub('yearResultsSelector').value, 2025);
        assert.strictEqual(vm.runInContext('currentEvent', sandbox), 'zhara');
        assert.strictEqual(vm.runInContext('currentYear', sandbox), 2025);
    });

    await checkAsync('initResultsPage() — без параметров URL использует активное событие с /api/current-event', async () => {
        resetDom();
        sandbox.location.search = '';
        fetchMock = (url) => {
            if (String(url).includes('/api/current-event')) {
                return Promise.resolve({ json: () => Promise.resolve({ event: 'kids', year: 2026 }) });
            }
            return Promise.resolve({ json: () => Promise.resolve({ results: [] }) });
        };

        await sandbox.initResultsPage();

        assert.strictEqual(vm.runInContext('currentEvent', sandbox), 'kids');
    });

    console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
    process.exit(failures === 0 ? 0 : 1);
})();
