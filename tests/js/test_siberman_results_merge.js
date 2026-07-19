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

// getElementById('app') должен возвращать ОДИН и тот же объект при каждом
// вызове (не новый) — иначе рендер-функции пишут innerHTML в объект, который
// тест-код уже никогда не увидит (та же ловушка, что и с let-переменными в
// vm-контексте, но для DOM-стабов).
const elementsById = {};
function domStub(id) {
    if (id && elementsById[id]) return elementsById[id];
    const el = { innerHTML: '', style: {}, textContent: '', value: '2025', appendChild: () => {}, addEventListener: () => {}, dataset: {}, querySelector: () => domStub(), getContext: () => ({}) };
    if (id) elementsById[id] = el;
    return el;
}
// Chart.js стаб — рендер-функции графиков (renderPaceChart/renderPositionChart)
// создают `new Chart(...)`, без стаба падают с ReferenceError.
class ChartStub {
    constructor(ctx, config) { this.config = config; this.options = config.options || {}; }
    destroy() {}
    getDatasetMeta() { return { data: [] }; }
    update() {}
}
const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: (id) => domStub(id),
        querySelectorAll: () => [],
        querySelector: () => domStub(),
        addEventListener: () => {},
        documentElement: { setAttribute: () => {}, getAttribute: () => 'dark' },
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    setInterval: () => 0,
    clearInterval: () => {},
    getComputedStyle: () => ({ getPropertyValue: () => '#6AABD7' }),
    Chart: ChartStub,
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

// ── Живой секундомер этапа: stageStartOffset()/stageIsPending()/computeActiveStageTimers() ──
// _data/_raceStartEpoch объявлены как let внутри исполненного скрипта —
// та же лексическая изоляция, что и _gender/_fmt (см. setState выше).
function setRaceData(individual, relay, raceStartEpoch) {
    sandbox.__individual = individual;
    sandbox.__relay = relay;
    sandbox.__raceStartEpoch = raceStartEpoch;
    vm.runInContext('_data = { individual: __individual, relay: __relay }; _raceStartEpoch = __raceStartEpoch;', sandbox);
}
function mkTimerInd(bib, overrides = {}) {
    return { bib, status: 'active', gender: 'M', cp: {}, swim_s: null, bike1_s: null, bike2_s: null, run_s: null, ...overrides };
}

check('stageStartOffset — swim всегда 0, bike_day1 = min swim_s среди дошедших', () => {
    setRaceData([mkTimerInd(1, { swim_s: 3000 }), mkTimerInd(2, { swim_s: 2500 }), mkTimerInd(3, { swim_s: null })], [], Date.now());
    assert.strictEqual(sandbox.stageStartOffset('swim'), 0);
    assert.strictEqual(sandbox.stageStartOffset('bike_day1'), 2500);
});

check('stageStartOffset — этап без единого дошедшего участника ещё не начался (null)', () => {
    setRaceData([mkTimerInd(1, { swim_s: null })], [], Date.now());
    assert.strictEqual(sandbox.stageStartOffset('bike_day1'), null);
});

check('stageIsPending — false, когда все участники этапа финишировали/сошли', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const finished = mkTimerInd(1, { cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    const dnf = mkTimerInd(2, { status: 'dnf' });
    setRaceData([finished, dnf], [], Date.now());
    assert.strictEqual(sandbox.stageIsPending('swim'), false);
});

check('stageIsPending — true, пока хотя бы один активный участник не дошёл до последней КТ этапа', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const finished = mkTimerInd(1, { cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    const stillSwimming = mkTimerInd(2, { cp: { swim: { 1: 500 } } });
    setRaceData([finished, stillSwimming], [], Date.now());
    assert.strictEqual(sandbox.stageIsPending('swim'), true);
});

check('computeStageTimerState — единый таймер «День 1», пока хотя бы плавание ИЛИ вело1 не закрыты', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const now = Date.now();
    // Один уже уехал на вело1 (заплыв закрыт для него), второй ещё плывёт —
    // день 1 в целом всё ещё "активен", отдельного таймера на вело1 нет.
    const finishedSwim = mkTimerInd(1, { cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    const stillSwimming = mkTimerInd(2, { cp: { swim: { 1: 500 } } });
    setRaceData([finishedSwim, stillSwimming], [], now - 100000);
    const state = sandbox.computeStageTimerState();
    assert.strictEqual(state.type, 'timer');
    assert.strictEqual(state.label, 'День 1');
});

check('computeStageTimerState — «Следующий этап Вело День 2», когда день 1 закрыт (все доплывшие сошли до вело1), а вело2 ещё не начался', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const now = Date.now();
    // Доплыл, но снялся до старта вело1 — bike1_s так и не проставлен, значит
    // формально "не вошёл" в вело2 (см. STAGE_PRIOR_KEYS/stageEntryOffset).
    const dnfAfterSwim = mkTimerInd(1, { status: 'dnf', cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    setRaceData([dnfAfterSwim], [], now - 100000);
    const state = sandbox.computeStageTimerState();
    assert.strictEqual(state.type, 'next');
    assert.strictEqual(state.label, 'Вело День 2');
});

check('computeStageTimerState — «Гонка завершена», когда все закончили бег (dnf/финиш)', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqBike2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    const now = Date.now();
    const finished = mkTimerInd(1, {
        cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { [maxSeqBike1]: 9000 }, bike_day2: { [maxSeqBike2]: 8000 }, run: { [maxSeqRun]: 2000 } },
        swim_s: 3000, bike1_s: 9000, bike2_s: 8000, run_s: 2000,
    });
    const dnfOnRun = mkTimerInd(2, {
        status: 'dnf',
        cp: { swim: { [maxSeqSwim]: 3100 }, bike_day1: { [maxSeqBike1]: 9100 }, bike_day2: { [maxSeqBike2]: 8100 }, run: { 3: 500 } },
        swim_s: 3100, bike1_s: 9100, bike2_s: 8100,
    });
    setRaceData([finished, dnfOnRun], [], now - 100000);
    const state = sandbox.computeStageTimerState();
    assert.strictEqual(state.type, 'done');
});

// ── Графики: buildPaceDatasets()/buildPositionDatasets() ──
check('buildPaceDatasets — точки по реальным КТ (X=км этапа, Y=темп/скорость), участники без сплитов не попадают', () => {
    setState('all', 'all');
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const withSplits = mkTimerInd(1, { splits: { bike_day1: { 1: 600, 2: 1200 } } }); // 3км/600с, 7км/1200с
    const noSplits = mkTimerInd(2, { splits: {} });
    setRaceData([withSplits, noSplits], [], Date.now());
    const datasets = sandbox.buildPaceDatasets('bike1');
    assert.strictEqual(datasets.length, 1, `ожидался 1 датасет (только с данными), получено ${datasets.length}`);
    assert.strictEqual(datasets[0]._bib, 1);
    assert.strictEqual(datasets[0].data[1].x, 3); // CHECKPOINT_DIST_KM.bike_day1[1] — вторая точка, первая реальная КТ
    assert.ok(datasets[0].data[1].y > 0, 'скорость должна быть положительным числом');
});
check('buildPaceDatasets — добавляет экстраполированную точку x=0 (первая КТ не с начала этапа)', () => {
    setState('all', 'all');
    const withSplits = mkTimerInd(1, { splits: { bike_day1: { 1: 600 } } });
    setRaceData([withSplits], [], Date.now());
    const datasets = sandbox.buildPaceDatasets('bike1');
    assert.strictEqual(datasets[0].data[0].x, 0, 'первая точка должна быть на x=0');
    assert.strictEqual(datasets[0].data[0].y, datasets[0].data[1].y, 'экстраполированная точка должна иметь то же Y, что первая реальная КТ');
});

check('buildPositionDatasets — X учитывает STAGE_KM_OFFSET, Y = глобальное место на КТ', () => {
    setState('all', 'all');
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const offsetBike1 = vm.runInContext('STAGE_KM_OFFSET.bike_day1', sandbox);
    const a = mkTimerInd(1, { cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { 1: 400 } }, swim_s: 3000 });
    const b = mkTimerInd(2, { cp: { swim: { [maxSeqSwim]: 3200 }, bike_day1: { 1: 500 } }, swim_s: 3200 });
    setRaceData([a, b], [], Date.now());
    const datasets = sandbox.buildPositionDatasets();
    assert.strictEqual(datasets.length, 2);
    const distTable = vm.runInContext('CHECKPOINT_DIST_KM.bike_day1', sandbox);
    const bike1PointA = datasets.find(d => d._bib === 1).data.find(p => p.x === offsetBike1 + distTable[1]);
    assert.ok(bike1PointA, 'ожидалась точка на bike_day1 seq=1 со смещением STAGE_KM_OFFSET.bike_day1');
    assert.strictEqual(bike1PointA.y, 1); // участник 1 пришёл на эту КТ первым (globalProgress меньше)
});

// ── computeCombinedOverallRanks() / combinedOverallRankRows() — единое место
// личники+эстафета вместе (п.14 задачи 2026-07-19: раньше личники (rank_overall
// из БД) и эстафета (relayPos-счётчик в разметке) ранжировались раздельно,
// что давало дублирующиеся места "1, 1, 2, 2..." при интерливинге ──
check('computeCombinedOverallRanks — единая последовательность 1,2,3... без дублей', () => {
    const individual = [mkInd(1, 22 * 3600), mkInd(2, 23 * 3600)];
    const relay = [mkRelay(10, 22.2 * 3600)]; // между личником 1 и 2 по времени
    const rows = sandbox.combinedOverallRankRows(individual, relay);
    const ranks = sandbox.computeCombinedOverallRanks(rows);
    assert.strictEqual(JSON.stringify(ranks), JSON.stringify({ 1: 1, 10: 2, 2: 3 }));
});

check('computeCombinedOverallRanks — не финишировавшие (null/dnf) не получают место', () => {
    const individual = [mkInd(1, 100), mkInd(2, null, 'dnf')];
    const relay = [mkRelay(10, null)];
    const rows = sandbox.combinedOverallRankRows(individual, relay);
    const ranks = sandbox.computeCombinedOverallRanks(rows);
    assert.strictEqual(JSON.stringify(ranks), JSON.stringify({ 1: 1 }));
});

// ── computeAutoScrollTab() — п.1 задачи 2026-07-19 (визуальный скролл
// табов до активного этапа, независимо от секундомера) ──
check('computeAutoScrollTab — плавание ещё активно -> swim', () => {
    const stillSwimming = mkTimerInd(1, { cp: { swim: { 1: 500 } } });
    setRaceData([stillSwimming], [], Date.now());
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'swim');
});

check('computeAutoScrollTab — плавание закрыто, вело1 активно -> bike', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const a = mkTimerInd(1, { cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { 1: 500 } }, swim_s: 3000 });
    setRaceData([a], [], Date.now());
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'bike');
});

check('computeAutoScrollTab — вело1 закрыт, вело2 не начался -> startlist', () => {
    // "Вело1 закрыт" при "вело2 не начался" данными представимо только через
    // сход ДО вело1 (dnf во время/после плавания, bike1_s так и не
    // проставлен) — иначе bike1_s сам по себе уже означал бы "вошёл в вело2"
    // (см. stageEntryOffset/STAGE_PRIOR_KEYS, тот же нюанс что и в тесте
    // computeStageTimerState выше).
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const a = mkTimerInd(1, { status: 'dnf', cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    setRaceData([a], [], Date.now());
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'startlist');
});

check('computeAutoScrollTab — вело2 активно -> bike', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const a = mkTimerInd(1, {
        cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { [maxSeqBike1]: 9000 }, bike_day2: { 1: 500 } },
        swim_s: 3000, bike1_s: 9000,
    });
    setRaceData([a], [], Date.now());
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'bike');
});

check('computeAutoScrollTab — бег ещё не начался (никто не вошёл) -> run', () => {
    // Аналогично — bike2_s не проставлен (сошёл во время вело2, не завершив),
    // иначе он сам по себе означал бы "вошёл в бег".
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const a = mkTimerInd(1, {
        status: 'dnf',
        cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { [maxSeqBike1]: 9000 }, bike_day2: { 3: 1000 } },
        swim_s: 3000, bike1_s: 9000,
    });
    setRaceData([a], [], Date.now());
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'run');
});

check('computeAutoScrollTab — бег активен -> run', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqBike2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const a = mkTimerInd(1, {
        cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { [maxSeqBike1]: 9000 }, bike_day2: { [maxSeqBike2]: 8000 }, run: { 3: 500 } },
        swim_s: 3000, bike1_s: 9000, bike2_s: 8000,
    });
    setRaceData([a], [], Date.now());
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'run');
});

check('computeAutoScrollTab — гонка полностью завершена -> overall', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqBike2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    const a = mkTimerInd(1, {
        cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { [maxSeqBike1]: 9000 }, bike_day2: { [maxSeqBike2]: 8000 }, run: { [maxSeqRun]: 2000 } },
        swim_s: 3000, bike1_s: 9000, bike2_s: 8000, run_s: 2000,
    });
    setRaceData([a], [], Date.now());
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'overall');
});

// ── kmToVirtualX()/virtualXToKm() — пропорциональный X графика «Позиция»
// (п.7.4): плавание 20% / вело 50% / бег 30% ширины, не реальный км ──
check('kmToVirtualX — границы сегментов (0/10/431/515 км -> 0/20/70/100%)', () => {
    assert.strictEqual(sandbox.kmToVirtualX(0), 0);
    assert.strictEqual(sandbox.kmToVirtualX(10), 20);
    assert.strictEqual(sandbox.kmToVirtualX(431), 70);
    assert.strictEqual(sandbox.kmToVirtualX(515), 100);
});
check('kmToVirtualX — середина сегмента плавания (5 км -> 10%)', () => {
    assert.strictEqual(sandbox.kmToVirtualX(5), 10);
});
check('virtualXToKm — обратное преобразование (round-trip)', () => {
    [0, 3, 10, 50, 155, 300, 431, 480, 515].forEach(km => {
        const roundTripped = sandbox.virtualXToKm(sandbox.kmToVirtualX(km));
        assert.ok(Math.abs(roundTripped - km) < 0.001, `${km} км round-trip дал ${roundTripped}`);
    });
});

// ── chartToggleSelect()/chartCompareColor() — мультивыбор для сравнения
// (п.7.2), без лимита на число (снят 2026-07-19), порядок = порядок выбора ──
function resetChartSelection() {
    vm.runInContext('_chartSelectedBibs = [];', sandbox);
}
check('chartToggleSelect — добавление сохраняет порядок выбора, не сортирует по bib', () => {
    resetChartSelection();
    sandbox.chartToggleSelect(30);
    sandbox.chartToggleSelect(5);
    sandbox.chartToggleSelect(17);
    const selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(JSON.stringify(selected), JSON.stringify([30, 5, 17]));
});
check('chartToggleSelect — повторный вызов на тот же bib снимает выбор', () => {
    resetChartSelection();
    sandbox.chartToggleSelect(30);
    sandbox.chartToggleSelect(30);
    const selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(selected.length, 0);
});
check('chartToggleSelect — без лимита, 5+ участников можно выбрать одновременно', () => {
    resetChartSelection();
    [1, 2, 3, 4, 5, 6].forEach(bib => sandbox.chartToggleSelect(bib));
    const selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(JSON.stringify(selected), JSON.stringify([1, 2, 3, 4, 5, 6]));
});
check('chartCompareColor — переиспользует палитру по кругу для 5-го и далее (без лимита)', () => {
    const c0 = sandbox.chartCompareColor(0);
    const c4 = sandbox.chartCompareColor(4); // 5-й участник (индекс 4) — тот же цвет, что 1-й (индекс 0)
    assert.strictEqual(c0, c4);
});
check('chartCompareColor — детерминирован по слоту, не зависит от вызова дважды подряд', () => {
    const c0a = sandbox.chartCompareColor(0);
    const c0b = sandbox.chartCompareColor(0);
    const c1 = sandbox.chartCompareColor(1);
    assert.strictEqual(c0a, c0b);
    assert.notStrictEqual(c0a, c1);
});

// ── computeRanksByValue() — общий примитив (баг-фикс дублирующихся мест
// на табах этапов, найден пользователем после хардрефреша: личники брали
// ранг из БД (только среди личников), эстафетчики — свой отдельный
// relayPos-счётчик; при интерливинге получались "1, 1, 2, 2...") ──
check('computeRanksByValue — произвольное поле val (не только overall_s), общий примитив', () => {
    const rows = [
        { key: 'a', val: 300, status: 'active' },
        { key: 'b', val: 100, status: 'active' },
        { key: 'c', val: 200, status: 'active' },
    ];
    const ranks = sandbox.computeRanksByValue(rows);
    assert.strictEqual(JSON.stringify(ranks), JSON.stringify({ b: 1, c: 2, a: 3 }));
});
check('computeRanksByValue — личник и эстафетчик с близкими временами на этапе не дублируют место', () => {
    // Ровно сценарий со скриншота: bib=1 личник 0:35:01, bib=1000:swim
    // эстафетчик 2:16:10 — единый пул, разные места (не оба "1").
    const rows = [
        { key: 1, val: 2101, status: 'active', gender: 'M' },
        { key: '1000:swim', val: 8170, status: 'active', gender: 'M' },
        { key: 2, val: 8647, status: 'active', gender: 'M' },
    ];
    const ranks = sandbox.computeRanksByValue(rows);
    assert.strictEqual(JSON.stringify(ranks), JSON.stringify({ 1: 1, '1000:swim': 2, 2: 3 }));
});
check('computeRanksByValue — раздельные ранги по полу (личник+эстафетчик одного пола вместе)', () => {
    const rows = [
        { key: 1, val: 100, status: 'active', gender: 'M' },
        { key: '10:swim', val: 150, status: 'active', gender: 'M' },
        { key: 2, val: 50, status: 'active', gender: 'F' },
    ];
    const maleRanks = sandbox.computeRanksByValue(rows.filter(r => r.gender === 'M'));
    const femaleRanks = sandbox.computeRanksByValue(rows.filter(r => r.gender === 'F'));
    assert.strictEqual(JSON.stringify(maleRanks), JSON.stringify({ 1: 1, '10:swim': 2 }));
    assert.strictEqual(JSON.stringify(femaleRanks), JSON.stringify({ 2: 1 }));
});

// ── rankHeaderCells()/rankBodyCells(teamLevel) — скрывать "По полу" при
// активном фильтре формата "Эстафета" в командных контекстах (Итоги гонки,
// Свод вело), т.к. у команды на этом уровне нет единого пола (запрошено
// пользователем 2026-07-19) ──
check('rankHeaderCells(true) — одна колонка "Место" при fmt=relay', () => {
    setState('relay', 'all');
    assert.strictEqual(sandbox.rankHeaderCells(true), '<th>Место</th>');
});
check('rankHeaderCells(true) — обе колонки при fmt!==relay (не затронуто)', () => {
    setState('all', 'all');
    assert.strictEqual(sandbox.rankHeaderCells(true), '<th>Место</th><th>По полу</th>');
});
check('rankHeaderCells() без teamLevel — не схлопывается даже при fmt=relay (табы этапов)', () => {
    setState('relay', 'all');
    assert.strictEqual(sandbox.rankHeaderCells(), '<th>Место</th><th>По полу</th>');
});
check('rankBodyCells(..., true) — одна ячейка при fmt=relay', () => {
    setState('relay', 'all');
    const html = sandbox.rankBodyCells(5, null, null, '', true);
    assert.strictEqual(html, '<td><span class="rank-num ">5</span></td>');
});

// ── bikeCombinedRelayRider()/renderBikeCombined — место по полу + скорость
// в своде вело (421 км), запрошено пользователем 2026-07-19. Эстафета
// показывается как РЕАЛЬНЫЙ велосипедист команды (один и тот же человек
// едет оба дня), не как безликая команда — у него есть личный пол/место. ──
function mkBikeRelay(bib, overrides) {
    return {
        bib, team_name: `Team${bib}`,
        members: [
            { relay_stage: 'bike', status: overrides.status ?? 'active', surname: overrides.surname, name: overrides.name, gender: overrides.gender, bike1_s: overrides.bike1_s, bike2_s: overrides.bike2_s },
        ],
    };
}
check('bikeCombinedRelayRider — реальные ФИО/пол велосипедиста, не название команды', () => {
    const team = mkBikeRelay(1000, { surname: 'Иванов', name: 'Пётр', gender: 'M', bike1_s: 100, bike2_s: 200 });
    const rider = sandbox.bikeCombinedRelayRider(team);
    assert.strictEqual(rider.bib, 1000);
    assert.strictEqual(rider.surname, 'Иванов');
    assert.strictEqual(rider.gender, 'M');
    assert.strictEqual(rider.team_name, 'Team1000');
});
check('renderBikeCombined() — эстафетчик получает настоящее место по полу (не "—")', () => {
    setState('all', 'all');
    const individual = [mkIndProgress(1, { gender: 'M', bike1_s: 5000, bike2_s: 9500 })];
    const relay = [mkBikeRelay(1000, { surname: 'Быстров', name: 'Олег', gender: 'M', bike1_s: 100, bike2_s: 200 })]; // заметно быстрее личника
    sandbox.__individual = individual;
    sandbox.__relay = relay;
    vm.runInContext('_data = { individual: __individual, relay: __relay };', sandbox);
    sandbox.renderBikeCombined();
    const html = sandbox.document.getElementById('app').innerHTML;
    assert.ok(html.includes('Скорость'), 'ожидалась колонка "Скорость" в заголовке');
    assert.ok(html.includes('По полу'), 'ожидалась колонка "По полу" в заголовке');
    assert.ok(html.includes('Быстров Олег'), `ожидалось реальное имя велосипедиста в разметке, html: ${html.slice(0, 500)}`);
    // Название команды может остаться подписью под ФИО (как на этапах), но
    // главным "именем участника" должно быть ФИО, не название команды.
    assert.ok(!/name-main">Team1000/.test(html), 'название команды не должно быть ГЛАВНЫМ именем участника');
    assert.ok(/\d+[.,]\d\s*км\/ч/.test(html), 'ожидалось значение скорости в км/ч');
    // Быстров быстрее личника — должен получить место 1 (в т.ч. по полу)
    const rowMatch = html.match(/rank-num[^>]*>1<\/span>[\s\S]{0,400}?Быстров/);
    assert.ok(rowMatch, 'эстафетчик Быстров должен быть на 1 месте (быстрее личника)');
});

// ── Автоочистка _chartSelectedBibs при смене фильтра формата/пола (баг
// найден пользователем 2026-07-19: выбранный участник "выпадал" из
// getFiltered(), график сравнения становился пустым, а "Сбросить выбор (N)"
// показывало устаревшее число, не совпадающее с реально видимыми чекбоксами) ──
function mkSwimRow(bib, gender) {
    const splits = { swim: {} };
    const cp = { swim: {} };
    for (let seq = 1; seq <= 7; seq++) { splits.swim[seq] = 300; cp.swim[seq] = 300 * seq + bib; }
    return { bib, surname: `Surname${bib}`, name: `Name${bib}`, gender, status: 'active', splits, cp, swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
}
check('renderPaceChart() — ранее выбранный участник, выпавший из фильтра пола, снимается с выбора', () => {
    setState('all', 'all');
    const individual = [mkSwimRow(1, 'M'), mkSwimRow(2, 'F')];
    sandbox.__individual = individual;
    vm.runInContext('_data = { individual: __individual, relay: [] }; _paceStage = "swim"; _chartSelectedBibs = [1, 2];', sandbox);
    // Переключаем фильтр на "только женщины" — участник 1 (M) должен выпасть.
    vm.runInContext('_gender = "F";', sandbox);
    sandbox.renderPaceChart();
    const selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(JSON.stringify(selected), JSON.stringify([2]), `ожидался только bib=2 после смены фильтра, получено ${JSON.stringify(selected)}`);
});
check('renderPositionChart() — та же автоочистка выбора', () => {
    setState('all', 'all');
    const individual = [mkSwimRow(1, 'M'), mkSwimRow(2, 'F')];
    sandbox.__individual = individual;
    vm.runInContext('_data = { individual: __individual, relay: [] }; _chartSelectedBibs = [1, 2];', sandbox);
    vm.runInContext('_gender = "M";', sandbox);
    sandbox.renderPositionChart();
    const selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(JSON.stringify(selected), JSON.stringify([1]), `ожидался только bib=1 после смены фильтра, получено ${JSON.stringify(selected)}`);
});

// ── Реальный баг: bib в API — СТРОКА (JSON), а не число. Чекбокс-обработчик
// раньше делал chartToggleSelect(Number(cb.dataset.chartbib)) — число
// никогда не совпадало с d._bib (строка) в .includes()/.indexOf(), выбор
// визуально отмечался, но график тут же оставался пустым/не сравнивал
// (найдено пользователем 2026-07-19, дважды воспроизведено на скриншотах) ──
check('Мультивыбор со СТРОКОВЫМ bib (как в реальном API) — график не остаётся пустым после выбора', () => {
    setState('all', 'all');
    const individual = [mkSwimRow('9999', 'M'), mkSwimRow('144', 'M')]; // bib строками, как в prod JSON
    sandbox.__individual = individual;
    vm.runInContext('_data = { individual: __individual, relay: [] }; _paceStage = "swim"; _chartSelectedBibs = [];', sandbox);
    sandbox.renderPaceChart();
    const datasets = sandbox.buildPaceDatasets('swim');
    assert.strictEqual(typeof datasets[0]._bib, 'string', 'd._bib должен остаться строкой (как bib из API)');
    // Симулируем реальный клик по чекбоксу — dataset.chartbib ВСЕГДА строка
    // (HTML data-атрибут), передаём как есть, без Number().
    sandbox.chartToggleSelect(datasets[0]._bib);
    sandbox.renderPaceChart();
    const chart = vm.runInContext('_paceChart', sandbox);
    assert.strictEqual(chart.config.data.datasets.length, 1, `после выбора одного участника график должен показать 1 линию, получено ${chart.config.data.datasets.length}`);
    assert.strictEqual(chart.config.data.datasets[0].label, datasets[0]._name);
});

// ── Вело (оба дня) — непрерывная линия скорости вело1+вело2 на графике
// Темп/скорость (запрошено пользователем 2026-07-19) ──
check('buildBikeCombinedPaceDatasets — вело2 продолжает вело1 по X (145+), без разрыва', () => {
    setState('all', 'all');
    const swimS = 2000;
    const row = mkTimerInd(1, {
        swim_s: swimS,
        splits: {
            bike_day1: { 1: swimS + 600, 2: 500 }, // seq=1 "раздут" заплывом — должен скорректироваться
            bike_day2: { 1: 700, 2: 650 },
        },
    });
    setRaceData([row], [], Date.now());
    const datasets = sandbox.buildBikeCombinedPaceDatasets();
    assert.strictEqual(datasets.length, 1);
    const xs = datasets[0].data.map(p => p.x);
    // Первая точка — экстраполяция x=0; далее вело1 (CHECKPOINT_DIST_KM.bike_day1[1..2]),
    // затем вело2 СМЕЩЁН на 145км (CHECKPOINT_DIST_KM.bike_day1[maxSeq]).
    const bike1MaxKm = vm.runInContext('CHECKPOINT_DIST_KM.bike_day1[STAGE_MAX_SEQ.bike_day1]', sandbox);
    assert.ok(xs.some(x => x > bike1MaxKm), `ожидались точки вело2 за пределами вело1 (>${bike1MaxKm} км), получено [${xs}]`);
    assert.strictEqual(xs[0], 0, 'первая точка должна быть экстраполяцией на x=0');
});
check('renderPaceChart(bike) — ось X охватывает весь объединённый велоэтап (421 км)', () => {
    setState('all', 'all');
    const row = mkTimerInd(1, {
        swim_s: 2000,
        splits: { bike_day1: { 1: 2600, 2: 500 }, bike_day2: { 1: 700 } },
    });
    setRaceData([row], [], Date.now());
    vm.runInContext(`_paceStage = 'bike'; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPaceChart();
    const chart = vm.runInContext('_paceChart', sandbox);
    const bike1Max = vm.runInContext('CHECKPOINT_DIST_KM.bike_day1[STAGE_MAX_SEQ.bike_day1]', sandbox);
    const bike2Max = vm.runInContext('CHECKPOINT_DIST_KM.bike_day2[STAGE_MAX_SEQ.bike_day2]', sandbox);
    assert.strictEqual(chart.config.options.scales.x.max, bike1Max + bike2Max);
    assert.strictEqual(chart.config.options.scales.y.reverse, false, 'скорость (км/ч) не должна инвертироваться');
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
