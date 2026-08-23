// Тест для static/js/analytics-results.js: живое "Место" на /results до
// финиша (запрос пользователя 2026-08-23, день гонки 21.1 км Жары) — почти
// как на Siberman. Три состояния:
//   1. Пока ни у одного участника нет ни одной пройденной КТ — сортировка
//      по алфавиту, "Место" = "—".
//   2. Как только участнику засчитана первая КТ — он получает живое место
//      (по current_distance, та же величина, что двигает маркер на
//      трекере), сразу занимает верх списка.
//   3. Финишировавшие — официальное место (rank_absolute/rank_sex/
//      rank_category с сервера) не трогается, живое место не считается.
//   DNF/DSQ — отдельной группой после бегущих (решение пользователя).
//   Живое место, как и официальное, считается отдельно по полу/категории
//   (не только абсолютное) — решение пользователя.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_live_rank.js
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

function mkRunner(surname, opts = {}) {
    return Object.assign({
        surname, name: 'Т', gender: 'Мужчина', category: 'М18-49',
        status: 'notstarted', current_distance: 0, last_kt_unix_ms: null,
    }, opts);
}

check('до первой отметки — все в тире "алфавит" (3)', () => {
    const runners = [mkRunner('Яковлев'), mkRunner('Абрамов'), mkRunner('Викулова')];
    sandbox._computeLiveRanks(runners);
    runners.forEach(r => assert.strictEqual(sandbox._liveRankTier(r), 3));
});

check('первая КТ пришла — только у неё тир "живой прогресс" (1), у остальных без КТ — тир 3', () => {
    const withKt = mkRunner('Абрамов', { status: 'running', current_distance: 5.1, last_kt_unix_ms: 1000 });
    const noKt = mkRunner('Яковлев', { status: 'running', current_distance: 0.3, last_kt_unix_ms: null }); // только оценка темпа, реальной КТ нет
    assert.strictEqual(sandbox._liveRankTier(withKt), 1);
    assert.strictEqual(sandbox._liveRankTier(noKt), 3);
});

check('живое место = 1 у единственного с прогрессом', () => {
    const runners = [
        mkRunner('Абрамов', { status: 'running', current_distance: 5.1, last_kt_unix_ms: 1000 }),
    ];
    sandbox._computeLiveRanks(runners);
    assert.strictEqual(runners[0].live_rank_absolute, 1);
});

check('двое с прогрессом — впереди тот, кто дальше по дистанции', () => {
    const runners = [
        mkRunner('Абрамов', { status: 'running', current_distance: 5.1, last_kt_unix_ms: 1000 }),
        mkRunner('Белов',   { status: 'running', current_distance: 10.4, last_kt_unix_ms: 2000 }),
    ];
    sandbox._computeLiveRanks(runners);
    assert.strictEqual(runners[1].live_rank_absolute, 1);
    assert.strictEqual(runners[0].live_rank_absolute, 2);
});

check('финишировавший — тир 0, официальное место не трогается, live_rank не проставляется', () => {
    const runners = [mkRunner('Финишер', { status: 'finished', rank_absolute: 1, current_distance: 21.1 })];
    sandbox._computeLiveRanks(runners);
    assert.strictEqual(sandbox._liveRankTier(runners[0]), 0);
    assert.strictEqual(runners[0].live_rank_absolute, undefined);
});

check('DNF после прохождения КТ — отдельный тир (2), после бегущих (1), перед не стартовавшими (3)', () => {
    const dnf = mkRunner('Сошедший', { status: 'dnf', current_distance: 10, last_kt_unix_ms: 500 });
    const running = mkRunner('Бегущий', { status: 'running', current_distance: 3, last_kt_unix_ms: 100 });
    const notStarted = mkRunner('НеСтартовал');
    assert.strictEqual(sandbox._liveRankTier(running), 1);
    assert.strictEqual(sandbox._liveRankTier(dnf), 2);
    assert.strictEqual(sandbox._liveRankTier(notStarted), 3);
});

check('живое место по полу/категории считается внутри своей подгруппы (решение пользователя)', () => {
    const runners = [
        mkRunner('Иванова', { status: 'running', current_distance: 8,  last_kt_unix_ms: 1, gender: 'Женщина', category: 'Ж18-49' }),
        mkRunner('Петрова', { status: 'running', current_distance: 5,  last_kt_unix_ms: 1, gender: 'Женщина', category: 'Ж18-49' }),
        mkRunner('Сидоров', { status: 'running', current_distance: 20, last_kt_unix_ms: 1, gender: 'Мужчина', category: 'М18-49' }),
    ];
    sandbox._computeLiveRanks(runners);
    assert.strictEqual(runners[0].live_rank_sex, 1); // Иванова 1я среди женщин, хотя Сидоров абсолютно дальше
    assert.strictEqual(runners[1].live_rank_sex, 2);
    assert.strictEqual(runners[2].live_rank_sex, 1); // Сидоров 1й среди мужчин (своя группа)
    assert.strictEqual(runners[2].live_rank_absolute, 1); // абсолютно Сидоров(20км) впереди Ивановой(8км)
    assert.strictEqual(runners[0].live_rank_absolute, 2);
});

check('_sortArray() дефолтным видом (time_gun): финишер → бегущие по прогрессу → DNF → не стартовавшие по алфавиту', () => {
    const runners = [
        mkRunner('Яковлев', { status: 'notstarted' }),
        mkRunner('Абрамов', { status: 'running', current_distance: 5.1, last_kt_unix_ms: 1000 }),
        mkRunner('Белов',   { status: 'running', current_distance: 10.4, last_kt_unix_ms: 2000 }),
        mkRunner('Финишер', { status: 'finished', rank_absolute: 1, time_gun_finish: '0:45:00' }),
        mkRunner('Сошедший', { status: 'dnf' }),
    ];
    sandbox._computeLiveRanks(runners);
    domStub('genderFilter').dataset.value = '';
    domStub('ageGroupFilter').value = '';
    vm.runInContext(`sortState = { column: 'time_gun', direction: 'asc' };`, sandbox);
    const sorted = sandbox._sortArray(runners).map(r => r.surname);
    assert.strictEqual(
        JSON.stringify(sorted),
        JSON.stringify(['Финишер', 'Белов', 'Абрамов', 'Сошедший', 'Яковлев']),
    );
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
