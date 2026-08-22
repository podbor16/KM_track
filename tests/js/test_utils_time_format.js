// Тест для static/js/utils.js: единый формат времени по проекту — меньше
// часа → "M:SS", час и больше → "H:MM:SS" (запрос пользователя 2026-08-22,
// найдено на живой карточке трекера: "0:22:48" вместо ожидаемого "22:48").
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_utils_time_format.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const utilsJs = fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8');

const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(utilsJs, sandbox);
const KMUtils = sandbox.window.KMUtils;

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('formatTime() — "H:MM:SS" с нулевым часом сворачивается в "M:SS"', () => {
    assert.strictEqual(KMUtils.formatTime('0:22:48'), '22:48');
});
check('formatTime() — "HH:MM:SS" с нулевым часом (ведущий 0) тоже сворачивается', () => {
    assert.strictEqual(KMUtils.formatTime('00:05:23'), '5:23');
});
check('formatTime() — час и больше остаётся "H:MM:SS"', () => {
    assert.strictEqual(KMUtils.formatTime('1:05:03'), '1:05:03');
});
check('formatTime() — ISO 8601 PT-строка < часа → "M:SS"', () => {
    assert.strictEqual(KMUtils.formatTime('PT22M48S'), '22:48');
});
check('formatTime() — ISO 8601 PT-строка >= часа → "H:MM:SS"', () => {
    assert.strictEqual(KMUtils.formatTime('PT1H5M3S'), '1:05:03');
});
check('formatTime() — уже сокращённая "M:SS" остаётся без изменений', () => {
    assert.strictEqual(KMUtils.formatTime('4:33'), '4:33');
});
check('formatTime() — null/пусто → "-"', () => {
    assert.strictEqual(KMUtils.formatTime(null), '-');
    assert.strictEqual(KMUtils.formatTime(''), '-');
});
check('parseDuration() — тот же формат, что и formatTime, для "H:MM:SS"', () => {
    assert.strictEqual(KMUtils.parseDuration('0:22:48'), '22:48');
    assert.strictEqual(KMUtils.parseDuration('1:05:03'), '1:05:03');
});
check('parseTimeToSeconds() — понимает короткий "M:SS" (регрессия: раньше отдавал Infinity для < 1 часа)', () => {
    assert.strictEqual(KMUtils.parseTimeToSeconds('5:45'), 345);
    assert.strictEqual(KMUtils.parseTimeToSeconds('22:48'), 1368);
});
check('parseTimeToSeconds() — "H:MM:SS" и пустое/некорректное значение (Infinity — сортировка уносит в конец)', () => {
    assert.strictEqual(KMUtils.parseTimeToSeconds('1:05:03'), 3903);
    assert.strictEqual(KMUtils.parseTimeToSeconds(null), Infinity);
    assert.strictEqual(KMUtils.parseTimeToSeconds(''), Infinity);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
