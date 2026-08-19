// Тесты для static/js/analytics-start-list.js:
// 1) applyFilters() скрывает фильтр/колонку "Возрастная группа" на любой
//    дистанции без брекетов категорий (данные, не хардкод конкретной
//    строки "2 км") — реальный случай: "500 м" Детского забега.
// 2) switchEvent(trigger) — год автоматически переключается на последний
//    год с данными (/api/registered-runners-years) ТОЛЬКО при смене
//    события (trigger==='event'), не при ручном выборе года.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_start_list_age_group_year.js
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
}

class FakeImage {
    set src(_url) { if (this.onerror) this.onerror(); } // без фото — не мешает тесту
    get src() { return this._url; }
}

let calledUrls = [];
let fetchMock = () => Promise.resolve({ json: () => Promise.resolve({}) });

const sandbox = {
    console,
    fetch: (url) => { calledUrls.push(String(url)); return fetchMock(url); },
    document: {
        getElementById: domStub,
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
        querySelectorAll: () => [],
        querySelector: () => null,
        documentElement: { style: { setProperty: () => {} } },
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    Image: FakeImage,
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

const KIDS_500 = [
    { sex: 'Мужчина', surname: 'Иванов', name: 'Иван', category: '', distance: '500 м' },
    { sex: 'Женщина', surname: 'Петрова', name: 'Анна', category: '', distance: '500 м' },
];
const KIDS_1KM = [
    { sex: 'Мужчина', surname: 'Сидоров', name: 'Пётр', category: '8 лет', distance: '1 км' },
];

check('KMUtils.parseDistanceKm() — учитывает единицу измерения ("500 м" < "1 км", не голое число)', () => {
    assert.strictEqual(sandbox.KMUtils.parseDistanceKm('500 м'), 0.5);
    assert.strictEqual(sandbox.KMUtils.parseDistanceKm('1 км'), 1);
    assert.ok(sandbox.KMUtils.parseDistanceKm('500 м') < sandbox.KMUtils.parseDistanceKm('1 км'));
});

check('populateDistances() — реальный случай Детского забега: дефолт "1 км" (максимальная), не "500 м"', () => {
    resetDom();
    setAllRunners([...KIDS_500, ...KIDS_1KM]);
    domStub('distanceFilter').value = '';
    vm.runInContext('populateDistances(allRunners)', sandbox);
    assert.strictEqual(domStub('distanceFilter').value, '1 км');
});

check('applyFilters() — скрывает фильтр/колонку "Возр. группа" на дистанции без категорий (500 м)', () => {
    resetDom();
    setAllRunners(KIDS_500);
    domStub('distanceFilter').value = '500 м';
    vm.runInContext('applyFilters()', sandbox);
    assert.strictEqual(domStub('ageGroupFilterGroup').style.display, 'none');
    assert.strictEqual(domStub('startListTable').classList.contains('km-table--hide-age-group'), true);
});

check('applyFilters() — НЕ скрывает фильтр на дистанции с категориями (1 км)', () => {
    resetDom();
    setAllRunners(KIDS_1KM);
    domStub('distanceFilter').value = '1 км';
    vm.runInContext('applyFilters()', sandbox);
    assert.strictEqual(domStub('ageGroupFilterGroup').style.display, '');
    assert.strictEqual(domStub('startListTable').classList.contains('km-table--hide-age-group'), false);
});

check('applyFilters() — скрытие считается только по ТЕКУЩЕЙ дистанции, соседняя без категорий не мешает', () => {
    resetDom();
    setAllRunners([...KIDS_500, ...KIDS_1KM]);
    domStub('distanceFilter').value = '1 км';
    vm.runInContext('applyFilters()', sandbox);
    assert.strictEqual(domStub('ageGroupFilterGroup').style.display, '');
});

(async () => {
    await checkAsync('switchEvent("event") — автовыбор последнего года с заявками из /api/registered-runners-years', async () => {
        resetDom();
        calledUrls = [];
        domStub('eventSelector').value = 'kids';
        domStub('yearStartSelector').value = '2025';
        fetchMock = (url) => {
            if (String(url).includes('registered-runners-years')) {
                assert.ok(String(url).includes('event_name=' + encodeURIComponent('Детский забег')));
                return Promise.resolve({ json: () => Promise.resolve({ years: [2026, 2025] }) });
            }
            return Promise.resolve({ json: () => Promise.resolve({}) });
        };
        await sandbox.switchEvent('event');
        assert.strictEqual(domStub('yearStartSelector').value, 2026);
        assert.ok(calledUrls.some(u => u.includes('registered-runners-years')));
    });

    await checkAsync('switchEvent("year") — НЕ дёргает /api/registered-runners-years, год берётся из селектора как есть', async () => {
        resetDom();
        calledUrls = [];
        domStub('eventSelector').value = 'kids';
        domStub('yearStartSelector').value = '2024';
        fetchMock = () => Promise.resolve({ json: () => Promise.resolve({ years: [2026] }) });
        await sandbox.switchEvent('year');
        assert.strictEqual(domStub('yearStartSelector').value, '2024');
        assert.ok(!calledUrls.some(u => u.includes('registered-runners-years')));
    });

    await checkAsync('switchEvent("event") — если API не вернул годы, значение селектора года не трогается', async () => {
        resetDom();
        domStub('eventSelector').value = 'kids';
        domStub('yearStartSelector').value = '2025';
        fetchMock = (url) => String(url).includes('registered-runners-years')
            ? Promise.resolve({ json: () => Promise.resolve({ years: [] }) })
            : Promise.resolve({ json: () => Promise.resolve({}) });
        await sandbox.switchEvent('event');
        assert.strictEqual(domStub('yearStartSelector').value, '2025');
    });

    console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
    process.exit(failures === 0 ? 0 : 1);
})();
