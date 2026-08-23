// Тест для static/js/analytics-results.js: дистанции КТ в графике темпа
// по отрезкам / таблице сплитов на /results теперь берутся из реального
// конфига события (checkpoints[].distance_km), а не из производной оценки
// по time/pace. Найдено пользователем 2026-08-23: отметка KT1, ровно 5.0 км
// по конфигу, показывалась как "5.02 км" — оценка по темпу лишь
// АППРОКСИМИРУЕТ километраж, конфиг даёт точное значение.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_analytics_results_segment_km_from_config.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/analytics-results.js'), 'utf-8');

function makeSimpleElement() { return { value: '', dataset: {}, style: {} }; }
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeSimpleElement();
    return elementsById[id];
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: domStub,
        createElement: () => makeSimpleElement(),
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

// Реальная схема Жары 21.1 км — KT1 РОВНО 5.0 км, не 5.02.
const DISTANCES_CFG = [
    {
        distance: '21.1 км',
        checkpoints: [
            { name: 'Старт', distance_km: 0 },
            { name: 'КТ1', distance_km: 5.0 },
            { name: 'КТ2', distance_km: 6.0 },
            { name: 'КТ3', distance_km: 10.55 },
            { name: 'КТ4', distance_km: 14.65 },
            { name: 'КТ5', distance_km: 15.65 },
            { name: 'КТ6', distance_km: 20.2 },
            { name: 'Финиш', distance_km: 21.1 },
        ],
    },
];
vm.runInContext('_liveEventDistances = ' + JSON.stringify(DISTANCES_CFG) + ';', sandbox);

check('_configCheckpointsForDistance() находит дистанцию по метке', () => {
    const cps = sandbox._configCheckpointsForDistance('21.1 км');
    assert.ok(cps, 'должен найти checkpoints для "21.1 км"');
    assert.strictEqual(cps[1].distance_km, 5.0);
});

check('_configCheckpointsForDistance() — null для неизвестной/неактивной дистанции', () => {
    assert.strictEqual(sandbox._configCheckpointsForDistance('100 км'), null);
    assert.strictEqual(sandbox._configCheckpointsForDistance(null), null);
});

check('buildKmMap() с конфигом — точное значение 5 (не 5.02) для KT1', () => {
    const configCps = sandbox._configCheckpointsForDistance('21.1 км');
    // Сегменты с сырыми временем/темпом, которые раньше давали НЕТОЧНОЕ 5.02
    // при делении time/pace — теперь конфиг должен победить целиком.
    const segments = [
        { segment_code: 'start-kt1', sg_time_clear: '0:16:25', sg_pace_avg: '3:17' },
    ];
    const map = sandbox.buildKmMap(segments, configCps);
    assert.strictEqual(map.kt1, 5.0);
    assert.strictEqual(map.kt6, 20.2);
    assert.strictEqual(map.finish, 21.1);
});

check('buildKmMap() без конфига (фоллбэк) — прежняя производная оценка по time/pace работает как раньше', () => {
    const segments = [
        { segment_code: 'start-kt1', sg_time_clear: '0:16:25', sg_pace_avg: '3:17' },
    ];
    const map = sandbox.buildKmMap(segments, null);
    assert.ok(map.kt1 > 4.9 && map.kt1 < 5.1, `ожидали значение около 5, получили ${map.kt1}`);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
