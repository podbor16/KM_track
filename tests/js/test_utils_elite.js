// «Элита» (2026-10-06): KMUtils.bibLabel / eliteFirst / eliteFilterSync.
// Запуск: node tests/js/test_utils_elite.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const els = {};
const el = () => {
    const set = new Set();
    return { style: {}, classList: { add: c => set.add(c), remove: c => set.delete(c), contains: c => set.has(c) } };
};
const sandbox = { document: { getElementById: id => (els[id] = els[id] || el()), currentScript: null }, URL, window: {} };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'static/js/utils.js'), 'utf-8'), sandbox);
const U = sandbox.window.KMUtils;

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); } catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('bibLabel — «Элита» вместо номера у элиты, номер у остальных', () => {
    assert.strictEqual(U.bibLabel(1515, 1), 'Элита');
    assert.strictEqual(U.bibLabel(343, 0), '343');
    assert.strictEqual(U.bibLabel(null, 0), '');
});
check('eliteFirst — элита первой, затем остальные (алфавит внутри — у вызывающего)', () => {
    const rows = [{ s: 'Б' }, { s: 'Я', is_elite: 1 }, { s: 'А' }, { s: 'В', is_elite: 1 }];
    rows.sort((a, b) => U.eliteFirst(a, b) || a.s.localeCompare(b.s, 'ru'));
    assert.deepStrictEqual(rows.map(r => r.s), ['В', 'Я', 'А', 'Б']);
});
check('eliteFilterSync — фильтр виден только при элите на дистанции; без элиты сбрасывается', () => {
    assert.strictEqual(U.eliteFilterSync([{ is_elite: 0 }]), false);
    assert.strictEqual(els.eliteFilterGroup.style.display, 'none');
    assert.strictEqual(U.eliteFilterSync([{ is_elite: 1 }]), false);          // виден, но не включён
    assert.strictEqual(els.eliteFilterGroup.style.display, '');
    els.eliteFilter.classList.add('active');
    assert.strictEqual(U.eliteFilterSync([{ is_elite: 1 }]), true);
    assert.strictEqual(U.eliteFilterSync([{ is_elite: 0 }]), false);         // сменили дистанцию — сброс
    assert.ok(!els.eliteFilter.classList.contains('active'));
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
