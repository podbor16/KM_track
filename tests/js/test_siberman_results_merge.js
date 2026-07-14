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

// ── buildRankedEntries()/bikeCombinedTime()/day1Progress()/day2Progress() ──
function mkIndProgress(bib, overrides = {}) {
    return { bib, status: 'active', gender: 'M', cp: {}, swim_s: null, bike1_s: null, bike2_s: null, run_s: null, ...overrides };
}
function mkRelayProgress(bib, membersOverrides) {
    return {
        bib, team_name: `Team${bib}`,
        members: [
            { relay_stage: 'swim', status: 'active', cp: membersOverrides.swimCp ?? {}, swim_s: membersOverrides.swim_s },
            { relay_stage: 'bike', status: 'active', cp: membersOverrides.bikeCp ?? {}, bike1_s: membersOverrides.bike1_s, bike2_s: membersOverrides.bike2_s },
            { relay_stage: 'run', status: 'active', cp: membersOverrides.runCp ?? {}, run_s: membersOverrides.run_s },
        ],
    };
}

check('bikeCombinedTime — сумма bike1+bike2, null если этап не завершён', () => {
    assert.strictEqual(sandbox.bikeCombinedTime({ bike1_s: 100, bike2_s: 200 }), 300);
    assert.strictEqual(sandbox.bikeCombinedTime({ bike1_s: 100, bike2_s: null }), null);
});

check('buildRankedEntries — сортировка по значению, null (не дошедшие/dnf) — в хвост', () => {
    const individual = [
        mkIndProgress(1, { bike1_s: 100, bike2_s: 200 }),        // 300
        mkIndProgress(2, { bike1_s: 50, bike2_s: null }),        // null (ещё не доехал день2)
        mkIndProgress(3, { bike1_s: 40, bike2_s: 60, status: 'dnf' }), // dnf -> null несмотря на времена
    ];
    const relay = [mkRelayProgress(10, { bike1_s: 30, bike2_s: 40 })]; // 70
    const entries = sandbox.buildRankedEntries(individual, relay, sandbox.bikeCombinedTime);
    const order = entries.map(e => e.entry.bib);
    assert.strictEqual(JSON.stringify(order), JSON.stringify([10, 1, 2, 3]), `expected [10,1,2,3], got [${order}]`);
    assert.strictEqual(entries[0].v, 70);
    assert.strictEqual(entries[1].v, 300);
    assert.strictEqual(entries[2].v, null);
});

check('day1Progress/day2Progress используют globalProgress по STAGE_MAX_SEQ', () => {
    // STAGE_MAX_SEQ объявлен как const внутри исполненного скрипта — та же
    // лексическая изоляция, что и у _gender/_fmt, читаем через runInContext.
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqBike2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const row = {
        cp: {
            bike_day1: { [maxSeqBike1]: 5000 },
            bike_day2: { [maxSeqBike2]: 9000 },
        },
        swim_s: 1000, bike1_s: 4000, bike2_s: 8000, run_s: null,
    };
    assert.strictEqual(sandbox.day1Progress(row), 5000);
    // bike_day2 elapsed отсчитывается от старта СВОЕГО этапа -> + swim_s + bike1_s
    assert.strictEqual(sandbox.day2Progress(row), 1000 + 4000 + 9000);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
