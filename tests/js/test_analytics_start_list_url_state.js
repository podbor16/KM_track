// Тесты для static/js/analytics-start-list.js: сохранение фильтров в URL
// (readStateFromUrl()/syncUrlFromState()) — прямая ссылка на конкретный
// событие+год+дистанцию+фильтры старт-листа (напр. чтобы прислать ссылку
// на нужный забег). Тот же паттерн, что и на Siberman results.html
// (history.replaceState, не pushState — см. test_siberman_results_merge.js).
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_start_list_url_state.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-start-list.js'), 'utf-8');

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
    ['', 'Женщина', 'Мужчина'].forEach(value => {
        const pill = makeElement('BUTTON');
        pill.dataset.value = value;
        pill._classes.add('km-pill');
        if (value === '') pill._classes.add('active');
        container.appendChild(pill);
    });
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: domStub,
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
        querySelectorAll: () => [],
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    URLSearchParams,
    location: { pathname: '/start_list', search: '', hash: '' },
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

const KIDS_RUNNERS = [
    { sex: 'Мужчина', surname: 'Иванов', name: 'Иван', category: '8 лет', distance: '1 км' },
    { sex: 'Женщина', surname: 'Петрова', name: 'Анна', category: '7 лет', distance: '1 км' },
    { sex: 'Мужчина', surname: 'Сидоров', name: 'Пётр', category: '', distance: '500 м' },
];

check('readStateFromUrl() — распознаёт event/year/distance/ageGroup из query', () => {
    resetDom();
    sandbox.location.search = '?event=kids&year=2026&distance=1%20%D0%BA%D0%BC&ageGroup=8%20%D0%BB%D0%B5%D1%82';
    sandbox.readStateFromUrl();
    assert.strictEqual(vm.runInContext('_urlEvent', sandbox), 'kids');
    assert.strictEqual(vm.runInContext('_urlYear', sandbox), 2026);
    assert.strictEqual(vm.runInContext('_urlDistance', sandbox), '1 км');
    assert.strictEqual(vm.runInContext('_urlAgeGroup', sandbox), '8 лет');
});

check('readStateFromUrl() — неизвестное событие в URL игнорируется (не ломает дефолт)', () => {
    resetDom();
    sandbox.location.search = '?event=не_существует';
    sandbox.readStateFromUrl();
    assert.strictEqual(vm.runInContext('_urlEvent', sandbox), null);
});

check('readStateFromUrl() — некорректный пол в URL игнорируется, пилюля не переключается', () => {
    resetDom();
    sandbox.location.search = '?gender=bogus';
    sandbox.readStateFromUrl();
    assert.strictEqual(sandbox.getGenderFilterValue(), '');
});

check('readStateFromUrl() — валидный пол применяет пилюлю сразу', () => {
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

check('_urlDistance/_urlAgeGroup применяются к select после загрузки данных и "потребляются" один раз', () => {
    resetDom();
    sandbox.location.search = '?distance=' + encodeURIComponent('1 км') + '&ageGroup=' + encodeURIComponent('8 лет');
    sandbox.readStateFromUrl();
    setAllRunners(KIDS_RUNNERS);
    vm.runInContext('applyFilters()', sandbox);

    assert.strictEqual(domStub('distanceFilter').value, '1 км');
    assert.strictEqual(domStub('ageGroupFilter').value, '8 лет');
    // "Потреблены" — второй applyFilters() с изменённым выбором пользователя
    // не должен снова принудительно ставить старое значение из URL, если
    // пользователь выбрал что-то другое
    domStub('distanceFilter').value = '500 м';
    domStub('ageGroupFilter').value = '';
    vm.runInContext('applyFilters()', sandbox);
    assert.strictEqual(domStub('distanceFilter').value, '500 м', 'ручной выбор дистанции не должен перебиваться повторно применённым URL-значением');
});

check('syncUrlFromState() — пишет event/year/distance/gender/ageGroup/search в URL через replaceState', () => {
    resetDom();
    setAllRunners(KIDS_RUNNERS);
    vm.runInContext(`currentEvent = 'kids'; currentYear = 2026;`, sandbox);
    domStub('distanceFilter').value = '1 км';
    sandbox.setGenderFilter('Мужчина');
    domStub('ageGroupFilter').value = '8 лет';
    domStub('surnameSearch').value = 'Иван';

    vm.runInContext('applyFilters()', sandbox);

    const params = new URLSearchParams(sandbox.location.search);
    assert.strictEqual(params.get('event'), 'kids');
    assert.strictEqual(params.get('year'), '2026');
    assert.strictEqual(params.get('distance'), '1 км');
    assert.strictEqual(params.get('gender'), 'Мужчина');
    assert.strictEqual(params.get('ageGroup'), '8 лет');
    assert.strictEqual(params.get('search'), 'Иван');
});

check('syncUrlFromState() — не пишет distance/gender/ageGroup/search в URL, если они пустые ("Все")', () => {
    resetDom();
    setAllRunners(KIDS_RUNNERS);
    vm.runInContext(`currentEvent = 'kids'; currentYear = 2026;`, sandbox);
    domStub('distanceFilter').value = '1 км';

    vm.runInContext('applyFilters()', sandbox);

    const params = new URLSearchParams(sandbox.location.search);
    assert.strictEqual(params.has('gender'), false);
    assert.strictEqual(params.has('ageGroup'), false);
    assert.strictEqual(params.has('search'), false);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
