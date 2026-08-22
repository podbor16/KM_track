// Тест для static/js/analytics-results.js: колонка "Категория" в таблице
// результатов видна только когда фильтр по возр. группе = "Все" (запрос
// пользователя 2026-08-22) — иначе она одинакова на каждой строке и не
// несёт информации.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_category_column.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeRowStub() {
    return {
        className: '',
        _innerHTML: '',
        dataset: {},
        set innerHTML(v) { this._innerHTML = v; },
        get innerHTML() { return this._innerHTML; },
        addEventListener() {},
    };
}
function makeTbodyStub() {
    const rows = [];
    return {
        _rows: rows,
        set innerHTML(v) { if (v === '') rows.length = 0; },
        get innerHTML() { return ''; },
        appendChild(row) { rows.push(row); return row; },
    };
}
function makeSimpleElement() {
    return { value: '', dataset: {}, style: {} };
}

const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) {
        elementsById[id] = id === 'resultsTableBody' ? makeTbodyStub() : makeSimpleElement();
    }
    return elementsById[id];
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: domStub,
        createElement: () => makeRowStub(),
        addEventListener: () => {},
        querySelectorAll: () => [],
    },
    URLSearchParams,
    location: { pathname: '/results', search: '', hash: '' },
    history: { replaceState: () => {} },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(utilsJs, sandbox);
vm.runInContext(scriptJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

const RUNNERS = [
    { status: 'Finished', surname: 'Баценко', name: 'Егор', start_number: '5026',
      category: 'Мальчики 2018 г.р.', rank_absolute: 1,
      time_gun_finish: '3:22', time_clear_finish: '3:22' },
    { status: 'Finished', surname: 'Сарахман', name: 'Артём', start_number: '5040',
      category: 'Мальчики 2019 г.р.', rank_absolute: 2,
      time_gun_finish: '3:24', time_clear_finish: '3:24' },
];

check('renderResultsTable() — фильтр возр. группы = "Все" → колонка "Категория" видна с текстом категории', () => {
    domStub('ageGroupFilter').value = '';
    sandbox.renderResultsTable(RUNNERS);
    const thCategory = domStub('thCategory');
    assert.strictEqual(thCategory.style.display, '');
    const rows = domStub('resultsTableBody')._rows;
    assert.ok(rows[0].innerHTML.includes('Мальчики 2018 г.р.'), 'строка должна содержать категорию первого участника');
    assert.ok(rows[1].innerHTML.includes('Мальчики 2019 г.р.'), 'строка должна содержать категорию второго участника');
});

check('renderResultsTable() — конкретная возр. группа выбрана → колонка "Категория" скрыта', () => {
    domStub('ageGroupFilter').value = 'Мальчики 2018 г.р.';
    sandbox.renderResultsTable(RUNNERS);
    const thCategory = domStub('thCategory');
    assert.strictEqual(thCategory.style.display, 'none');
    const rows = domStub('resultsTableBody')._rows;
    assert.ok(!rows[0].innerHTML.includes('Мальчики 2018 г.р.'), 'категория не должна рендериться в ячейке при активном фильтре');
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
