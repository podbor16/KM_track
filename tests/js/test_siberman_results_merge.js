// Тест buildMergedOverallEntries()/rankBodyCells() из templates/siberman/results.html
// (личники+эстафета в едином порядке, разделение места на абсолют/по полу).
// В проекте нет JS-тест-фреймворка — используется node:vm, тот же паттерн,
// что и для gap-тестов (задача 4 Live v2). Запуск: node tests/js/test_siberman_results_merge.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const commonJs = fs.readFileSync(path.join(ROOT, 'static/js/siberman-common.js'), 'utf-8');
const html = fs.readFileSync(path.join(ROOT, 'templates/siberman/results.html'), 'utf-8');
const inlineScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1])[0];

const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: () => ({ innerHTML: '', style: {}, textContent: '', value: '2025', appendChild: () => {}, addEventListener: () => {} }),
        querySelectorAll: () => [],
        addEventListener: () => {},
        documentElement: { setAttribute: () => {}, getAttribute: () => 'dark' },
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(commonJs, sandbox);
vm.runInContext(inlineScript, sandbox);

// let _gender/_fmt объявлены внутри исполненного скрипта — отдельная
// лексическая привязка, sandbox._gender=... извне её не видит. Мутируем
// через runInContext (тот же персистентный контекст).
function setState(fmt, gender) {
    vm.runInContext(`_fmt = ${JSON.stringify(fmt)}; _gender = ${JSON.stringify(gender)};`, sandbox);
}

let failures = 0;
function check(name, fn) {
    try {
        fn();
        console.log(`OK   ${name}`);
    } catch (e) {
        failures++;
        console.log(`FAIL ${name}: ${e.message}`);
    }
}

function mkInd(bib, overall_s, status = 'active') {
    return { bib, overall_s, status, gender: 'M', cp: {} };
}
function mkRelay(bib, overall_s) {
    return { bib, overall_s, team_name: `Team${bib}`, members: [] };
}

check('интерливинг личников и эстафеты по overall_s (fmt=all)', () => {
    setState('all', 'all');
    const individual = [mkInd(1, 100), mkInd(2, 300)];
    const relay = [mkRelay(10, 200)];
    const merged = sandbox.buildMergedOverallEntries(individual, relay);
    const order = merged.map(e => e.entry.bib);
    assert.strictEqual(JSON.stringify(order), JSON.stringify([1, 10, 2]), `expected [1,10,2], got [${order}]`);
});

check('не финишировавшие и эстафета без результата — в хвосте', () => {
    setState('all', 'all');
    const individual = [mkInd(1, 100), mkInd(2, null, 'dnf')];
    const relay = [mkRelay(10, null), mkRelay(11, 50)];
    const merged = sandbox.buildMergedOverallEntries(individual, relay);
    const order = merged.map(e => e.entry.bib);
    assert.strictEqual(JSON.stringify(order), JSON.stringify([11, 1, 2, 10]), `expected [11,1,2,10], got [${order}]`);
});

check('fmt=individual — эстафета не подмешивается', () => {
    setState('individual', 'all');
    const individual = [mkInd(1, 100)];
    const relay = [];
    const merged = sandbox.buildMergedOverallEntries(individual, relay);
    assert.strictEqual(merged.length, 1);
    assert.strictEqual(merged[0].type, 'individual');
});

check('rankBodyCells порядок меняется местами по _gender', () => {
    setState('all', 'all');
    const allHtml = sandbox.rankBodyCells(5, 2, 'M', '');
    const idxAll5 = allHtml.indexOf('5</span>');
    const idxAll2 = allHtml.indexOf('2</span>');
    assert.ok(idxAll5 < idxAll2, `при _gender=all абсолют (5) должен идти раньше по-полу (2); html=${allHtml}`);

    setState('all', 'M');
    const genderHtml = sandbox.rankBodyCells(5, 2, 'M', '');
    const idx2 = genderHtml.indexOf('2</span>');
    const idx5 = genderHtml.indexOf('5</span>');
    assert.ok(idx2 < idx5, `при _gender=M по-полу (2) должен идти раньше абсолюта (5); html=${genderHtml}`);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
