// Тест для static/js/tracker-api.js: карточки "DNF"/"DSQ" в общей
// статистике трекера (запрос пользователя 2026-08-23). Раньше единственная
// карточка "Снялись" считала results.filter(r => race_status === 'Disqualifed'
// || race_status === 'Disqualified') — эти строки НИКОГДА не совпадали с
// реальным значением 'DSQ' (см. convert_status() в load_race_results.py),
// а 'DNF' вообще не проверялся — DSQ/DNF участники "терялись" из статистики,
// хотя реально были в БД (найдено на живых данных Жары 21.1км).
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_tracker_analytics_dnf_dsq.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/tracker-api.js'), 'utf-8');

function makeElement() {
    return { textContent: '', innerHTML: '' };
}
const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement();
    return elementsById[id];
}

const sandbox = {
    console,
    document: {
        getElementById: domStub,
        querySelector: () => null,
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(scriptJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

// race_status — реальные значения из convert_status() (не 'Disqualified').
const RESULTS = [
    { race_status: 'Finished',    sex: 'Мужчина' },
    { race_status: 'Not started', sex: 'Женщина' },
    { race_status: 'DSQ',         sex: 'Мужчина' },
    { race_status: 'DSQ',         sex: 'Женщина' },
    { race_status: 'DNF',         sex: 'Мужчина' },
    { race_status: 'Withdrawn',   sex: 'Женщина' },
];

check('renderAnalyticsHTML() — карточка DSQ показывает реальное число DSQ (не 0)', () => {
    const stats = { total: 6, finished: 1, not_started: 1, running: 0, dnf: 2, dsq: 2, male: 3, female: 3 };
    const html = sandbox.renderAnalyticsHTML(stats, []);
    assert.ok(html.includes('>DSQ<'), 'должна быть подпись "DSQ"');
    assert.ok(!html.includes('Снялись'), 'старая подпись "Снялись" не должна остаться');
    // Значение DSQ (2) должно стоять прямо перед подписью "DSQ" карточки
    const dsqCardMatch = html.match(/stat-card-value[^>]*>(\d+)<\/div>\s*<div class="stat-card-label">DSQ</);
    assert.ok(dsqCardMatch, html);
    assert.strictEqual(dsqCardMatch[1], '2');
});

check('renderAnalyticsHTML() — карточка DNF переименована из "Снялись" и показывает реальное число', () => {
    const stats = { total: 6, finished: 1, not_started: 1, running: 0, dnf: 2, dsq: 2, male: 3, female: 3 };
    const html = sandbox.renderAnalyticsHTML(stats, []);
    const dnfCardMatch = html.match(/stat-card-value[^>]*>(\d+)<\/div>\s*<div class="stat-card-label">DNF</);
    assert.ok(dnfCardMatch, html);
    assert.strictEqual(dnfCardMatch[1], '2');
});

check('loadAnalytics()-эквивалентный подсчёт: DSQ/DNF считаются по реальным race_status, не по несуществующим "Disqualified"', () => {
    const stats = {
        total:        RESULTS.length,
        finished:     RESULTS.filter(r => r.race_status === 'Finished').length,
        not_started:  RESULTS.filter(r => r.race_status === 'Not started').length,
        running:      RESULTS.filter(r => r.race_status === 'Running').length,
        dnf:          RESULTS.filter(r => r.race_status === 'DNF' || r.race_status === 'Withdrawn').length,
        dsq:          RESULTS.filter(r => r.race_status === 'DSQ').length,
        male:         RESULTS.filter(r => r.sex === 'Мужчина').length,
        female:       RESULTS.filter(r => r.sex === 'Женщина').length,
    };
    assert.strictEqual(stats.dsq, 2, 'оба DSQ-участника должны быть посчитаны');
    assert.strictEqual(stats.dnf, 2, 'DNF + Withdrawn должны быть посчитаны вместе как DNF');
    assert.strictEqual(stats.total, 6);
});

check('getStatusText() — DSQ и DNF получают собственные читаемые подписи', () => {
    assert.strictEqual(sandbox.getStatusText('DSQ'), 'DSQ');
    assert.strictEqual(sandbox.getStatusText('DNF'), 'DNF');
    assert.strictEqual(sandbox.getStatusText('Withdrawn'), 'DNF');
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
