// Тест для static/js/analytics-results.js: populateAgeGroups() — сортировка
// возрастных категорий по возрасту (по возрастанию), женщины сначала, потом
// мужчины. Реальная находка (2026-08-21, скриншот /results для «Жара»):
// список категорий выглядел "случайным" — старый список regex-правил
// (AGE_ORDER_RULES) не покрывал детские категории Жары ("Ж12-13"/"Ж14-15"/
// "Ж16-17" — все падали в один "прочее"-бакет без внутреннего порядка) и
// путал "75-79"/"80+" (оба матчили одно и то же правило "75|80\+|..."). Фикс
// — извлекать первое число из строки категории и сортировать по нему.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_age_group_sort.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeElement(tag) {
    const children = [];
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
        querySelectorAll() { return []; },
    };
}

const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement('DIV');
    return elementsById[id];
}
function resetDom() {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
    domStub('genderFilter').dataset.value = '';
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

// Ровно те категории, что были на живом /results для «Жара» 5 км
// (2026-08-21) — реальный набор после того, как судья переписал названия
// категорий в Copernico на компактный формат "Ж18-49"/"М80+" и т.п.
const ZHARA_RUNNERS = [
    { gender: 'Женщина', category: 'Ж18-49' },
    { gender: 'Женщина', category: 'Ж50-59' },
    { gender: 'Женщина', category: 'Ж60-64' },
    { gender: 'Женщина', category: 'Ж65-69' },
    { gender: 'Женщина', category: 'Ж80+' },
    { gender: 'Женщина', category: 'Ж12-13' },
    { gender: 'Женщина', category: 'Ж16-17' },
    { gender: 'Женщина', category: 'Ж14-15' },
    { gender: 'Мужчина', category: 'М18-49' },
    { gender: 'Мужчина', category: 'М50-59' },
    { gender: 'Мужчина', category: 'М60-64' },
    { gender: 'Мужчина', category: 'М65-69' },
    { gender: 'Мужчина', category: 'М70-74' },
    { gender: 'Мужчина', category: 'М80+' },
    { gender: 'Мужчина', category: 'М75-79' },
    { gender: 'Мужчина', category: 'М12-13' },
    { gender: 'Мужчина', category: 'М16-17' },
    { gender: 'Мужчина', category: 'М14-15' },
];

check('populateAgeGroups() — категории идут по возрасту (женщины сначала, потом мужчины)', () => {
    resetDom();
    sandbox.populateAgeGroups(ZHARA_RUNNERS);
    const values = domStub('ageGroupFilter').options.map(o => o.value).filter(v => v !== '');

    assert.deepStrictEqual(values, [
        'Ж12-13', 'Ж14-15', 'Ж16-17', 'Ж18-49', 'Ж50-59', 'Ж60-64', 'Ж65-69', 'Ж80+',
        'М12-13', 'М14-15', 'М16-17', 'М18-49', 'М50-59', 'М60-64', 'М65-69', 'М70-74', 'М75-79', 'М80+',
    ]);
});

check('populateAgeGroups() — 75-79 идёт перед 80+ (раньше оба матчили одно правило)', () => {
    resetDom();
    sandbox.populateAgeGroups(ZHARA_RUNNERS);
    const values = domStub('ageGroupFilter').options.map(o => o.value);
    const idx75 = values.indexOf('М75-79');
    const idx80 = values.indexOf('М80+');
    assert.ok(idx75 < idx80, `М75-79 (${idx75}) должен идти раньше М80+ (${idx80})`);
});

// Регрессия (2026-08-23): «Жара» 5 км и 21.1 км — разные схемы категорий
// (5 км — укрупнённая "50-59", 21.1 км — сплит "50-54"/"55-59"), но
// populateAgeGroups() строил список из allRunners без учёта выбранной
// дистанции — на 21.1 км в фильтре висели категории с 5 км, которым там
// физически не соответствовал ни один участник.
const MIXED_DISTANCE_RUNNERS = [
    { gender: 'Женщина', category: 'Ж50-59', event: '5 км' },
    { gender: 'Мужчина', category: 'М50-59', event: '5 км' },
    { gender: 'Женщина', category: 'Ж50-54', event: '21.1 км' },
    { gender: 'Женщина', category: 'Ж55-59', event: '21.1 км' },
    { gender: 'Мужчина', category: 'М50-54', event: '21.1 км' },
];

check('populateAgeGroups() — при выбранной дистанции категории только с неё', () => {
    resetDom();
    domStub('distanceFilter').value = '21.1 км';
    sandbox.populateAgeGroups(MIXED_DISTANCE_RUNNERS);
    const values = domStub('ageGroupFilter').options.map(o => o.value).filter(v => v !== '');

    assert.deepStrictEqual(values, ['Ж50-54', 'Ж55-59', 'М50-54']);
});

check('populateAgeGroups() — без выбранной дистанции категории со всех (не ломаем старое поведение)', () => {
    resetDom();
    domStub('distanceFilter').value = '';
    sandbox.populateAgeGroups(MIXED_DISTANCE_RUNNERS);
    const values = domStub('ageGroupFilter').options.map(o => o.value).filter(v => v !== '');

    assert.deepStrictEqual(values, ['Ж50-59', 'Ж50-54', 'Ж55-59', 'М50-59', 'М50-54']);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
