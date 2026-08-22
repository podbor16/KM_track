// Тест для static/js/analytics-results.js: тай-брейк сортировки колонок
// времени (Офиц./Чист.) внутри одной целой секунды. Найдено пользователем
// на живом Детском забеге 2026-08-22: Момотов Артемий (место в категории 53)
// и Осипенко Владимир (место 52) оба финишировали в "5:48" по официальному
// времени — таблица сортировала тай-брейк по фамилии в алфавитном порядке
// ("Момотов" < "Осипенко"), а НЕ по уже посчитанному на сервере месту
// (с точностью до мс, см. _recalculate_ranks() в load_race_results.py) —
// из-за чего строка с местом 53 визуально шла выше строки с местом 52.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_time_tiebreak.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeElement() {
    return { value: '', dataset: {} };
}
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement();
    return elementsById[id];
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: domStub,
        createElement: () => makeElement(),
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

// Точное воспроизведение живого случая: Момотов (кат. место 53) и Осипенко
// (кат. место 52) — оба "5:48" по офиц. времени с точностью до целой секунды.
const RUNNERS_TIE = [
    { status: 'Finished', surname: 'Момотов', name: 'Артемий', start_number: '8086',
      time_gun_finish: '5:48', time_clear_finish: '5:48',
      rank_absolute: 53, rank_category: 53, rank_sex: 53 },
    { status: 'Finished', surname: 'Осипенко', name: 'Владимир', start_number: '8124',
      time_gun_finish: '5:48', time_clear_finish: '5:45',
      rank_absolute: 52, rank_category: 52, rank_sex: 52 },
];

check('_sortArray() по офиц. времени — тай-брейк на равной секунде идёт по месту в категории, а не по алфавиту фамилии', () => {
    domStub('genderFilter').dataset.value = '';
    domStub('ageGroupFilter').value = 'Мальчики 2018 г.р.'; // активен фильтр по возрастной группе
    vm.runInContext(`sortState = { column: 'time_gun', direction: 'asc' };`, sandbox);
    const sorted = sandbox._sortArray(RUNNERS_TIE);
    assert.strictEqual(sorted[0].surname, 'Осипенко', 'место 52 должно идти раньше места 53');
    assert.strictEqual(sorted[1].surname, 'Момотов');
});

check('_sortArray() по чистому времени — Осипенко (5:45) реально быстрее, тай-брейк тут не нужен, но место совпадает', () => {
    domStub('genderFilter').dataset.value = '';
    domStub('ageGroupFilter').value = 'Мальчики 2018 г.р.';
    vm.runInContext(`sortState = { column: 'time_net', direction: 'asc' };`, sandbox);
    const sorted = sandbox._sortArray(RUNNERS_TIE);
    assert.strictEqual(sorted[0].surname, 'Осипенко');
    assert.strictEqual(sorted[1].surname, 'Момотов');
});

check('_sortArray() без активных фильтров — тай-брейк идёт по rank_absolute', () => {
    domStub('genderFilter').dataset.value = '';
    domStub('ageGroupFilter').value = '';
    vm.runInContext(`sortState = { column: 'time_gun', direction: 'asc' };`, sandbox);
    const sorted = sandbox._sortArray(RUNNERS_TIE);
    assert.strictEqual(sorted[0].surname, 'Осипенко');
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
