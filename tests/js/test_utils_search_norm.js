// Тест KMUtils.searchNorm(): поиск по ФИО без учёта регистра и «ё»/«е».
// Запуск: node tests/js/test_utils_search_norm.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const sandbox = { console, window: {} };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8'), sandbox);
const norm = (s) => vm.runInContext(`KMUtils.searchNorm(${JSON.stringify(s)})`, sandbox);

assert.strictEqual(norm('  Семёнов '), 'семенов');
assert.strictEqual(norm('СЁМИН'), 'семин');
assert.strictEqual(norm(null), '');
assert.ok(norm('Семёнова').startsWith(norm('Семен')));
console.log('ALL PASSED');
