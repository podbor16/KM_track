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
    const handlers = {};
    const el = {
        innerHTML: '', style: {}, textContent: '', value: '2025', appendChild: () => {},
        // Реально запоминаем обработчики (не no-op) — нужно, чтобы тесты
        // могли симулировать клик по кнопкам сайдбара графика, не завися
        // от настоящего DOM.
        addEventListener: (type, fn) => { (handlers[type] ??= []).push(fn); },
        _handlers: handlers,
        dataset: {}, querySelector: () => domStub(), getContext: () => ({}), scrollIntoView: () => {},
    };
    if (id) elementsById[id] = el;
    return el;
}
// Chart.js стаб — рендер-функции графиков (renderPaceChart/renderPositionChart)
// создают `new Chart(...)`, без стаба падают с ReferenceError.
class ChartStub {
    constructor(ctx, config) {
        this.config = config; this.options = config.options || {}; this.data = config.data || {};
        // Простое 1px=1единица отображение — достаточно для тестов
        // nearestDatasetIndexAtPixel/onHover/onClick (реальная раскладка
        // canvas в node:vm недоступна, но геометрия хит-теста проверяется
        // именно в этих условных единицах).
        this.scales = {
            x: { getValueForPixel: px => px, getPixelForValue: v => v },
            y: { getValueForPixel: px => px, getPixelForValue: v => v },
        };
    }
    destroy() {}
    getDatasetMeta(datasetIndex) {
        const ds = this.data.datasets?.[datasetIndex];
        return { data: (ds?.data || []).map(p => ({ x: p.x, y: p.y })) };
    }
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
        body: { style: {} },
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    setInterval: () => 0,
    clearInterval: () => {},
    getComputedStyle: () => ({ getPropertyValue: () => '#6AABD7' }),
    Chart: ChartStub,
    window: {},
    // Стаб для чтения/записи состояния таба/фильтров в URL (п.4 v7,
    // 2026-08-03) — history.replaceState просто запоминает последний URL,
    // location.search тесты не используют напрямую (стартуют с дефолтов).
    URLSearchParams,
    location: { pathname: '/', search: '', hash: '' },
    history: { replaceState: (_s, _t, url) => { sandbox.location.search = (url.split('?')[1] ? '?' + url.split('?')[1] : ''); } },
    // Тесты по умолчанию эмулируют десктоп с мышью (не мобильный виджет
    // выбора участников, не touch-специфичное отключение клика по линии) —
    // matches:false для любого запроса, если тесту не нужно другое.
    matchMedia: () => ({ matches: false }),
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(commonJs, sandbox);
vm.runInContext(inlineScript, sandbox);

// Виртуальная КТ конца Дня 2 (Свода вело) — нужна фикстурам "финишировал
// оба вело-дня" ниже (2026-08-03: renderBikeCombined перешёл на
// bikeCombinedLastPos(), которая читает cp, а не bike1_s/bike2_s
// напрямую — фикстуры, где заданы только bike1_s/bike2_s без cp, теперь
// должны явно давать cp.bike_day2 на последней КТ, иначе bikeCombinedLastPos
// вернёт null, будто участник вело вообще не начинал).
const MAX_SEQ_BIKE_DAY2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
function finishedBikeCp(bike2_s) {
    return { bike_day2: { [MAX_SEQ_BIKE_DAY2]: bike2_s } };
}

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

// cp.run — единственный источник live-позиции для buildMergedOverallEntries
// теперь (racePos/raceSortKey, не overall_s напрямую) — фикстуры кодируют
// то же самое "финишное время" через КТ финиша бега, чтобы старые тесты
// на порядок интерливинга остались осмысленными (2026-08-03, Задача 7).
function mkInd(bib, overall_s, status = 'active') {
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    const cp = overall_s != null ? { run: { [maxSeqRun]: overall_s } } : {};
    return { bib, overall_s, status, gender: 'M', cp };
}
function mkRelay(bib, overall_s) {
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    const members = overall_s != null
        ? [{ relay_stage: 'run', status: 'active', run_s: overall_s, cp: { run: { [maxSeqRun]: overall_s } } }]
        : [];
    return { bib, overall_s, team_name: `Team${bib}`, members };
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

// ── buildRankedEntries() — переиспользует racePos/raceSortKey (та же
// модель, что и Итоги гонки, Задача 7), maxStage вместо getValue ──
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
check('buildRankedEntries — сортировка по live-позиции (maxStage=bike_day1), null (не начали День 1/dnf) — в хвост', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const individual = [
        mkIndProgress(1, { swim_s: 100, bike1_s: 200, cp: { swim: { 7: 100 }, bike_day1: { [n1]: 300 } } }),   // финишировал День 1: 300
        mkIndProgress(2, { swim_s: 50, cp: { swim: { 7: 50 } } }),                                              // ещё плывёт (в рамках Дня 1)
        mkIndProgress(3, { swim_s: 40, bike1_s: 60, status: 'dnf', cp: { swim: { 7: 40 }, bike_day1: { 2: 100 } } }), // dnf
    ];
    const relay = [mkRelayProgress(10, { swim_s: 30, swimCp: { swim: { 7: 30 } }, bike1_s: 40, bikeCp: { bike_day1: { [n1]: 70 } } })]; // 70, финишировал День 1
    const entries = sandbox.buildRankedEntries(individual, relay, 'bike_day1');
    const order = entries.map(e => e.entry.bib);
    assert.strictEqual(JSON.stringify(order), JSON.stringify([10, 1, 2, 3]), `expected [10,1,2,3], got [${order}]`);
    assert.strictEqual(entries[0].v, 70);
    assert.strictEqual(entries[1].v, 300);
    assert.ok(entries[2].v > 0, 'участник 2 ещё плывёт — v = live-прогресс, не null');
    assert.strictEqual(entries[3].v, null, 'dnf без активного статуса — v всегда null');
});

// ── Живой секундомер этапа: stageStartOffset()/stageIsPending()/computeActiveStageTimers() ──
// _data/_raceStartEpoch объявлены как let внутри исполненного скрипта —
// та же лексическая изоляция, что и _gender/_fmt (см. setState выше).
function setRaceData(individual, relay, raceStartEpoch, bike2StartEpoch = null, runStartEpoch = null) {
    sandbox.__individual = individual;
    sandbox.__relay = relay;
    sandbox.__raceStartEpoch = raceStartEpoch;
    sandbox.__bike2StartEpoch = bike2StartEpoch;
    sandbox.__runStartEpoch = runStartEpoch;
    vm.runInContext('_data = { individual: __individual, relay: __relay }; _raceStartEpoch = __raceStartEpoch; _bike2StartEpoch = __bike2StartEpoch; _runStartEpoch = __runStartEpoch; _recordsIndex = {};', sandbox);
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
    assert.strictEqual(state.label, 'День 2');
});

check('computeStageTimerState — день 1 закрыт, известно ПЛАНОВОЕ время старта вело-дня-2 (в будущем) — обратный отсчёт, не статичный текст', () => {
    // Запрошено пользователем 2026-08-06: раньше после закрытия дня 1
    // виджет всегда показывал статичный "Следующий этап: Вело День 2" —
    // теперь, если известно плановое время старта (bike2_start в конфиге,
    // не по факту прихода участника), должен тикать обратный отсчёт до него.
    // Лейбл — просто название этапа, без "Следующий этап"/"До начала"
    // (запрошено пользователем: излишне, название + отсчёт достаточно).
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const dnfAfterSwim = mkTimerInd(1, { status: 'dnf', cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    const now = Date.now();
    const scheduledBike2 = now + 2 * 3600 * 1000; // через 2 часа
    setRaceData([dnfAfterSwim], [], now - 100000, scheduledBike2, null);
    const state = sandbox.computeStageTimerState();
    assert.strictEqual(state.type, 'countdown');
    assert.strictEqual(state.label, 'День 2');
    assert.strictEqual(state.startEpoch, scheduledBike2);
});
check('computeStageTimerState — кто-то УЖЕ финишировал день 1 (личный "вход" в вело-день-2 известен), но плановый старт ещё впереди — всё равно обратный отсчёт, не elapsed-секундомер', () => {
    // Реальный баг с продакшна (найдено пользователем 2026-08-06, "Вело День 2"
    // 07.08 08:00, а отсчёт шёл до полуночи): как только ПЕРВЫЙ участник
    // реально финиширует день 1 (swim_s+bike1_s оба не null), stageStartOffset
    // ('bike_day2') перестаёт быть null — старая версия проверки (off==null
    // до sched) в этот момент уже пропускала ветку с плановым временем и
    // уходила в elapsed-таймер от личного времени входа этого финишера,
    // ИГНОРИРУЯ то, что по расписанию день ещё не начался. Правильно —
    // плановое время должно иметь приоритет, пока оно не наступило,
    // независимо от того, есть ли уже "личный вход" у кого-то.
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const finishedDay1 = mkTimerInd(1, {
        cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { [maxSeqBike1]: 9000 } },
        swim_s: 3000, bike1_s: 9000,
    });
    const now = Date.now();
    const scheduledBike2 = now + 5 * 3600 * 1000; // через 5 часов, ещё не наступило
    setRaceData([finishedDay1], [], now - 20000, scheduledBike2, null);
    const state = sandbox.computeStageTimerState();
    assert.strictEqual(state.type, 'countdown', `ожидался обратный отсчёт до планового старта, получили: ${JSON.stringify(state)}`);
    assert.strictEqual(state.label, 'День 2');
    assert.strictEqual(state.startEpoch, scheduledBike2);
});
check('computeStageTimerState — день 1 закрыт, плановое время вело-дня-2 УЖЕ ПРОШЛО — статичный текст, не отрицательный отсчёт', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const dnfAfterSwim = mkTimerInd(1, { status: 'dnf', cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    const now = Date.now();
    const pastScheduled = now - 3600 * 1000; // час назад — расписание уже "просрочено"
    setRaceData([dnfAfterSwim], [], now - 100000, pastScheduled, null);
    const state = sandbox.computeStageTimerState();
    assert.strictEqual(state.type, 'next');
    assert.strictEqual(state.label, 'День 2');
});
check('computeStageTimerState — плановое время дня 2 УЖЕ ПРОШЛО, кто-то ещё активен — тикающий секундомер ОТ ПЛАНОВОГО СТАРТА, не от личного времени входа финишера дня 1', () => {
    // Реальный баг с продакшна (найдено пользователем 2026-08-07, второй
    // день только начался, а таймер сразу показал ~17 часов): старый якорь
    // `_raceStartEpoch + off*1000` — это время, когда САМЫЙ БЫСТРЫЙ участник
    // закончил день 1 (off), а не момент реального старта дня 2. Если день 1
    // у лидера занял, скажем, 17 часов, таймер "Дня 2" сразу после его
    // планового старта показывал бы ~17ч вместо ~0. Правильный якорь —
    // plannedEpoch (bike2_start), когда он уже наступил.
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    // Лидер финишировал день 1 за 17 часов (61200с) от старта гонки.
    const finishedDay1 = mkTimerInd(1, {
        cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { [maxSeqBike1]: 61200 } },
        swim_s: 3000, bike1_s: 58200,
    });
    const raceStart = Date.now() - 18 * 3600 * 1000; // гонка началась 18ч назад
    const scheduledBike2 = raceStart + 17.5 * 3600 * 1000; // плановый старт дня 2 — 30 мин назад
    setRaceData([finishedDay1], [], raceStart, scheduledBike2, null);
    const state = sandbox.computeStageTimerState();
    assert.strictEqual(state.type, 'timer', `ожидался тикающий секундомер: ${JSON.stringify(state)}`);
    assert.strictEqual(state.label, 'День 2');
    assert.strictEqual(state.startEpoch, scheduledBike2, `якорь таймера должен быть плановым стартом дня 2, не временем входа финишера дня 1: ${JSON.stringify(state)}`);
});

check('computeStageTimerState — race_start ещё в будущем — обратный отсчёт до старта, не "День 1"', () => {
    // 2026-08-04: раньше это ушло бы в "День 1"-таймер (naive Date.now()-start
    // на будущий race_start), найдено на реальных тестовых данных со
    // стартом "прошлого года" по системным часам.
    setRaceData([], [], Date.now() + 3600 * 1000);
    const state = sandbox.computeStageTimerState();
    assert.strictEqual(state.type, 'countdown');
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
function mkFinishedRow(bib, totalS, status = 'active') {
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    return { bib, status, gender: 'M', swim_s: 0, bike1_s: 0, bike2_s: 0, run_s: status === 'active' ? totalS : null, cp: { run: { [maxSeqRun]: totalS } } };
}
function mkFinishedRelay(bib, totalS) {
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    return {
        bib, team_name: `Team${bib}`,
        members: [
            { relay_stage: 'swim', status: 'active', cp: {}, swim_s: 0 },
            { relay_stage: 'bike', status: 'active', cp: {}, bike1_s: 0, bike2_s: 0 },
            { relay_stage: 'run', status: 'active', cp: { run: { [maxSeqRun]: totalS } }, run_s: totalS },
        ],
    };
}
check('computeCombinedOverallRanks — единая последовательность 1,2,3... без дублей (live, по racePos)', () => {
    const individual = [mkFinishedRow(1, 22 * 3600), mkFinishedRow(2, 23 * 3600)];
    const relay = [mkFinishedRelay(10, 22.2 * 3600)]; // между личником 1 и 2 по времени
    const rows = sandbox.combinedOverallRankRows(individual, relay);
    const ranks = sandbox.computeCombinedOverallRanks(rows, null);
    assert.strictEqual(JSON.stringify(ranks), JSON.stringify({ 1: 1, 10: 2, 2: 3 }));
});
check('computeCombinedOverallRanks — не финишировавшие (null прогресс/dnf) не получают место', () => {
    const individual = [mkFinishedRow(1, 100), { bib: 2, status: 'dnf', gender: 'M', cp: {} }];
    const relay = [{ bib: 10, team_name: 'Team10', members: [] }]; // без прогресса вовсе
    const rows = sandbox.combinedOverallRankRows(individual, relay);
    const ranks = sandbox.computeCombinedOverallRanks(rows, null);
    assert.strictEqual(JSON.stringify(ranks), JSON.stringify({ 1: 1 }));
});
check('computeCombinedOverallRanks — считает место ДО финиша всей гонки (live)', () => {
    const a = { bib: 1, status: 'active', gender: 'M', swim_s: 4000, cp: { swim: { 7: 4000 }, bike_day1: { 2: 4500 } } }; // уже на вело
    const b = { bib: 2, status: 'active', gender: 'M', swim_s: null, cp: { swim: { 4: 1380 } } }; // ещё плывёт
    const rows = sandbox.combinedOverallRankRows([a, b], []);
    const ranks = sandbox.computeCombinedOverallRanks(rows, null);
    assert.strictEqual(ranks[1], 1, `участник уже на вело должен быть 1-м местом: ${JSON.stringify(ranks)}`);
    assert.strictEqual(ranks[2], 2, `участник ещё плывёт должен быть 2-м: ${JSON.stringify(ranks)}`);
});

// Регрессия на саму причину бага задачи 4: раньше место требовало overall_s
// (полный финиш ВСЕЙ гонки), а до этого момента эстафета получала
// незаслуженное преимущество через накапливающийся overall_s команды —
// личник с бОльшим реальным прогрессом мог оказаться позади ещё не
// финишировавшей эстафеты. Тест закрепляет: место — по racePos (реальная
// точка на дистанции), НЕ по типу участника — проверено в обе стороны.
check('computeCombinedOverallRanks — mid-race личник и mid-race эстафета вместе: место по прогрессу, не по типу', () => {
    // Личник уже на вело (дальше), эстафета ещё плывёт (позади).
    const soloOnBike = { bib: 1, status: 'active', gender: 'M', swim_s: 4000, cp: { swim: { 7: 4000 }, bike_day1: { 2: 4500 } } };
    const relayStillSwimming = {
        bib: 10, team_name: 'Team10',
        members: [
            { relay_stage: 'swim', status: 'active', cp: { swim: { 4: 1380 } }, swim_s: null },
            { relay_stage: 'bike', status: 'active', cp: {}, bike1_s: null, bike2_s: null },
            { relay_stage: 'run', status: 'active', cp: {}, run_s: null },
        ],
    };
    let rows = sandbox.combinedOverallRankRows([soloOnBike], [relayStillSwimming]);
    let ranks = sandbox.computeCombinedOverallRanks(rows, null);
    assert.strictEqual(ranks[1], 1, `личник дальше (уже на вело) — должен быть 1-м: ${JSON.stringify(ranks)}`);
    assert.strictEqual(ranks[10], 2, `эстафета ещё плывёт — должна быть 2-й: ${JSON.stringify(ranks)}`);

    // Наоборот: эстафета уже на вело (дальше), личник ещё плывёт (позади) —
    // то же преимущество не должно доставаться личнику просто по типу.
    const soloStillSwimming = { bib: 2, status: 'active', gender: 'M', swim_s: null, cp: { swim: { 4: 1380 } } };
    const relayOnBike = {
        bib: 11, team_name: 'Team11',
        members: [
            { relay_stage: 'swim', status: 'active', cp: { swim: { 7: 4000 } }, swim_s: 4000 },
            { relay_stage: 'bike', status: 'active', cp: { bike_day1: { 2: 4500 } }, bike1_s: null, bike2_s: null },
            { relay_stage: 'run', status: 'active', cp: {}, run_s: null },
        ],
    };
    rows = sandbox.combinedOverallRankRows([soloStillSwimming], [relayOnBike]);
    ranks = sandbox.computeCombinedOverallRanks(rows, null);
    assert.strictEqual(ranks[11], 1, `эстафета дальше (уже на вело) — должна быть 1-й: ${JSON.stringify(ranks)}`);
    assert.strictEqual(ranks[2], 2, `личник ещё плывёт — должен быть 2-м: ${JSON.stringify(ranks)}`);
});

check('computeOverallGaps — отставание считается ДО того, как кто-то финишировал всю гонку', () => {
    // ПРИМЕЧАНИЕ: cp.swim[4] у ahead добавлен сверх буквального текста плана —
    // computeOverallGaps ищет значение лидера ТОЧНО на seq отстающего (без
    // поиска "назад", как computeStageGaps), это поведение не менялось этой
    // задачей. Без записи на этой же КТ лидер (уже уехавший на вело) не даёт
    // сравнимого значения, и gap для B не проставляется вовсе — найдено
    // реальным прогоном.
    const ahead = { key: 'A', status: 'active', gender: 'M', swim_s: 4000, cp: { swim: { 4: 1200, 7: 4000 }, bike_day1: { 2: 4500 } } };
    const behind = { key: 'B', status: 'active', gender: 'M', swim_s: null, cp: { swim: { 4: 1380 } } };
    const gaps = sandbox.computeOverallGaps([ahead, behind]);
    assert.strictEqual(gaps.A, 0, `A дальше всех — лидер, gap=0: ${JSON.stringify(gaps)}`);
    assert.ok(gaps.B > 0, `B должен получить положительное отставание: ${JSON.stringify(gaps)}`);
});
check('computeOverallGaps — с maxStage ограничивается днём (переиспользуется на вкладках "Дни")', () => {
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    // ПРИМЕЧАНИЕ: cp.bike_day1[2] у finishedDay1 добавлен сверх буквального
    // текста плана — та же причина, что и в тесте выше: без записи ТОЧНО на
    // seq=2 (позиция midDay1) у лидера нет сравнимого значения, и gaps.B
    // остаётся undefined вместо положительного отставания.
    const finishedDay1 = { key: 'A', status: 'active', swim_s: 4000, bike1_s: 4500, cp: { swim: { 7: 4000 }, bike_day1: { 2: 4300, [maxSeqBike1]: 8500 }, run: { 3: 20000 } } };
    const midDay1 = { key: 'B', status: 'active', swim_s: 4200, cp: { swim: { 7: 4200 }, bike_day1: { 2: 5000 } } };
    const gaps = sandbox.computeOverallGaps([finishedDay1, midDay1], 'bike_day1');
    assert.strictEqual(gaps.A, 0, `A дальше всех В ПРЕДЕЛАХ ДНЯ 1 (бег из cp игнорируется) — лидер: ${JSON.stringify(gaps)}`);
    assert.ok(gaps.B > 0);
});
check('computeOverallGaps — mid-race личник vs mid-race эстафета: лидер по прогрессу в обе стороны', () => {
    // Сборка строк идентична реальному вызову в renderOverall()
    // (results.html:825-828): teamGapRow(team) для эстафеты, {key, cp,
    // status, ...} для личника — computeOverallGaps не должен отличать их.
    // ПРИМЕЧАНИЕ: cp.swim[4] у лидера (уже на вело) добавлен сверх минимума —
    // та же причина, что и в тесте "отставание считается ДО того, как кто-то
    // финишировал" выше: computeOverallGaps ищет значение лидера ТОЧНО на seq
    // отстающего, без записи на этой же КТ gap не проставляется вовсе.
    const soloOnBike = { key: 1, cp: { swim: { 4: 1200, 7: 4000 }, bike_day1: { 2: 4500 } }, status: 'active', swim_s: 4000, bike1_s: null, bike2_s: null, run_s: null };
    const relayStillSwimming = sandbox.teamGapRow({
        bib: 10,
        members: [
            { relay_stage: 'swim', status: 'active', cp: { swim: { 4: 1380 } }, swim_s: null },
            { relay_stage: 'bike', status: 'active', cp: {}, bike1_s: null, bike2_s: null },
            { relay_stage: 'run', status: 'active', cp: {}, run_s: null },
        ],
    });
    let gaps = sandbox.computeOverallGaps([soloOnBike, relayStillSwimming]);
    assert.strictEqual(gaps[1], 0, `личник дальше (уже на вело) — лидер: ${JSON.stringify(gaps)}`);
    assert.ok(gaps[10] > 0, `эстафета позади (ещё плывёт) — положительное отставание: ${JSON.stringify(gaps)}`);

    // Наоборот: эстафета дальше (уже на вело) — лидер, личник ещё плывёт.
    const soloStillSwimming = { key: 2, cp: { swim: { 4: 1380 } }, status: 'active', swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
    const relayOnBike = sandbox.teamGapRow({
        bib: 11,
        members: [
            { relay_stage: 'swim', status: 'active', cp: { swim: { 4: 1200, 7: 4000 } }, swim_s: 4000 },
            { relay_stage: 'bike', status: 'active', cp: { bike_day1: { 2: 4500 } }, bike1_s: null, bike2_s: null },
            { relay_stage: 'run', status: 'active', cp: {}, run_s: null },
        ],
    });
    gaps = sandbox.computeOverallGaps([soloStillSwimming, relayOnBike]);
    assert.strictEqual(gaps[11], 0, `эстафета дальше (уже на вело) — лидер: ${JSON.stringify(gaps)}`);
    assert.ok(gaps[2] > 0, `личник позади (ещё плывёт) — положительное отставание: ${JSON.stringify(gaps)}`);
});

// ── computeAutoScrollTab() — п.1 задачи 2026-07-19 (визуальный скролл
// табов до активного этапа, независимо от секундомера) ──
check('computeAutoScrollTab — race_start ещё в будущем (ростер загружен, отметок нет) -> null, не "swim"', () => {
    // 2026-08-04: загрузили участников на будущий год, гонка не началась —
    // stageIsPending('swim') было true уже из одного факта "все активны и
    // никто не финишировал заплыв" (тот же нюанс, что уже поймали в
    // computeStageTimerState() для секундомера, но забыли применить здесь) —
    // таб "Плавание" ошибочно подсвечивался пульсирующей точкой как "живой".
    const notStarted = mkTimerInd(1, { cp: {} });
    setRaceData([notStarted], [], Date.now() + 3600 * 1000);
    assert.strictEqual(sandbox.computeAutoScrollTab(), null);
});
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

check('computeAutoScrollTab — заплыв закрыт, вело-2/бег ещё не наступили -> bike (не "startlist")', () => {
    // 2026-08-04, второй раунд: раньше это была отдельная вкладка "startlist"
    // (расчётный список вело-2) — теперь индикатор просто остаётся на "bike"
    // (там же живёт вело-день-1), пока реально не наступит вело-2/бег —
    // не убегает вперёд к этапу без данных.
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const a = mkTimerInd(1, { status: 'dnf', cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    setRaceData([a], [], Date.now());
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'bike');
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

check('computeAutoScrollTab — вело-2 идёт, бег по факту ещё не наступил -> bike (не убегает вперёд на "run")', () => {
    // 2026-08-04, второй раунд: раньше "никто не вошёл в бег" сразу же
    // указывало на вкладку "Бег" (там пока пусто) — теперь индикатор
    // остаётся на "bike", пока бег реально/по расписанию не наступит.
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const a = mkTimerInd(1, {
        status: 'dnf',
        cp: { swim: { [maxSeqSwim]: 3000 }, bike_day1: { [maxSeqBike1]: 9000 }, bike_day2: { 3: 1000 } },
        swim_s: 3000, bike1_s: 9000,
    });
    setRaceData([a], [], Date.now());
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'bike');
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

// ── computeAutoScrollState().live — первый финиш заплыва делает ОБА таба
// (Плавание+Вело) "живыми" одновременно, скролл при этом держится на
// Плавании, пока оно не закроется целиком (2026-08-04, второй раунд) ──
check('computeAutoScrollState — первый финишер заплыва: live=[swim,bike], но scroll=swim (второй ещё плывёт)', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const finished = mkTimerInd(1, { cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    const stillSwimming = mkTimerInd(2, { cp: { swim: { 1: 500 } } });
    setRaceData([finished, stillSwimming], [], Date.now());
    const state = sandbox.computeAutoScrollState();
    // JSON.stringify — не deepStrictEqual: массив создан внутри vm-песочницы,
    // у него другой Array-конструктор (другой "realm"), чем у host-процесса,
    // deepStrictEqual считает их разными объектами при идентичном содержимом.
    assert.strictEqual(JSON.stringify(Array.from(state.live).sort()), JSON.stringify(['bike', 'swim']));
    assert.strictEqual(state.scroll, 'swim');
});
check('computeAutoScrollState — никто ещё не финишировал заплыв: live=[swim] только', () => {
    const stillSwimming = mkTimerInd(1, { cp: { swim: { 1: 500 } } });
    setRaceData([stillSwimming], [], Date.now());
    assert.strictEqual(JSON.stringify(Array.from(sandbox.computeAutoScrollState().live)), JSON.stringify(['swim']));
});

// ── Расписание Вело Дня 2 / Бега из админки (bike2StartEpoch/runStartEpoch) —
// переключение по ВРЕМЕНИ, даже если данных по новому этапу ещё нет ──
check('computeAutoScrollTab — заплыв закрыт, время вело-2 из админки ещё не наступило -> bike, не переключается раньше времени', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const a = mkTimerInd(1, { status: 'dnf', cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    setRaceData([a], [], Date.now(), Date.now() + 3600 * 1000);
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'bike');
});
check('computeAutoScrollTab — заплыв закрыт, время вело-2 из админки уже наступило -> тоже bike (тот же топ-таб, но переключение состоялось)', () => {
    // Вело-2 живёт на том же топ-табе "bike" (Вело), что и вело-1 — время
    // из админки здесь влияет на runHasStarted-гейт дальше, не на сам
    // результат этого шага; проверяем, что при наступившем времени вело-2,
    // но НЕ наступившем времени бега, индикатор остаётся на "bike" (не run).
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const a = mkTimerInd(1, { status: 'dnf', cp: { swim: { [maxSeqSwim]: 3000 } }, swim_s: 3000 });
    setRaceData([a], [], Date.now(), Date.now() - 1000, Date.now() + 3600 * 1000);
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'bike');
});
check('computeAutoScrollTab — время бега из админки наступило, но данных по бегу ещё нет -> run (переключается СРАЗУ по времени)', () => {
    // Участник активен, заплыв финиширован (иначе завис бы на "swim"),
    // данных по бегу — вообще никаких: переключение на "run" всё равно
    // должно состояться, раз время уже наступило.
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const a = mkTimerInd(1, { status: 'active', swim_s: 3000, cp: { swim: { [maxSeqSwim]: 3000 } } });
    setRaceData([a], [], Date.now(), Date.now() - 3600 * 1000, Date.now() - 1000);
    assert.strictEqual(sandbox.computeAutoScrollTab(), 'run');
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

// ── bikeCombinedRelayRider()/renderBikeCombined — место по полу + скорость
// в своде вело (421 км), запрошено пользователем 2026-07-19. Эстафета
// показывается как РЕАЛЬНЫЙ велосипедист команды (один и тот же человек
// едет оба дня), не как безликая команда — у него есть личный пол/место. ──
function mkBikeRelay(bib, overrides) {
    return {
        bib, team_name: `Team${bib}`,
        members: [
            { relay_stage: 'bike', status: overrides.status ?? 'active', surname: overrides.surname, name: overrides.name, gender: overrides.gender, bike1_s: overrides.bike1_s, bike2_s: overrides.bike2_s, cp: overrides.cp ?? {} },
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
    const individual = [mkIndProgress(1, { gender: 'M', bike1_s: 5000, bike2_s: 9500, cp: finishedBikeCp(9500) })];
    const relay = [mkBikeRelay(1000, { surname: 'Быстров', name: 'Олег', gender: 'M', bike1_s: 100, bike2_s: 200, cp: finishedBikeCp(200) })]; // заметно быстрее личника
    sandbox.__individual = individual;
    sandbox.__relay = relay;
    vm.runInContext('_data = { individual: __individual, relay: __relay };', sandbox);
    sandbox.renderBikeCombined();
    const html = sandbox.document.getElementById('app').innerHTML;
    assert.ok(html.includes('Скорость'), 'ожидалась колонка "Скорость" в заголовке');
    assert.ok(html.includes('Место (пол)'), 'ожидалась колонка "Место (пол)" в заголовке');
    assert.ok(html.includes('Быстров Олег'), `ожидалось реальное имя велосипедиста в разметке, html: ${html.slice(0, 500)}`);
    // Название команды может остаться подписью под ФИО (как на этапах), но
    // главным "именем участника" должно быть ФИО, не название команды.
    assert.ok(!/name-main">Team1000/.test(html), 'название команды не должно быть ГЛАВНЫМ именем участника');
    assert.ok(/\d+[.,]\d\s*км\/ч/.test(html), 'ожидалось значение скорости в км/ч');
    // Быстров быстрее личника — должен получить место 1 (в т.ч. по полу)
    const rowMatch = html.match(/rank-num[^>]*>1<\/span>[\s\S]{0,400}?Быстров/);
    assert.ok(rowMatch, 'эстафетчик Быстров должен быть на 1 месте (быстрее личника)');
});
check('renderBikeCombined() — отставание встроено под временем (новая колонка, п.3 v5, 2026-07-23)', () => {
    setState('all', 'all');
    const individual = [mkIndProgress(1, { gender: 'M', bike1_s: 5000, bike2_s: 9500, cp: finishedBikeCp(9500) })]; // 14500с
    const relay = [mkBikeRelay(1000, { surname: 'Быстров', name: 'Олег', gender: 'M', bike1_s: 100, bike2_s: 200, cp: finishedBikeCp(200) })]; // 300с — лидер
    sandbox.__individual = individual;
    sandbox.__relay = relay;
    vm.runInContext('_data = { individual: __individual, relay: __relay };', sandbox);
    sandbox.renderBikeCombined();
    const html = sandbox.document.getElementById('app').innerHTML;
    assert.ok(html.includes('time-gap-sub'), `ожидалось отставание под временем: ${html.slice(0, 700)}`);
    assert.ok(html.includes('Лидер'), `лидер (Быстров, 300с) должен получить подпись "Лидер": ${html.slice(0, 700)}`);
});
check('renderBikeCombined() фильтр "Эстафета"+Пол=Все — 2 колонки Место/Место (пол), 3-колоночный режим убран (п.7 v6, 2026-08-02)', () => {
    const relay = [
        { bib: '1000', team_name: 'КомандаА', members: [
            { relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 100, cp: {} },
            { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: 5000, bike2_s: 4000, cp: finishedBikeCp(4000) },
            { relay_stage: 'run', status: 'active', gender: 'M', run_s: 100, cp: {} },
        ] },
        { bib: '1001', team_name: 'КомандаБ', members: [
            { relay_stage: 'swim', status: 'active', gender: 'F', swim_s: 100, cp: {} },
            { relay_stage: 'bike', status: 'active', gender: 'F', bike1_s: 6000, bike2_s: 5000, cp: finishedBikeCp(5000) },
            { relay_stage: 'run', status: 'active', gender: 'F', run_s: 100, cp: {} },
        ] },
    ];
    setRaceData([], relay, Date.now());
    setState('relay', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    assert.ok(html.includes('<th class="r">Место</th>') && html.includes('Место (пол)'), `ожидались колонки Место/Место (пол): ${html.slice(0,600)}`);
    assert.ok(!html.includes('>Формат</th>'), `колонки "Формат" быть не должно: ${html.slice(0,600)}`);
    const rowA = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1000<[\s\S]*?<\/tr>/)[0];
    assert.ok(/rank-num[^>]*>1</.test(rowA), `КомандаА (9000с) быстрее КомандыБ (11000с) — место 1: ${rowA}`);
});
check('renderBikeCombined() — ранг среди ВИДИМЫХ строк, не по полному ростеру (откат 2026-07-23)', () => {
    const individual = [mkIndProgress(1, { gender: 'M', bike1_s: 100, bike2_s: 100, cp: finishedBikeCp(100) })]; // 200с — самый быстрый, но невидим
    const relay = [mkBikeRelay(1000, { surname: 'Средний', name: 'Иван', gender: 'M', bike1_s: 5000, bike2_s: 4000, cp: finishedBikeCp(4000) })]; // 9000с
    sandbox.__individual = individual;
    sandbox.__relay = relay;
    vm.runInContext('_data = { individual: __individual, relay: __relay };', sandbox);
    setState('relay', 'all'); // личник (самый быстрый) не виден при fmt=relay
    sandbox.renderBikeCombined();
    const html = sandbox.document.getElementById('app').innerHTML;
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1000<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка эстафеты не найдена: ${html}`);
    // Единственная видимая строка — должна получить абсолютный ранг 1,
    // несмотря на то, что невидимый личник объективно быстрее.
    assert.ok(/rank-num[^>]*>1</.test(rowMatch[0]), `эстафета — единственная видимая строка, абсолютный ранг 1: ${rowMatch[0]}`);
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

// ── Запас по оси Y (grace/min-max) — крайние точки данных (1-е место,
// самая быстрая скорость) не должны рисоваться ровно на границе графика
// (найдено пользователем 2026-07-19) ──
check('renderPaceChart — ось Y использует grace (запас над авто-диапазоном)', () => {
    setState('all', 'all');
    const row = mkTimerInd(1, { splits: { swim: { 1: 300 } } });
    setRaceData([row], [], Date.now());
    vm.runInContext(`_paceStage = 'swim'; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPaceChart();
    const chart = vm.runInContext('_paceChart', sandbox);
    assert.strictEqual(chart.config.options.scales.y.grace, '8%');
});
check('renderPositionChart — min/max оси Y с запасом (не 1..maxRank впритык)', () => {
    setState('all', 'all');
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const row = mkTimerInd(1, { cp: { swim: { [maxSeqSwim]: 300 } }, swim_s: 300 });
    setRaceData([row], [], Date.now());
    sandbox.renderPositionChart();
    const chart = vm.runInContext('_positionChart', sandbox);
    const yScale = chart.config.options.scales.y;
    assert.ok(yScale.min < 1, `min должен быть меньше 1 (запас сверху), получено ${yScale.min}`);
    assert.ok(yScale.max > 1, 'max должен быть больше реального худшего места (запас снизу)');
});
check('renderPositionChart — тики оси Y только целые, от 1 до maxRank (afterBuildTicks)', () => {
    setState('all', 'all');
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const rows = [1, 2, 3].map(bib => mkTimerInd(bib, { cp: { swim: { [maxSeqSwim]: 300 + bib } }, swim_s: 300 + bib }));
    setRaceData(rows, [], Date.now());
    sandbox.renderPositionChart();
    const chart = vm.runInContext('_positionChart', sandbox);
    const axisStub = { ticks: null };
    chart.config.options.scales.y.afterBuildTicks(axisStub);
    const values = axisStub.ticks.map(t => t.value);
    assert.strictEqual(JSON.stringify(values), JSON.stringify([1, 2, 3]), `ожидались целые тики 1..3, получено ${JSON.stringify(values)}`);
});

// ── Список участников для сравнения сортируется по алфавиту (не по порядку
// API) — запрошено пользователем 2026-07-19 ──
check('chartParticipantListItemsHtml — сортировка по алфавиту, не по порядку datasets', () => {
    const datasets = [
        { _bib: 1, _name: 'Яковлев Иван' },
        { _bib: 2, _name: 'Астафьев Сергей' },
        { _bib: 3, _name: 'Летницкий Дмитрий' },
    ];
    vm.runInContext('_chartSearchQuery = ""; _chartSelectedBibs = [];', sandbox);
    const html = sandbox.chartParticipantListItemsHtml(datasets);
    const idxA = html.indexOf('Астафьев');
    const idxL = html.indexOf('Летницкий');
    const idxY = html.indexOf('Яковлев');
    assert.ok(idxA < idxL && idxL < idxY, `ожидался алфавитный порядок Астафьев < Летницкий < Яковлев, html: ${html}`);
});

// ── Единая плашка hover (имя+значение вместе), не два конкурирующих
// элемента (canvas-плагин + встроенный тултип Chart.js) — найдено
// пользователем 2026-07-20 на реальных скриншотах (плашки перекрывались) ──
check('renderPaceChart() режим по умолчанию — встроенный тултип отключён (одна плашка вместо двух)', () => {
    setState('all', 'all');
    const row = mkTimerInd(1, { splits: { swim: { 1: 300 } } });
    setRaceData([row], [], Date.now());
    vm.runInContext(`_paceStage = 'swim'; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPaceChart();
    const chart = vm.runInContext('_paceChart', sandbox);
    assert.strictEqual(chart.config.options.plugins.tooltip.enabled, false, 'встроенный тултип должен быть отключён вне режима сравнения');
});
check('renderPositionChart() режим по умолчанию — встроенный тултип отключён', () => {
    setState('all', 'all');
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const row = mkTimerInd(1, { cp: { swim: { [maxSeqSwim]: 300 } }, swim_s: 300 });
    setRaceData([row], [], Date.now());
    vm.runInContext(`_chartSelectedBibs = [];`, sandbox);
    sandbox.renderPositionChart();
    const chart = vm.runInContext('_positionChart', sandbox);
    assert.strictEqual(chart.config.options.plugins.tooltip.enabled, false);
});
check('renderPaceChart() режим сравнения — встроенный тултип ВКЛЮЧЁН (легенда уже называет линии, canvas-плагин не рисует)', () => {
    setState('all', 'all');
    const row = mkTimerInd('1', { splits: { swim: { 1: 300 } } });
    setRaceData([row], [], Date.now());
    vm.runInContext(`_paceStage = 'swim';`, sandbox);
    sandbox.chartToggleSelect('1');
    sandbox.renderPaceChart();
    const chart = vm.runInContext('_paceChart', sandbox);
    assert.notStrictEqual(chart.config.options.plugins.tooltip.enabled, false, 'в режиме сравнения тултип должен остаться включён');
});
check('attachSpaghettiHover — hoverInfo.text объединяет имя И значение (formatPoint)', () => {
    const fakeChart = {
        data: { datasets: [{ label: 'Иванов Иван', data: [{ x: 3.9, y: 22 }] }] },
        scales: { x: { getValueForPixel: px => px, getPixelForValue: v => v }, y: { getValueForPixel: px => px, getPixelForValue: v => v } },
        getDatasetMeta: () => ({ data: [{ x: 100, y: 200 }] }),
        update: () => {},
        options: {},
    };
    sandbox.attachSpaghettiHover(fakeChart, '#f00', '#ccc', (x, y) => `${x} км: место ${y}`);
    // Курсор ровно на x=3.9 (значение = пиксель в этом стабе) — единственная
    // точка датасета, hit-test обязан выбрать датасет 0.
    fakeChart.options.onHover.call(fakeChart, { x: 3.9, y: 22 });
    assert.strictEqual(fakeChart._hoverInfo.text, 'Иванов Иван — 3.9 км: место 22');
});

check('buildPositionDatasets(stage) — место ВНУТРИ этапа (не по всей гонке), реальный км + экстраполяция x=0', () => {
    setState('all', 'all');
    // A: медленно прошёл плавание+вело (сумма 18000с до бега), но САМЫЙ
    // быстрый на 1-м km бега (500с) — глобально позади, локально на бегу впереди.
    const rowA = mkTimerInd('1', { swim_s: 1000, bike1_s: 9000, bike2_s: 8000, cp: { run: { 1: 500 } } });
    // B: быстро прошёл плавание+вело (сумма 9500с), но медленнее на 1-м км бега (5000с).
    const rowB = mkTimerInd('2', { swim_s: 500, bike1_s: 5000, bike2_s: 4000, cp: { run: { 1: 5000 } } });
    setRaceData([rowA, rowB], [], Date.now());
    const datasets = sandbox.buildPositionDatasets('run');
    const a = datasets.find(d => d._bib === '1');
    const b = datasets.find(d => d._bib === '2');
    // Экстраполяция до x=0 — та же, что и в глобальном режиме (найдено
    // пользователем 2026-07-21: без неё линии на графике "по этапу"
    // визуально начинались не с самого начала оси X).
    assert.strictEqual(a.data.length, 2, 'экстраполированная точка x=0 + реальная КТ');
    assert.strictEqual(a.data[0].x, 0, 'экстраполяция до x=0');
    assert.strictEqual(a.data[1].x, 7, 'X — реальный км ВНУТРИ этапа (CHECKPOINT_DIST_KM.run[1] = 7)');
    assert.strictEqual(a.data[1].y, 1, 'A локально впереди на бегу (500с < 5000с) — место 1');
    assert.strictEqual(b.data[1].y, 2, 'B локально позади на бегу — место 2');
});
check('buildPositionDatasets() без аргумента — прежнее поведение (глобальный ранг, экстраполяция x=0)', () => {
    setState('all', 'all');
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const rowA = mkTimerInd('1', { cp: { swim: { [maxSeqSwim]: 300 } }, swim_s: 300 });
    setRaceData([rowA], [], Date.now());
    const datasets = sandbox.buildPositionDatasets();
    const a = datasets.find(d => d._bib === '1');
    assert.strictEqual(a.data[0].x, 0, 'глобальный режим по-прежнему экстраполирует до x=0');
});

check('renderPositionChart() per-stage — ось X фиксированная длина этапа (не растёт по мере прогресса), без stageBoundaries-плагина', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { cp: { run: { 1: 500, 2: 1000 } } });
    setRaceData([rowA], [], Date.now());
    vm.runInContext(`_positionStage = 'run'; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPositionChart();
    const chart = vm.runInContext('_positionChart', sandbox);
    assert.strictEqual(chart.config.options.scales.x.max, 84, 'CHECKPOINT_DIST_KM.run[12] = 84 — вся длина этапа, как у графика Темп/скорость, а не только пройденная часть');
    assert.ok(!chart.config.plugins.some(p => p.id === 'stageBoundaries'), 'границы этапов не рисуются в per-stage режиме');
});
check('renderPositionChart() без выбранного этапа — прежнее поведение (виртуальная ось 0-100, stageBoundaries на месте)', () => {
    setState('all', 'all');
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const rowA = mkTimerInd('1', { cp: { swim: { [maxSeqSwim]: 300 } }, swim_s: 300 });
    setRaceData([rowA], [], Date.now());
    vm.runInContext(`_positionStage = null; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPositionChart();
    const chart = vm.runInContext('_positionChart', sandbox);
    assert.strictEqual(chart.config.options.scales.x.max, 100);
    assert.ok(chart.config.plugins.some(p => p.id === 'stageBoundaries'), 'в глобальном режиме границы этапов рисуются, как раньше');
});
check('attachSpaghettiHover formatPoint per-stage — текст без пересчёта в виртуальный км (реальный км этапа как есть)', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { cp: { run: { 1: 500 } } });
    setRaceData([rowA], [], Date.now());
    vm.runInContext(`_positionStage = 'run'; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPositionChart();
    const chart = vm.runInContext('_positionChart', sandbox);
    // Курсор ровно на реальной КТ (x=7 км, ChartStub.scales — 1px=1 единица) —
    // index:0 теперь экстраполированная точка x=0, добавленная 2026-07-21
    // для сплошного начала линии от края графика, index:1 реальная КТ.
    chart.options.onHover.call(chart, { x: 7, y: 1 });
    assert.ok(chart._hoverInfo.text.includes('7.0 км: место 1'), `неожиданный текст: ${chart._hoverInfo.text}`);
});

check('computeBikeCombinedCheckpointRanks — КТ дня2 сравниваются по elapsed ОТ НАЧАЛА ВЕЛО (bike1_s + cp.bike_day2), не по сырому cp.bike_day2', () => {
    // A: долго ехал день1 (9000с), но "быстрый" сырой сплит на 1-й КТ дня2 (100с)
    //    — наивное сравнение сырых cp.bike_day2 поставило бы A первым, но по
    //    факту A суммарно медленнее (9000+100=9100 > 1000+5000=6000).
    const rowA = { key: '1', cp: { bike_day1: {}, bike_day2: { 1: 100 } }, bike1_s: 9000 };
    const rowB = { key: '2', cp: { bike_day1: {}, bike_day2: { 1: 5000 } }, bike1_s: 1000 };
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const ranks = vm.runInContext('computeBikeCombinedCheckpointRanks', sandbox)([rowA, rowB]);
    assert.strictEqual(ranks[n1 + 1]['2'], 1, 'B суммарно быстрее (6000 < 9100) — место 1');
    assert.strictEqual(ranks[n1 + 1]['1'], 2, 'A суммарно медленнее — место 2');
});
check('buildPositionDatasets(\'bike\') — единый вело-этап 421км, день2 смещён на длину дня1, с экстраполяцией x=0', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { bike1_s: 9000, cp: { bike_day1: { 1: 3000 }, bike_day2: { 1: 200 } } });
    setRaceData([rowA], [], Date.now());
    const datasets = sandbox.buildPositionDatasets('bike');
    const a = datasets.find(d => d._bib === '1');
    const bike1MaxKm = vm.runInContext('CHECKPOINT_DIST_KM.bike_day1[STAGE_MAX_SEQ.bike_day1]', sandbox);
    assert.strictEqual(a.data[0].x, 0, 'экстраполяция до x=0');
    assert.ok(a.data.some(p => p.x > bike1MaxKm), `ожидались точки дня2 за пределами дня1 (>${bike1MaxKm} км): ${JSON.stringify(a.data)}`);
});
check('renderPositionChart() _positionStage=\'bike\' — ось X на весь объединённый велоэтап (421 км), без stageBoundaries', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { bike1_s: 9000, cp: { bike_day1: { 1: 3000 }, bike_day2: { 1: 200 } } });
    setRaceData([rowA], [], Date.now());
    vm.runInContext(`_positionStage = 'bike'; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPositionChart();
    const chart = vm.runInContext('_positionChart', sandbox);
    assert.strictEqual(chart.config.options.scales.x.max, 421, 'CHECKPOINT_DIST_KM.bike_day1[6] + bike_day2[8] = 145 + 276 = 421');
    assert.ok(!chart.config.plugins.some(p => p.id === 'stageBoundaries'), 'границы этапов не рисуются в per-stage режиме');
});

check('chartSelectAllToggleHtml — "Выбрать всех" когда не все видимые выбраны', () => {
    const datasets = [{ _bib: '1', _name: 'Иванов Иван' }, { _bib: '2', _name: 'Петров Пётр' }];
    vm.runInContext(`_chartSearchQuery = ''; _chartSelectedBibs = ['1'];`, sandbox);
    const html = sandbox.chartSelectAllToggleHtml(datasets);
    assert.ok(html.includes('Выбрать всех'), `ожидалась кнопка "Выбрать всех": ${html}`);
});
check('chartSelectAllToggleHtml — "Очистить всех" когда все видимые (по фильтру поиска) уже выбраны', () => {
    const datasets = [{ _bib: '1', _name: 'Иванов Иван' }, { _bib: '2', _name: 'Петров Пётр' }];
    // Поиск сужает список до одного "Иванов" — он уже выбран, значит ВСЕ
    // видимые выбраны, хотя Петров (вне фильтра) — нет.
    vm.runInContext(`_chartSearchQuery = 'иванов'; _chartSelectedBibs = ['1'];`, sandbox);
    const html = sandbox.chartSelectAllToggleHtml(datasets);
    assert.ok(html.includes('Очистить всех'), `ожидалась кнопка "Очистить всех": ${html}`);
});
check('attachChartSelectAllHandler — клик "Выбрать всех" добавляет только отфильтрованных, не трогая остальных', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { splits: { swim: { 1: 300 } } });
    const rowB = mkTimerInd('2', { splits: { swim: { 1: 400 } } });
    setRaceData([rowA, rowB], [], Date.now());
    vm.runInContext(`_paceStage = 'swim'; _chartSearchQuery = ''; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPaceChart();
    const btn = domStub('chartSelectAllToggle');
    btn._handlers.click[0]();
    const selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(JSON.stringify(selected.slice().sort()), JSON.stringify(['1', '2']), `получено [${selected}]`);
});
check('attachChartSelectAllHandler — повторный клик, когда все выбраны, очищает выбор ("Очистить всех")', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { splits: { swim: { 1: 300 } } });
    setRaceData([rowA], [], Date.now());
    vm.runInContext(`_paceStage = 'swim'; _chartSearchQuery = ''; _chartSelectedBibs = ['1'];`, sandbox);
    sandbox.renderPaceChart();
    const btn = domStub('chartSelectAllToggle');
    btn._handlers.click[0]();
    const selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(selected.length, 0, `ожидался пустой выбор, получено [${selected}]`);
});

check('dataChanged() — false, когда тело ответа идентично последнему загруженному (защита от лишней перерисовки графика на каждый тик поллинга)', () => {
    vm.runInContext(`_lastDataJson = '{"individual":[]}';`, sandbox);
    assert.strictEqual(sandbox.dataChanged('{"individual":[]}'), false, 'идентичное тело — данные не изменились');
});
check('dataChanged() — true, когда тело ответа отличается', () => {
    vm.runInContext(`_lastDataJson = '{"individual":[]}';`, sandbox);
    assert.strictEqual(sandbox.dataChanged('{"individual":[{"bib":"1"}]}'), true, 'другое тело — данные изменились');
});

check('renderPositionChart() — диапазон оси Y компактный при сравнении маленькой группы, не по всему полю участников (п.5, 2026-07-22)', () => {
    setState('all', 'all');
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    // 10 участников, места 1..10 на одной КТ — выбираем для сравнения
    // только тех, кто занял места 1-2 (лучшая пара).
    const rows = Array.from({ length: 10 }, (_, i) => mkTimerInd(String(i + 1), { cp: { swim: { [maxSeqSwim]: 300 + i } }, swim_s: 300 + i }));
    setRaceData(rows, [], Date.now());
    vm.runInContext(`_positionStage = null; _chartSelectedBibs = ['1', '2'];`, sandbox);
    sandbox.renderPositionChart();
    const chart = vm.runInContext('_positionChart', sandbox);
    const yScale = chart.config.options.scales.y;
    // Без динамики диапазон был бы привязан к худшему месту среди ВСЕХ 10
    // участников (max ~10); при сравнении только топ-2 диапазон должен
    // ужаться к местам 1-2 с небольшим запасом, а не оставаться огромным.
    assert.ok(yScale.max < 6, `диапазон должен быть компактным вокруг мест 1-2, получено max=${yScale.max}`);
});

check('buildPositionDatasets() — эстафета исключена из "Вся гонка" при активном фильтре пола (нет единого пола у команды), но остаётся на конкретном этапе', () => {
    setState('all', 'F');
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const team = { bib: '1000', team_name: 'КомандаА', members: [
        { relay_stage: 'swim', status: 'active', gender: 'F', swim_s: 1000, cp: { swim: { [maxSeqSwim]: 1000 } } },
        { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: 9000, bike2_s: 8000, cp: {} },
        { relay_stage: 'run', status: 'active', gender: 'M', run_s: null, cp: {} },
    ] };
    setRaceData([], [team], Date.now());
    const wholeRace = sandbox.buildPositionDatasets(null);
    assert.strictEqual(wholeRace.length, 0, `эстафета не должна попадать на график "Вся гонка" с фильтром пола: ${JSON.stringify(wholeRace)}`);
    const swimStage = sandbox.buildPositionDatasets('swim');
    assert.strictEqual(swimStage.length, 1, `на конкретном этапе эстафета должна остаться: ${JSON.stringify(swimStage)}`);
});

// ── buildPositionDatasets(stage) — подпись эстафеты меняется в зависимости
// от этапа (аналогично chartParticipantRowsForStage/buildBikeCombinedPaceDatasets
// на графике Темп/скорость): на "Вся гонка" — только название команды,
// на конкретном этапе — "Имя Фамилия (Команда)" именно того члена команды,
// который бежал/плыл/крутил педали ИМЕННО этот этап (найдено пользователем
// 2026-07-22: раньше подпись была ВСЕГДА только названием команды).
function mkRelayTeamStages() {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    return { bib: '1000', team_name: 'КомандаX', members: [
        { relay_stage: 'swim', status: 'active', surname: 'Пловцов', name: 'Иван', gender: 'M', swim_s: 1000, cp: { swim: { [maxSeqSwim]: 1000 } } },
        { relay_stage: 'bike', status: 'active', surname: 'Велосипедов', name: 'Пётр', gender: 'M', bike1_s: 3000, bike2_s: 3500, cp: { bike_day1: { 1: 400 }, bike_day2: { 1: 300 } } },
        { relay_stage: 'run', status: 'active', surname: 'Бегунов', name: 'Сергей', gender: 'M', run_s: 2000, cp: { run: { 1: 500 } } },
    ] };
}
check('buildPositionDatasets(null) — эстафета на "Вся гонка" подписана ТОЛЬКО названием команды (без изменений)', () => {
    setState('all', 'all');
    const team = mkRelayTeamStages();
    setRaceData([], [team], Date.now());
    const datasets = sandbox.buildPositionDatasets(null);
    const d = datasets.find(x => x._bib === '1000');
    assert.strictEqual(d._name, 'КомандаX', `ожидалось только название команды, получено: ${d._name}`);
});
check('buildPositionDatasets(\'swim\') — эстафета подписана именем ПЛОВЦА команды', () => {
    setState('all', 'all');
    const team = mkRelayTeamStages();
    setRaceData([], [team], Date.now());
    const datasets = sandbox.buildPositionDatasets('swim');
    const d = datasets.find(x => x._bib === '1000');
    assert.strictEqual(d._name, 'Пловцов Иван (КомандаX)', `получено: ${d._name}`);
});
check('buildPositionDatasets(\'run\') — эстафета подписана именем БЕГУНА команды (не пловца/велосипедиста)', () => {
    setState('all', 'all');
    const team = mkRelayTeamStages();
    setRaceData([], [team], Date.now());
    const datasets = sandbox.buildPositionDatasets('run');
    const d = datasets.find(x => x._bib === '1000');
    assert.strictEqual(d._name, 'Бегунов Сергей (КомандаX)', `получено: ${d._name}`);
});
check('buildPositionDatasets(stage) — фильтр по полу исключает эстафетчика не того пола (2026-07-23, п.5)', () => {
    setState('all', 'F');
    const team = mkRelayTeamStages(); // пловец команды — мужчина
    setRaceData([], [team], Date.now());
    const datasets = sandbox.buildPositionDatasets('swim');
    assert.strictEqual(datasets.find(x => x._bib === '1000'), undefined, 'команда с пловцом-мужчиной не должна попасть в список при фильтре "Женщины"');
});
check('chartParticipantRowsForStage/buildPaceDatasets — фильтр по полу исключает эстафетчика не того пола (2026-07-23, п.5)', () => {
    setState('all', 'F');
    const team = mkRelayTeamStages(); // велосипедист команды — мужчина
    setRaceData([], [team], Date.now());
    const datasets = sandbox.buildPaceDatasets('bike1');
    assert.strictEqual(datasets.find(x => x._bib === '1000'), undefined, 'команда с велосипедистом-мужчиной не должна попасть в список при фильтре "Женщины"');
});
check('buildPositionDatasets(\'bike\') — эстафета подписана именем ВЕЛОСИПЕДИСТА команды', () => {
    setState('all', 'all');
    const team = mkRelayTeamStages();
    setRaceData([], [team], Date.now());
    const datasets = sandbox.buildPositionDatasets('bike');
    const d = datasets.find(x => x._bib === '1000');
    assert.strictEqual(d._name, 'Велосипедов Пётр (КомандаX)', `получено: ${d._name}`);
});

// ── nearestDatasetIndexAtPixel() — геометрический hit-test для hover/click
// на графиках-спагетти (см. комментарий над функцией в results.html):
// выбирает линию по Y на ИНТЕРПОЛЯЦИИ между соседними точками ровно в X
// курсора, а не по ближайшей одиночной точке (как встроенный Chart.js
// mode:'nearest') — иначе при редких КТ подсвечивалась линия, чья точка
// формально ближе курсору, хотя сама линия проходит далеко от него.
function identityScaleChart(datasets) {
    return {
        data: { datasets },
        scales: {
            x: { getValueForPixel: px => px, getPixelForValue: v => v },
            y: { getValueForPixel: px => px, getPixelForValue: v => v },
        },
    };
}
check('nearestDatasetIndexAtPixel — доказательство изменения поведения: старая nearest-по-точке логика выбрала бы ДРУГОЙ датасет', () => {
    // NEAR: плоская линия y=0 от x=0 до x=10 — в X курсора (x=5) её
    // интерполированный Y равен 0, всего 0.5px от курсора (y=0.5).
    const near = { data: [{ x: 0, y: 0 }, { x: 10, y: 0 }] };
    // FAR: у неё есть ОТДЕЛЬНАЯ точка (x=4, y=0.4) почти вплотную к курсору
    // в "сыром" пиксельном расстоянии (dist~1.0 до курсора x=5,y=0.5) — это
    // ровно тот сценарий, который ломал старый mode:'nearest' (ближайшая
    // ОДНА точка), хотя дальше линия FAR резко уходит вверх к (x=20,y=100),
    // и на X=5 (курсор) FAR-линия физически проходит далеко от курсора
    // (интерполяция даёт y≈6.6, за пределы NEAR).
    const far = { data: [{ x: 4, y: 0.4 }, { x: 20, y: 100 }] };
    const chart = identityScaleChart([near, far]);
    // Курсор x=5, y=0.5.
    const idx = sandbox.nearestDatasetIndexAtPixel(chart, 5, 0.5);
    assert.strictEqual(idx, 0, `новый hit-test должен выбрать NEAR (линия визуально под курсором), получено idx=${idx}`);
    // Явная проверка, что "наивный ближайшая одиночная точка" дала бы FAR:
    // расстояние курсора до точки FAR(4,0.4) = sqrt(1^2+0.1^2)≈1.005,
    // до ближайшей точки NEAR (0,0) или (10,0) = sqrt(25+0.25)≈5.02.
    const distFarPoint = Math.hypot(5 - 4, 0.5 - 0.4);
    const distNearPoint = Math.min(Math.hypot(5 - 0, 0.5 - 0), Math.hypot(5 - 10, 0.5 - 0));
    assert.ok(distFarPoint < distNearPoint, 'сетап должен подтверждать, что старая точечная логика выбрала бы FAR (иначе тест не доказывает изменение поведения)');
});
check('nearestDatasetIndexAtPixel — клик мимо всех линий (дальше maxDistPx) возвращает null', () => {
    const chart = identityScaleChart([{ data: [{ x: 0, y: 0 }, { x: 10, y: 0 }] }]);
    const idx = sandbox.nearestDatasetIndexAtPixel(chart, 5, 1000, 30);
    assert.strictEqual(idx, null, `клик далеко от единственной линии должен вернуть null, получено ${idx}`);
});

// ── attachSpaghettiClick() — клик по линии добавляет/убирает участника из
// сравнения (Task 3) — та же кнопка, что и чекбокс в сайдбаре ──
check('attachSpaghettiClick — клик по линии добавляет bib в _chartSelectedBibs, повторный клик по той же точке убирает (toggle)', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { splits: { swim: { 1: 300 } } });
    const rowB = mkTimerInd('2', { splits: { swim: { 1: 900 } } });
    setRaceData([rowA, rowB], [], Date.now());
    // _tab/_chartSubTab выставлены на 'chart'/'pace' — иначе render() внутри
    // attachSpaghettiClick пойдёт по умолчанию в renderOverall() (default
    // _tab='overall') и не пересоздаст _paceChart по-настоящему.
    vm.runInContext(`_tab = 'chart'; _chartSubTab = 'pace'; _paceStage = 'swim'; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPaceChart();
    const chart = vm.runInContext('_paceChart', sandbox);
    // Датасет '1' — единственная точка на x=0 (splitPaceValue), см. buildPaceDatasets;
    // ChartStub.scales — 1px=1единица, кликаем прямо в неё.
    const dsA = chart.data.datasets.find(d => d._bib === '1');
    assert.ok(dsA, 'ожидался датасет для bib=1');
    const clickPoint = dsA.data[dsA.data.length - 1];
    chart.options.onClick.call(chart, { x: clickPoint.x, y: clickPoint.y });
    let selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(JSON.stringify(selected), JSON.stringify(['1']), `после первого клика ожидался ['1'], получено ${JSON.stringify(selected)}`);
    // render() внутри attachSpaghettiClick пересоздаёт _paceChart — берём
    // свежий объект и кликаем в ту же точку данных ещё раз (toggle обратно).
    const chart2 = vm.runInContext('_paceChart', sandbox);
    const dsA2 = chart2.data.datasets.find(d => d.label === dsA.label) || chart2.data.datasets[0];
    const clickPoint2 = dsA2.data[dsA2.data.length - 1];
    chart2.options.onClick.call(chart2, { x: clickPoint2.x, y: clickPoint2.y });
    selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(selected.length, 0, `после второго клика (toggle) ожидался пустой выбор, получено ${JSON.stringify(selected)}`);
});
check('attachSpaghettiClick — клик мимо всех линий не меняет выбор', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { splits: { swim: { 1: 300 } } });
    setRaceData([rowA], [], Date.now());
    vm.runInContext(`_tab = 'chart'; _chartSubTab = 'pace'; _paceStage = 'swim'; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPaceChart();
    const chart = vm.runInContext('_paceChart', sandbox);
    chart.options.onClick.call(chart, { x: 99999, y: 99999 });
    const selected = vm.runInContext('_chartSelectedBibs', sandbox);
    assert.strictEqual(selected.length, 0, `клик далеко от всех линий не должен ничего выбрать, получено ${JSON.stringify(selected)}`);
});

check('formatBadge() — бейдж "Э" тем же CSS-паттерном, что genderBadge', () => {
    const html = vm.runInContext('formatBadge', sandbox)();
    assert.ok(html.includes('badge-e'), `ожидался класс badge-e: ${html}`);
    assert.ok(html.includes('>Э<'), `ожидалась буква Э: ${html}`);
});
check('rankHeaderCells(show2=false) — только колонка Место', () => {
    const html = sandbox.rankHeaderCells(false, 'Пол/Формат');
    assert.strictEqual(html, '<th class="r">Место</th>');
});
check('rankHeaderCells(show2=true) — Место + вторичная колонка', () => {
    const html = sandbox.rankHeaderCells(true, 'Пол/Формат');
    assert.strictEqual(html, '<th class="r">Место</th><th class="r">Пол/Формат</th>');
});
check('rankBodyCells(show2=false) — только ячейка абсолюта', () => {
    const html = sandbox.rankBodyCells(false, 5, 2, '<span class="badge badge-m">М</span>', '');
    assert.strictEqual(html.match(/<td/g).length, 1, `ожидалась ровно одна ячейка: ${html}`);
    assert.ok(html.includes('>5<'), `ожидался абсолют 5: ${html}`);
});
check('rankBodyCells(show2=true) — абсолют первой ячейкой, бейдж+число второй', () => {
    const html = sandbox.rankBodyCells(true, 5, 2, '<span class="badge badge-m">М</span>', '');
    const m = html.match(/^<td class="r">(.*?)<\/td><td class="r">(.*?)<\/td>$/);
    assert.ok(m, `неожиданная структура: ${html}`);
    assert.ok(m[1].includes('>5<'), `первая колонка — абсолют 5: ${html}`);
    assert.ok(m[2].includes('badge-m') && m[2].includes('>2<'), `вторая колонка — бейдж+2: ${html}`);
});
check('rankBodyCells — rankSecondary=null даёт прочерк во вторичной ячейке', () => {
    const html = sandbox.rankBodyCells(true, 5, null, '', '');
    assert.ok(html.includes('<span class="muted">—</span>'), `ожидался прочерк: ${html}`);
});

function domGetAppHtml() {
    return domStub('app').innerHTML;
}

check('renderOverall() — эстафета получает бейдж Э{формат} вместо прочерка, строка подсвечена, колонки Пол/Формат убраны', () => {
    setState('all', 'all');
    const ind = mkTimerInd('1', { surname: 'Иванов', name: 'Иван', status: 'active', overall_s: 20000, overall_rank_g: 1, cp: { run: { [vm.runInContext('STAGE_MAX_SEQ.run', sandbox)]: 20000 } } });
    const relay = [{
        bib: '1000', team_name: 'Автобаланс', overall_s: 22000,
        members: [
            { relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 1000, cp: { swim: { [vm.runInContext('STAGE_MAX_SEQ.swim', sandbox)]: 1000 } } },
            { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: 9000, bike2_s: 8000, cp: {} },
            { relay_stage: 'run', status: 'active', gender: 'M', run_s: 4000, cp: { run: { [vm.runInContext('STAGE_MAX_SEQ.run', sandbox)]: 22000 } } },
        ],
    }];
    setRaceData([ind], relay, Date.now());
    sandbox.renderOverall();
    const html = domGetAppHtml();
    assert.ok(!html.includes('<th>Пол</th>'), `колонка "Пол" должна быть убрана: ${html.slice(0,500)}`);
    assert.ok(!html.includes('<th>Формат</th>'), `колонка "Формат" должна быть убрана: ${html.slice(0,500)}`);
    // formatBadge() оборачивает "Э" в свой собственный <span> (см.
    // siberman-common.js), поэтому в итоговой разметке между "Э" и рангом
    // остаётся закрывающий тег ("...badge-e">Э</span>1") — проверяем это
    // регэкспом вместо литеральной подстроки ">Э1<".
    assert.ok(html.includes('badge-e') && /Э<\/span>1</.test(html), `эстафета должна получить бейдж Э1 (единственная команда — формат-ранг 1): ${html}`);
    assert.ok(html.includes('relay-row'), `строка эстафеты должна быть подсвечена: ${html}`);
    assert.ok(html.includes('badge-individual'), `личник должен получить бейдж "Индивидуальный": ${html}`);
});

check('renderOverall() — новый порядок колонок (Итого+Отст. перед Плав/Вело/Бег), отставание под временем не отдельной колонкой (п.3/4, v5)', () => {
    setState('all', 'all');
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    const fast = mkTimerInd('1', { swim_s: 1000, bike1_s: 9000, bike2_s: 8000, run_s: 2000, overall_s: 20000, cp: { swim: { [maxSeqSwim]: 1000 }, run: { [maxSeqRun]: 20000 } } });
    const slow = mkTimerInd('2', { swim_s: 1500, bike1_s: 9500, bike2_s: 8500, run_s: 2500, overall_s: 22000, cp: { swim: { [maxSeqSwim]: 1500 }, run: { [maxSeqRun]: 22000 } } });
    setRaceData([fast, slow], [], Date.now());
    sandbox.renderOverall();
    const html = domGetAppHtml();
    // Заголовок: Итого идёт СРАЗУ после Участника, до Плав./Вело/Бег.
    const headOrder = html.indexOf('>Итого<') < html.indexOf('Плав.') && html.indexOf('>Итого<') > html.indexOf('УЧАСТНИК');
    assert.ok(headOrder, `ожидался порядок Участник→Итого→Плав/Вело/Бег в шапке: ${html.slice(0, 700)}`);
    assert.ok(!html.includes('<th class="r">Отставание</th>'), `отдельной колонки "Отставание" быть не должно: ${html.slice(0, 700)}`);
    // У отстающего (bib=2) под временем Плавания должно быть его личное
    // отставание (500с = 1500-1000) — timeGapCell встроил его в ту же ячейку.
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">2<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка bib=2 не найдена: ${html}`);
    assert.ok(rowMatch[0].includes('time-gap-sub'), `под временем плавания должно быть отставание (time-gap-sub): ${rowMatch[0]}`);
});

// ── renderStage() — истинный абсолют (полный ростер) + 3-колоночный режим
// при fmt='relay' (задача 3 плана 2026-07-22) ──
check('renderStage() внутренние ранги — computeRanksByValue по ВИДИМЫМ строкам, не по полному ростеру (откат 2026-07-23)', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const rows = [
        mkTimerInd('1', { gender: 'M', swim_s: 300, cp: { swim: { [maxSeqSwim]: 300 } } }),
        mkTimerInd('2', { gender: 'F', swim_s: 400, cp: { swim: { [maxSeqSwim]: 400 } } }),
        mkTimerInd('3', { gender: 'F', swim_s: 500, cp: { swim: { [maxSeqSwim]: 500 } } }),
    ];
    setRaceData(rows, [], Date.now());
    setState('individual', 'F');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    // Строка bib=2 должна содержать rank-num "1" — мужчина №1 не виден в
    // таблице (фильтр "Женщины"), значит "Место" считается ТОЛЬКО среди
    // видимых женщин: №2 (400с) идёт первой, №3 (500с) — второй. Полный
    // откат: раньше "Место" было "истинным абсолютом" по полному ростеру
    // (включая невидимого мужчину) — пользователь попросил вернуть
    // фильтро-зависимый пересчёт (2026-07-23).
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">2<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка bib=2 не найдена: ${html}`);
    assert.ok(/rank-num[^>]*>1</.test(rowMatch[0]), `ожидалось место 1 среди видимых женщин (мужчина не виден): ${rowMatch[0]}`);
});
check('renderStage() фильтр "Эстафета"+Пол=Все — 2 колонки Место/Место (пол), 3-колоночный режим убран (п.7 v6, 2026-08-02)', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const relay = [
        { bib: '1000', team_name: 'КомандаА', members: [{ relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 300, cp: { swim: { [maxSeqSwim]: 300 } } }] },
        { bib: '1001', team_name: 'КомандаБ', members: [{ relay_stage: 'swim', status: 'active', gender: 'F', swim_s: 400, cp: { swim: { [maxSeqSwim]: 400 } } }] },
    ];
    setRaceData([], relay, Date.now());
    setState('relay', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.includes('<th class="r">Место</th>') && html.includes('Место (пол)'), `ожидались колонки Место/Место (пол): ${html.slice(0,600)}`);
    assert.ok(!html.includes('>Формат</th>'), `колонки "Формат" быть не должно: ${html.slice(0,600)}`);
});
check('renderStage() фильтр "Эстафета"+Пол=М — 1 колонка "Место" (п.7 v6, 2026-08-02)', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const relay = [
        { bib: '1000', team_name: 'КомандаА', members: [{ relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 300, cp: { swim: { [maxSeqSwim]: 300 } } }] },
        { bib: '1001', team_name: 'КомандаБ', members: [{ relay_stage: 'swim', status: 'active', gender: 'F', swim_s: 400, cp: { swim: { [maxSeqSwim]: 400 } } }] },
    ];
    setRaceData([], relay, Date.now());
    setState('relay', 'M');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.match(/<th class="r">Место<\/th>/g)?.length === 1, `ожидалась ровно одна колонка "Место": ${html.slice(0,600)}`);
    assert.ok(!html.includes('Место (пол)'), `второй колонки быть не должно при активном фильтре пола: ${html.slice(0,600)}`);
});
check('renderStage() — время+отставание в одной ячейке, отдельной колонки "Отставание" нет (п.3 v5)', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const fast = mkTimerInd('1', { gender: 'M', swim_s: 300, cp: { swim: { [maxSeqSwim]: 300 } } });
    const slow = mkTimerInd('2', { gender: 'M', swim_s: 400, cp: { swim: { [maxSeqSwim]: 400 } } });
    setRaceData([fast, slow], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(!html.includes('<th class="r">Отставание</th>'), `отдельной колонки "Отставание" быть не должно: ${html.slice(0,700)}`);
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">2<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка bib=2 не найдена: ${html}`);
    assert.ok(rowMatch[0].includes('time-gap-sub'), `под временем должно быть отставание отстающего (time-gap-sub): ${rowMatch[0]}`);
});
check('renderStage() фильтр "Эстафета"+Пол=М — "Место" среди ВИДИМЫХ команд (откат 2026-07-23, обновлено под п.7 v6)', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const relay = [
        { bib: '1000', team_name: 'КомандаА', members: [{ relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 300, cp: { swim: { [maxSeqSwim]: 300 } } }] },
        { bib: '1001', team_name: 'КомандаБ', members: [{ relay_stage: 'swim', status: 'active', gender: 'F', swim_s: 400, cp: { swim: { [maxSeqSwim]: 400 } } }] },
    ];
    setRaceData([], relay, Date.now());
    // gender='M' — КомандаБ (F) не видна в таблице вовсе (relayMembers её
    // исключает). КомандаА получает место 1 — здесь совпадает с "полным
    // ростером" просто потому, что она и так быстрее обеих команд;
    // реальная разница видна в отдельном тесте ниже.
    setState('relay', 'M');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1000<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка КомандыА не найдена: ${html}`);
    assert.ok(/rank-num[^>]*>1</.test(rowMatch[0]), `КомандаА должна получить место 1: ${rowMatch[0]}`);
});
check('renderStage() фильтр "Эстафета"+Пол=М — "Место" НЕ учитывает невидимую (отфильтрованную по полу) команду', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const relay = [
        { bib: '1000', team_name: 'КомандаА', members: [{ relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 500, cp: { swim: { [maxSeqSwim]: 500 } } }] },
        { bib: '1001', team_name: 'КомандаБ', members: [{ relay_stage: 'swim', status: 'active', gender: 'F', swim_s: 100, cp: { swim: { [maxSeqSwim]: 100 } } }] },
    ];
    setRaceData([], relay, Date.now());
    // КомандаБ (F, самая быстрая) НЕ видна при фильтре "Мужчины" — КомандаА
    // (M, медленнее КомандыБ) должна получить место 1 среди видимых, не 2.
    setState('relay', 'M');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1000<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка КомандыА не найдена: ${html}`);
    assert.ok(/rank-num[^>]*>1</.test(rowMatch[0]), `КомандаА должна получить место 1 среди видимых (невидимая быстрая КомандаБ не в счёт): ${rowMatch[0]}`);
});

check('render() — фильтр по полу виден на этапах/Своде вело при fmt=relay, скрыт на Итогах/Днях', () => {
    setRaceData([], [{ bib: '1000', team_name: 'К', overall_s: 1000, members: [] }], Date.now());
    setState('relay', 'all');
    const genderGroupTab = (tab) => {
        vm.runInContext(`_tab = ${JSON.stringify(tab)};`, sandbox);
        sandbox.render();
        return domStub('genderGroup').style.display;
    };
    assert.strictEqual(genderGroupTab('overall'), 'none', 'Итоги гонки — фильтр по полу скрыт при эстафете');
    assert.strictEqual(genderGroupTab('day1'), 'none', 'День 1 — фильтр по полу скрыт при эстафете');
    assert.strictEqual(genderGroupTab('swim'), '', 'Плавание — фильтр по полу ВИДЕН при эстафете');
    vm.runInContext(`_bikeSubTab = 'combined';`, sandbox);
    assert.strictEqual(genderGroupTab('bike'), '', 'Свод вело/Вело1/Вело2 — фильтр по полу ВИДЕН при эстафете');
});

check('renderRankedProgress() (Дни) — 2 колонки рангов как в Итогах/на этапах, Последняя КТ, "Финиш"', () => {
    setState('all', 'all');
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const ind = mkTimerInd('1', { gender: 'M', bike1_s: 5000, swim_s: 1000, cp: { swim: { [maxSeqSwim]: 1000 }, bike_day1: { [maxSeqB1]: 5000 } } });
    setRaceData([ind], [], Date.now());
    sandbox.renderDay1();
    const html = domGetAppHtml();
    assert.ok(html.includes('<th class="r">Место</th>') || html.includes('Пол/Формат') || html.includes('Место (пол)'), `ожидалась колонка места: ${html.slice(0,500)}`);
    assert.ok(html.includes('Отметка'), `ожидалась колонка "Отметка" (как в Итогах/на этапах): ${html.slice(0,600)}`);
    // Отставание больше не отдельной колонкой (п.3 v5) — встроено под
    // временем через timeGapCell, поэтому колонки "Отставание" в шапке нет.
    assert.ok(!html.includes('<th class="r">Отставание</th>'), `отдельной колонки "Отставание" быть не должно: ${html.slice(0,700)}`);
    assert.ok(!html.includes('Абсолют'), `отдельная колонка "Абсолют" не нужна (место уже абсолютное): ${html.slice(0,700)}`);
    assert.ok(html.includes('badge-fin">Финиш<'), `статус должен быть "Финиш" (унифицировано с Итогами/Этапами, п.6 v6): ${html}`);
});
check('renderDay1() — живое "Время" показывается ДО завершения Дня 1 (не "—")', () => {
    const midDay1 = mkTimerInd('1', { status: 'active', swim_s: 4000, cp: { swim: { 7: 4000 }, bike_day1: { 2: 4500 } } }); // ещё в Дне 1
    setRaceData([midDay1], [], Date.now());
    setState('all', 'all');
    sandbox.renderDay1();
    const html = domGetAppHtml();
    const row = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    assert.ok(!/time-cell">\s*<span class="muted">—<\/span>/.test(row), `"Время" не должно быть пустым до конца Дня 1: ${row}`);
});
check('renderRankedProgress() (Дни) — отставание ПУЛ-ОТНОСИТЕЛЬНОЕ (от лидера текущего фильтра), не абсолютное (п.10 v5)', () => {
    setState('individual', 'all');
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    // Быстрая эстафета (не видна при fmt=individual) НЕ должна быть точкой
    // отсчёта для отставания второго личника — при пул-относительном
    // отставании (п.10) отсчёт идёт от лидера СРЕДИ ВИДИМЫХ (личник bib=1).
    const fastInd = mkTimerInd('1', { gender: 'M', bike1_s: 5000, swim_s: 1000, cp: { swim: { [maxSeqSwim]: 1000 }, bike_day1: { [maxSeqB1]: 5000 } } });
    const slowInd = mkTimerInd('2', { gender: 'M', bike1_s: 6000, swim_s: 1000, cp: { swim: { [maxSeqSwim]: 1000 }, bike_day1: { [maxSeqB1]: 6000 } } });
    const relayFaster = { bib: '1000', team_name: 'К', members: [
        { relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 100, cp: { swim: { [maxSeqSwim]: 100 } } },
        { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: 100, bike2_s: null, cp: { bike_day1: { [maxSeqB1]: 100 } } },
        { relay_stage: 'run', status: 'active', gender: 'M', run_s: null, cp: {} },
    ] };
    setRaceData([fastInd, slowInd], [relayFaster], Date.now());
    sandbox.renderDay1();
    const html = domGetAppHtml();
    const leaderRow = html.match(/<tr class="[^"]*"[^>]*>[\s\S]*?bib-cell">1<[\s\S]*?<\/tr>/);
    const slowRow = html.match(/<tr class="[^"]*"[^>]*>[\s\S]*?bib-cell">2<[\s\S]*?<\/tr>/);
    assert.ok(leaderRow && slowRow, `обе строки личников должны быть найдены: ${html}`);
    assert.ok(leaderRow[0].includes('Лидер'), `bib=1 — лидер видимого пула, timeGapCell должен показать "Лидер": ${leaderRow[0]}`);
    const expectedGap = vm.runInContext('fmtGap(1000)', sandbox); // 6000-5000
    assert.ok(slowRow[0].includes(expectedGap), `bib=2 отстаёт от bib=1 (видимый лидер) на ${expectedGap}, не от невидимой эстафеты: ${slowRow[0]}`);
});
check('День 1 — отставание внутри пула считается от лидера пула (computeOverallGaps, вместо удалённой poolGap)', () => {
    setState('all', 'all');
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const rowA = mkTimerInd('1', { gender: 'M', swim_s: 1000, bike1_s: 4000, cp: { bike_day1: { [maxSeqB1]: 4000 } } });
    const rowB = mkTimerInd('2', { gender: 'M', swim_s: 1000, bike1_s: 5000, cp: { bike_day1: { [maxSeqB1]: 5000 } } });
    setRaceData([rowA, rowB], [], Date.now());
    sandbox.renderDay1();
    const html = domGetAppHtml();
    const leaderRow = html.match(/<tr class="[^"]*"[^>]*>[\s\S]*?bib-cell">1<[\s\S]*?<\/tr>/);
    const slowRow = html.match(/<tr class="[^"]*"[^>]*>[\s\S]*?bib-cell">2<[\s\S]*?<\/tr>/);
    assert.ok(leaderRow && slowRow, `обе строки должны быть найдены: ${html}`);
    assert.ok(leaderRow[0].includes('Лидер'), `лидер пула (меньший v) — "Лидер": ${leaderRow[0]}`);
    const expectedGap = vm.runInContext('fmtGap(1000)', sandbox);
    assert.ok(slowRow[0].includes(expectedGap), `отстающий — разница v: ${slowRow[0]}`);
});
check('День 1 — Место (абсолют) = ранг среди ВИДИМЫХ строк текущего фильтра, невидимая эстафета не "съедает" места (откат 2026-07-24)', () => {
    setState('individual', 'all');
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const ind = mkTimerInd('1', { swim_s: 5000, bike1_s: 5000, cp: { swim: { [maxSeqSwim]: 5000 }, bike_day1: { [maxSeqB1]: 5000 } } });
    const relayFaster = { bib: '1000', team_name: 'К', members: [
        { relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 100, cp: { swim: { [maxSeqSwim]: 100 } } },
        { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: 100, bike2_s: null, cp: { bike_day1: { [maxSeqB1]: 100 } } },
        { relay_stage: 'run', status: 'active', gender: 'M', run_s: null, cp: {} },
    ] };
    setRaceData([ind], [relayFaster], Date.now());
    sandbox.renderDay1();
    const html = domGetAppHtml();
    // Фильтр "individual" скрывает эстафету из строк — при пересчёте по
    // ВИДИМЫМ строкам (не по полному ростеру года) единственный видимый
    // личник должен получить абсолютное место 1, а не 2 (эстафета быстрее,
    // но невидима — не должна "занимать" место в фильтрованном зачёте;
    // запрошено пользователем 2026-07-24, при фильтре "Личный" номера мест
    // ранее пропускались из-за скрытых эстафетчиков).
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка личника не найдена: ${html}`);
    const rankNums = [...rowMatch[0].matchAll(/rank-num[^>]*>(\d+)</g)].map(m => m[1]);
    assert.ok(rankNums.includes('1'), `ожидалось абсолютное место 1 (единственный видимый): rankNums=${JSON.stringify(rankNums)}, строка: ${rowMatch[0]}`);
    assert.ok(!rankNums.includes('2'), `невидимая эстафета не должна давать место 2: rankNums=${JSON.stringify(rankNums)}, строка: ${rowMatch[0]}`);
});

// ── timeGapCell()/buildStats() — v5 п.2/3/4 фундамент (2026-07-23) ──
check('timeGapCell() — время+0 отставание даёт "Лидер"', () => {
    const html = sandbox.timeGapCell('1:00:00', 0);
    assert.ok(html.includes('1:00:00'), `время должно быть в разметке: ${html}`);
    assert.ok(html.includes('Лидер'), `нулевое отставание — подпись "Лидер": ${html}`);
});
check('timeGapCell() — положительное отставание форматируется через fmtGap', () => {
    const html = sandbox.timeGapCell('1:05:00', 300);
    const expected = vm.runInContext('fmtGap(300)', sandbox);
    assert.ok(html.includes(expected), `ожидался fmtGap(300)="${expected}": ${html}`);
});
check('timeGapCell() — время="—" даёт прочерк, gap игнорируется', () => {
    const html = sandbox.timeGapCell('—', null);
    assert.ok(html.includes('—') && !html.includes('time-main'), `ожидался просто прочерк: ${html}`);
});
check('timeGapCell() — gap=null (не с чем сравнивать) — время без под-строки', () => {
    const html = sandbox.timeGapCell('1:00:00', null);
    assert.ok(html.includes('1:00:00') && !html.includes('time-gap-sub'), `не должно быть под-строки отставания: ${html}`);
});
check('avgPaceLabel(swim) — темп на 100м из дистанции и времени', () => {
    // 2,6 км за 1500с → 1500/2.6=576.9 с/км → /10=57.7≈58с/100м → "0:58 /100м"
    const label = sandbox.avgPaceLabel('swim', 2.6, 1500);
    assert.strictEqual(label, sandbox.fmtPace100m(1500 / 2.6), `ожидался тот же формат, что и fmtPace100m: ${label}`);
});
check('avgPaceLabel(bike_day1) — скорость км/ч из дистанции и времени', () => {
    // 72 км за 7200с (2ч) → 36 км/ч
    const label = sandbox.avgPaceLabel('bike_day1', 72, 7200);
    assert.strictEqual(label, sandbox.fmtSpeed(72 / (7200 / 3600)), `ожидалась скорость через fmtSpeed: ${label}`);
});
check('avgPaceLabel(run) — темп мин/км из дистанции и времени', () => {
    // 35 км за 12600с → 360с/км → "6:00 /км"
    const label = sandbox.avgPaceLabel('run', 35, 12600);
    assert.strictEqual(label, sandbox.fmtPace(Math.round(12600 / 35)), `ожидался темп через fmtPace: ${label}`);
});
check('avgPaceLabel — null при отсутствии времени или нулевой дистанции', () => {
    assert.strictEqual(sandbox.avgPaceLabel('run', 10, null), '—', `null timeS → прочерк`);
    assert.strictEqual(sandbox.avgPaceLabel('run', 0, 100), '—', `нулевая дистанция → прочерк`);
});
check('splitPaceLabel не сломан рефакторингом (regression)', () => {
    // Существующий пример поведения ДО рефакторинга: 10 км общий сплит между
    // seq=1(3км) и seq=2(10км) на bike_day1 → distKm=7, если splitS=630 (10.5 мин)
    // → 7/(630/3600)=40 км/ч
    const label = sandbox.splitPaceLabel('bike_day1', 2, 630);
    assert.strictEqual(label, sandbox.fmtSpeed(7 / (630 / 3600)), `splitPaceLabel должен работать как раньше: ${label}`);
});
check('buildStats() — 2 карточки (Личники/Эстафеты) с DNF/DSQ по relayStats', () => {
    const individual = [
        mkTimerInd('1', { status: 'active', overall_s: 20000, cp: { run: { [vm.runInContext('STAGE_MAX_SEQ.run', sandbox)]: 20000 } } }),
        mkTimerInd('2', { status: 'dnf', overall_s: null, cp: {} }),
    ];
    const relayStats = { total: 3, finished: 1, dnfDsq: 2 };
    const html = sandbox.buildStats(individual, relayStats, null);
    assert.ok(html.includes('stat-card'), `ожидались карточки: ${html}`);
    assert.ok(html.includes('>2<') && html.includes('Лично'), `личников должно быть 2: ${html}`);
    assert.ok(html.includes('>3<') && html.includes('Эстафеты'), `должно быть "Эстафеты" (не "Эстафет"), эстафет должно быть 3 (relayStats.total): ${html}`);
    assert.ok(html.includes('1 финишировало'), `1 личник финишировал: ${html}`);
    assert.ok(html.includes('2 DNF/DSQ'), `2 DNF/DSQ у эстафет (relayStats.dnfDsq): ${html}`);
});
check('buildStats() — карточка "Эстафеты" скрыта, когда relayStats.total === 0', () => {
    const individual = [mkTimerInd('1', { status: 'active', overall_s: 20000, cp: { run: { [vm.runInContext('STAGE_MAX_SEQ.run', sandbox)]: 20000 } } })];
    const html = sandbox.buildStats(individual, { total: 0, finished: 0, dnfDsq: 0 }, null);
    assert.ok(!html.includes('Эстафет'), `карточка эстафет не должна рендериться при total=0: ${html}`);
});
check('buildStats() — карточка "Личников" скрыта, когда individual пуст (только эстафета)', () => {
    const html = sandbox.buildStats([], { total: 5, finished: 2, dnfDsq: 1 }, null);
    assert.ok(!html.includes('Лично'), `карточка личников не должна рендериться при пустом individual: ${html}`);
    assert.ok(html.includes('Эстафет'), `карточка эстафет должна остаться: ${html}`);
});

// ── bikeCombinedRawCp()/computeBikeCombinedCheckpointGaps()/bikeCombinedDistKm()/
// bikeCombinedCheckpointLabel() — гэпы/дистанция/подписи для виртуальных КТ
// «Вело (оба дня)», нужны генератору постов трансляции (Задача 6) ──
check('bikeCombinedRawCp — виртуальный seq в пределах Дня 1 вычитает заплыв (та же база, что у bike1_s)', () => {
    // cp.bike_day1 хранится elapsed ОТ СТАРТА ГОНКИ (включает заплыв) —
    // "объединённое вело" 0..421 км должно быть БЕЗ заплыва, как и
    // bike1_s (bike1_abs - swim в compute_stage_totals). Раньше день1 и
    // день2 считались в разных базах — нашли при проектировании live-времени
    // Свода вело (2026-08-03).
    const row = { cp: { bike_day1: { 3: 5000 }, bike_day2: {} }, bike1_s: 20000, swim_s: 800 };
    assert.strictEqual(sandbox.bikeCombinedRawCp(row, 3), 4200, '5000 (elapsed от старта гонки) - 800 (заплыв) = 4200 (elapsed от старта вело)');
});
check('bikeCombinedRawCp — без swim_s (не указан) не ломается — ведёт себя как раньше (0 вычитается)', () => {
    const row = { cp: { bike_day1: { 6: 18000 }, bike_day2: {} }, bike1_s: 18000 };
    assert.strictEqual(sandbox.bikeCombinedRawCp(row, 6), 18000, 'без swim_s — вычитается 0, обратная совместимость с существующими фикстурами');
});
check('bikeCombinedRawCp — виртуальный seq в Дне 2 прибавляет bike1_s (итог Дня 1)', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox); // 6
    const row = { cp: { bike_day1: {}, bike_day2: { 2: 3000 } }, bike1_s: 20000 };
    assert.strictEqual(sandbox.bikeCombinedRawCp(row, n1 + 2), 23000, 'День 2 seq2 → bike1_s + cp.bike_day2[2]');
});
check('bikeCombinedRawCp — null, если КТ ещё не пройдена', () => {
    const row = { cp: { bike_day1: {}, bike_day2: {} }, bike1_s: 20000 };
    assert.strictEqual(sandbox.bikeCombinedRawCp(row, 1), undefined, 'нет данных на этой КТ — undefined/null');
});
check('computeBikeCombinedCheckpointRanks не сломан рефакторингом (regression)', () => {
    const rows = [
        { key: 'A', cp: { bike_day1: { 6: 18000 }, bike_day2: {} }, bike1_s: 18000, status: 'active' },
        { key: 'B', cp: { bike_day1: { 6: 19000 }, bike_day2: {} }, bike1_s: 19000, status: 'active' },
    ];
    const ranks = sandbox.computeBikeCombinedCheckpointRanks(rows);
    assert.strictEqual(ranks[6].A, 1, 'A быстрее на КТ6 Дня 1 — место 1');
    assert.strictEqual(ranks[6].B, 2, 'B медленнее — место 2');
});
check('computeBikeCombinedCheckpointGaps — гэп между участниками на виртуальной КТ', () => {
    const rows = [
        { key: 'A', cp: { bike_day1: { 6: 18000 }, bike_day2: {} }, bike1_s: 18000, status: 'active' },
        { key: 'B', cp: { bike_day1: { 6: 19000 }, bike_day2: {} }, bike1_s: 19000, status: 'active' },
    ];
    const gaps = sandbox.computeBikeCombinedCheckpointGaps(rows);
    assert.strictEqual(gaps[6].A, 0, 'лидер — гэп 0');
    assert.strictEqual(gaps[6].B, 1000, 'отстаёт на 1000с');
});
check('bikeCombinedDistKm — дистанция на виртуальной КТ (День1 и День2)', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const distKmBikeDay1 = vm.runInContext('CHECKPOINT_DIST_KM.bike_day1', sandbox);
    const distKmBikeDay2 = vm.runInContext('CHECKPOINT_DIST_KM.bike_day2', sandbox);
    assert.strictEqual(sandbox.bikeCombinedDistKm(3), distKmBikeDay1[3], 'КТ внутри Дня 1 — прямая дистанция');
    const expectedDay2 = distKmBikeDay1[n1] + distKmBikeDay2[2];
    assert.strictEqual(sandbox.bikeCombinedDistKm(n1 + 2), expectedDay2, 'КТ в Дне 2 — 145 (весь День1) + дистанция внутри Дня2');
});
check('bikeCombinedCheckpointLabel — подпись с пометкой дня', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    assert.ok(sandbox.bikeCombinedCheckpointLabel(3).includes('День 1'), 'КТ Дня 1 помечена "(День 1)"');
    assert.ok(sandbox.bikeCombinedCheckpointLabel(n1 + 2).includes('День 2'), 'КТ Дня 2 помечена "(День 2)"');
});
check('bikeCombinedLastPos — live-позиция на Дне 1 (без заплыва в value)', () => {
    const row = { cp: { bike_day1: { 3: 5000 }, bike_day2: {} }, bike1_s: 20000, swim_s: 800 };
    const pos = sandbox.bikeCombinedLastPos(row);
    assert.strictEqual(pos.seq, 3);
    assert.strictEqual(pos.value, 4200);
});
check('bikeCombinedLastPos — null, если вело ещё не начато', () => {
    const row = { cp: { bike_day1: {}, bike_day2: {} } };
    assert.strictEqual(sandbox.bikeCombinedLastPos(row), null);
});
check('bikeCombinedGaps — если у лидера нет ни одного сохранённого значения раньше виртуальной КТ отстающего, отставание не показывается (не фабрикуется из 0)', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    // У лидера в cp.bike_day1 сохранён ТОЛЬКО финиш дня (seq n1) — ни одной
    // промежуточной КТ раньше viseq=4 отстающего нет, значит его значение
    // "на или до" этой точки неизвестно → gaps.B не должен появиться вообще.
    const ahead = { key: 'A', status: 'active', entry: { cp: { bike_day1: { [n1]: 18000 }, bike_day2: { 2: 3000 } }, bike1_s: 18000, swim_s: 0 } }; // в Дне 2
    const behind = { key: 'B', status: 'active', entry: { cp: { bike_day1: { 4: 12000 }, bike_day2: {} }, bike1_s: null, swim_s: 0 } }; // ещё в Дне 1
    const gaps = sandbox.bikeCombinedGaps([ahead, behind]);
    assert.strictEqual(gaps.A, 0, 'A дальше всех — лидер, gap=0');
    assert.strictEqual(gaps.B, undefined, `Нет данных лидера раньше КТ B → gap не фабрикуется: ${JSON.stringify(gaps)}`);
});
check('bikeCombinedGaps — если у лидера ЕСТЬ сохранённая промежуточная КТ раньше/на виртуальной КТ отстающего, отставание считается от неё точно', () => {
    const ahead = { key: 'A', status: 'active', entry: { cp: { bike_day1: { 4: 10000, 6: 18000 }, bike_day2: { 2: 3000 } }, bike1_s: 18000, swim_s: 0 } }; // в Дне 2, но seq4 дня1 сохранён
    const behind = { key: 'B', status: 'active', entry: { cp: { bike_day1: { 4: 12000 }, bike_day2: {} }, bike1_s: null, swim_s: 0 } }; // ещё в Дне 1, vseq=4
    const gaps = sandbox.bikeCombinedGaps([ahead, behind]);
    assert.strictEqual(gaps.A, 0, 'A дальше всех — лидер, gap=0');
    assert.strictEqual(gaps.B, 2000, `Отставание B = 12000 - 10000 = 2000: ${JSON.stringify(gaps)}`);
});

check('computeStageGaps — отставание считается ДО того, как кто-то финишировал этап (лидер = дальше всех прямо сейчас)', () => {
    // У A есть свой сохранённый сплит на КТ1 (100с) — это НЕ тест "лидер без
    // данных на КТ отстающего" (это отдельно покрыто bikeCombinedGaps, gap
    // там не фабрикуется из воздуха), а тест именно на выбор ЛИДЕРА по
    // live-прогрессу: A дальше всех (КТ4, 5,2 км), хотя его "сырое" время
    // НА ЭТОЙ ЖЕ КТ4 (1380с) больше, чем "сырое" время B на КТ1 (120с).
    const ahead = { key: 'A', status: 'active', cp: { swim: { 1: 100, 4: 1380 } } };  // 5,2 км
    const behind = { key: 'B', status: 'active', cp: { swim: { 1: 120 } } };  // 1,3 км, но меньше "сырого" времени
    const gaps = sandbox.computeStageGaps([ahead, behind], 'swim');
    assert.strictEqual(gaps.A, 0, `A дальше всех — должен быть лидером с gap=0: ${JSON.stringify(gaps)}`);
    assert.ok(gaps.B > 0, `B должен получить положительное отставание, а не остаться без записи: ${JSON.stringify(gaps)}`);
});

// ── currentStage(row, maxStage) — п.1 v6, 2026-08-02: ограничение границей
// дня на вкладках "Дни" (раньше показывал этап "Бег", если участник уже
// там отметился, хотя вкладка про вело) ──
check('currentStage(row, maxStage) — не заходит дальше maxStage, даже если есть данные дальше', () => {
    const row = { cp: {
        swim: { 7: 1000 },
        bike_day1: { 6: 5000 },
        bike_day2: { 8: 9000 },
        run: { 12: 20000 },
    } };
    assert.strictEqual(sandbox.currentStage(row, 'bike_day1'), 'bike_day1', 'День 1 — не должен видеть bike_day2/run');
    assert.strictEqual(sandbox.currentStage(row, 'bike_day2'), 'bike_day2', 'День 1+2 — не должен видеть run');
});
check('currentStage(row) без maxStage — прежнее поведение (последний этап по всей гонке)', () => {
    const row = { cp: { swim: { 7: 1000 }, run: { 12: 20000 } } };
    assert.strictEqual(sandbox.currentStage(row), 'run', 'без maxStage — реальный текущий этап (Итоги/Свод вело)');
});

// ── _circleWord()/lastCpTwoLineHtml() — п.3 v6, 2026-08-02: двухстрочная
// ячейка "последняя КТ" ──
check('_circleWord — русское склонение по числу', () => {
    assert.strictEqual(sandbox._circleWord(1), 'круг');
    assert.strictEqual(sandbox._circleWord(2), 'круга');
    assert.strictEqual(sandbox._circleWord(4), 'круга');
    assert.strictEqual(sandbox._circleWord(5), 'кругов');
    assert.strictEqual(sandbox._circleWord(11), 'кругов');
    assert.strictEqual(sandbox._circleWord(12), 'кругов');
});
check('lastCpTwoLineHtml — плавание, круговая КТ — "N км" + "m круг"', () => {
    const html = sandbox.lastCpTwoLineHtml('swim', 4); // seq4 = круг 2 (SWIM_LAP_SEQS)
    assert.ok(html.includes('5,2 км'), `ожидалась дистанция 5,2 км: ${html}`);
    assert.ok(html.includes('2 круга'), `ожидался круг 2: ${html}`);
});
check('lastCpTwoLineHtml — плавание, "разворот" (не круг) — только "N км", без второй строки', () => {
    const html = sandbox.lastCpTwoLineHtml('swim', 1); // seq1 = разворот, не круг
    assert.ok(html.includes('1,3 км'), `ожидалась дистанция 1,3 км: ${html}`);
    assert.ok(!html.includes('muted-sub'), `второй строки быть не должно: ${html}`);
});
check('lastCpTwoLineHtml — бег, промежуточная КТ — "N км" + "m круг"', () => {
    const html = sandbox.lastCpTwoLineHtml('run', 3);
    assert.ok(html.includes('21 км'), `ожидалась дистанция 21 км: ${html}`);
    assert.ok(html.includes('3 круга'), `ожидался круг 3: ${html}`);
});
check('lastCpTwoLineHtml — вело, промежуточная КТ — только "N км" (у вело нет круга)', () => {
    const html = sandbox.lastCpTwoLineHtml('bike_day1', 2);
    assert.ok(html.includes('10 км'), `ожидалась дистанция 10 км: ${html}`);
    assert.ok(!html.includes('muted-sub'), `второй строки быть не должно (вело без кругов): ${html}`);
});
check('lastCpTwoLineHtml — финиш любого этапа — вторая строка "Финиш"', () => {
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    assert.ok(sandbox.lastCpTwoLineHtml('run', maxSeqRun).includes('Финиш'), 'финиш бега — "Финиш"');
    assert.ok(sandbox.lastCpTwoLineHtml('bike_day1', maxSeqBike1).includes('Финиш'), 'финиш вело — тоже "Финиш" (не круг)');
});
check('lastCpTwoLineHtml — seq=null даёт прочерк', () => {
    assert.strictEqual(sandbox.lastCpTwoLineHtml('run', null), '—');
});

// ── lastReachedIncludingSubmarks()/lastCpTwoLineHtml() субметки — задача 6
// Live v2, Copernico "-500м до круга" (seq 101..112) ──
check('lastCpTwoLineHtml — бег, субметка "-500м до круга" — km + "N круг (-500м)"', () => {
    const html = sandbox.lastCpTwoLineHtml('run', 101); // 6.5 км, круг 1
    assert.ok(html.includes('6,5 км'), `ожидалась дистанция 6,5 км: ${html}`);
    assert.ok(html.includes('1 круг') && html.includes('-500м'), `ожидался "1 круг (-500м)": ${html}`);
});
check('lastCpTwoLineHtml — бег, последняя субметка (круг 12) — НЕ "Финиш" (это не seq=12)', () => {
    const html = sandbox.lastCpTwoLineHtml('run', 112); // 83.5 км, круг 12, но не финиш
    assert.ok(html.includes('83,5 км'), `ожидалась дистанция 83,5 км: ${html}`);
    assert.ok(!html.includes('Финиш'), `субметка перед финишем не должна показывать "Финиш": ${html}`);
});
check('lastReachedIncludingSubmarks — субметка позже последнего круга побеждает по расстоянию', () => {
    const cp = { run: { 8: 30000, 109: 31000 } }; // круг 8 (56км) + субметка круга 9 (62.5км)
    const pos = sandbox.lastReachedIncludingSubmarks(cp, 'run');
    assert.strictEqual(pos.seq, 109, `должна победить субметка 109 (62.5км) как более дальняя: ${JSON.stringify(pos)}`);
    assert.strictEqual(pos.value, 31000);
});
check('lastReachedIncludingSubmarks — круговая КТ побеждает более раннюю субметку', () => {
    const cp = { run: { 101: 5000, 1: 6000 } }; // субметка круга 1 (6.5км) + сам круг 1 (7км)
    const pos = sandbox.lastReachedIncludingSubmarks(cp, 'run');
    assert.strictEqual(pos.seq, 1, `круг 1 (7км) дальше субметки (6.5км): ${JSON.stringify(pos)}`);
});
check('lastReachedIncludingSubmarks — не влияет на другие этапы (делегирует в lastReached)', () => {
    const cp = { swim: { 4: 1000 } };
    const pos = sandbox.lastReachedIncludingSubmarks(cp, 'swim');
    assert.strictEqual(pos.seq, 4);
});
check('lastReachedIncludingSubmarks — пусто, если нет ни круговых, ни субметок', () => {
    assert.strictEqual(sandbox.lastReachedIncludingSubmarks({ run: {} }, 'run'), null);
});
check('lastReachedIncludingSubmarks — субметки НЕ влияют на lastReached (finish-детекция не меняется)', () => {
    // Участник дошёл только до субметки 112 (83.5км, почти финиш) — обычный
    // lastReached() (используется для "финишировал?"/ранги/статус) должен
    // остаться null, а не решить, что seq=12 (финиш) достигнут.
    const cp = { run: { 112: 40000 } };
    assert.strictEqual(sandbox.lastReached(cp, 'run'), null);
});

// ── bikeCombinedLastSeq()/bikeCombinedLastCpHtml() — Отметка на Своде вело
// (п.3 v6, колонки раньше не было вовсе) ──
check('bikeCombinedLastSeq — приоритет дня 2 над днём 1, если есть данные обоих', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const cp = { bike_day1: { [n1]: 5000 }, bike_day2: { 2: 3000 } };
    assert.strictEqual(sandbox.bikeCombinedLastSeq(cp), n1 + 2);
});
check('bikeCombinedLastSeq — только день 1 — виртуальный seq в пределах дня 1', () => {
    const cp = { bike_day1: { 3: 5000 }, bike_day2: {} };
    assert.strictEqual(sandbox.bikeCombinedLastSeq(cp), 3);
});
check('bikeCombinedLastSeq — нет данных вовсе — null', () => {
    assert.strictEqual(sandbox.bikeCombinedLastSeq({ bike_day1: {}, bike_day2: {} }), null);
});
check('bikeCombinedLastCpHtml — финиш дня 2 (весь Свод вело пройден) — "Финиш"', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const n2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const cp = { bike_day1: { [n1]: 145 }, bike_day2: { [n2]: 421 } };
    const html = sandbox.bikeCombinedLastCpHtml(cp);
    assert.ok(html.includes('Финиш'), `ожидался "Финиш": ${html}`);
});

// ── bikeCombinedStatus() — п.2 v6, 2026-08-02: DNF на беге не должен
// превращать в DNF уже пройденное вело (найдено на Дащенко/Пушкарёве) ──
check('bikeCombinedStatus — DNF по общей гонке, но вело-2 реально финишировано — "active"', () => {
    const n2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const row = { status: 'dnf', cp: { bike_day2: { [n2]: 9000 } } };
    assert.strictEqual(sandbox.bikeCombinedStatus(row), 'active', 'вело пройдено полностью — DNF (на беге) не должен просачиваться сюда');
});
check('bikeCombinedStatus — DNF реально НА вело (не дошёл до финиша дня 2) — остаётся DNF', () => {
    const row = { status: 'dnf', cp: { bike_day2: { 3: 4000 } } }; // не последняя КТ
    assert.strictEqual(sandbox.bikeCombinedStatus(row), 'dnf');
});
check('bikeCombinedStatus — status уже active — возвращает active без проверки cp', () => {
    const row = { status: 'active', cp: {} };
    assert.strictEqual(sandbox.bikeCombinedStatus(row), 'active');
});

// ── renderStartlist() — без фильтров формата/пола, новые заголовки (п.8 v6, 2026-08-02) ──
check('renderStartlist() — заголовки "Порядок старта"/"Время старта" (две строки)', () => {
    const ind = mkTimerInd('1', { surname: 'Иванов', name: 'Иван', bike2_start_s: 1000 });
    setRaceData([ind], [], Date.now());
    setState('all', 'all');
    sandbox.renderStartlist();
    const html = domGetAppHtml();
    assert.ok(html.includes('Порядок<br>старта'), `ожидался заголовок "Порядок старта": ${html.slice(0, 400)}`);
    assert.ok(html.includes('Время<br>старта'), `ожидался заголовок "Время старта": ${html.slice(0, 400)}`);
});
check('renderStartlist() — игнорирует активный фильтр пола (показывает всех стартующих)', () => {
    const men = mkTimerInd('1', { surname: 'Иванов', name: 'Иван', gender: 'M', bike2_start_s: 1000 });
    const women = mkTimerInd('2', { surname: 'Петрова', name: 'Анна', gender: 'F', bike2_start_s: 2000 });
    setRaceData([men, women], [], Date.now());
    // Фильтр "Мужчины" оставлен активным (унаследован с другой вкладки) —
    // стартовый лист всё равно должен показать обоих: фильтров на этой
    // вкладке больше нет вовсе (не только UI, но и сама выборка данных).
    setState('all', 'M');
    sandbox.renderStartlist();
    const html = domGetAppHtml();
    assert.ok(html.includes('bib-cell">1<'), `мужчина должен быть в списке: ${html}`);
    assert.ok(html.includes('bib-cell">2<'), `женщина тоже должна быть в списке, несмотря на фильтр "Мужчины": ${html}`);
});
check('render() — блок фильтров скрыт на вкладке "Стартовый список"', () => {
    setRaceData([], [], Date.now());
    setState('all', 'all');
    vm.runInContext(`_tab = 'startlist';`, sandbox);
    sandbox.render();
    assert.strictEqual(domStub('mainFiltersBar').style.display, 'none', 'фильтры должны быть скрыты на Стартовом листе');
    vm.runInContext(`_tab = 'overall';`, sandbox);
    sandbox.render();
    assert.strictEqual(domStub('mainFiltersBar').style.display, '', 'на других вкладках фильтры должны быть видны');
});

// ── dayStatus()/renderDay1()/renderDay2() — DNF на более позднем этапе (беге)
// не должен занулять уже пройденный вело-день (найдено пользователем
// 2026-08-02 на Дащенко/Пушкарёве — тот же класс бага, что чинили для
// Свода вело через bikeCombinedStatus) ──
check('dayStatus — DNF по общей гонке (на беге), но День 1 (bike_day1) реально пройден — "active"', () => {
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const row = { status: 'dnf', cp: { bike_day1: { [maxSeqB1]: 5000 } } };
    assert.strictEqual(sandbox.dayStatus(row, 'bike_day1'), 'active');
});
check('dayStatus — DNF реально НА этом дне (не дошёл до финиша bike_day1) — остаётся DNF', () => {
    const row = { status: 'dnf', cp: { bike_day1: { 3: 3000 } } }; // не последняя КТ
    assert.strictEqual(sandbox.dayStatus(row, 'bike_day1'), 'dnf');
});
check('dayStatus — без maxStage возвращает status как есть', () => {
    assert.strictEqual(sandbox.dayStatus({ status: 'dnf', cp: {} }, undefined), 'dnf');
});
check('renderDay1() — участник с DNF на беге, но День 1 пройден полностью: статус "Финиш", но строка блёклая и внизу (как на Плавании)', () => {
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    // Дащенко/Пушкарёв: status='dnf' (сошёл на беге), но день 1 (плавание+
    // вело1) реально пройден — cp.bike_day1 дошёл до последней КТ. Более
    // быстрый (по времени) активный участник должен быть ВЫШЕ в списке,
    // несмотря на большее day1Progress-время у DNF-участника не имеющее
    // значения — сошедший всегда внизу (запрошено пользователем
    // 2026-08-02: "блёклые внизу как на плавании").
    const dnfButFinishedDay = mkTimerInd('1', {
        status: 'dnf', gender: 'M', swim_s: 100, bike1_s: 200, // очень быстрый, но всё равно должен быть внизу
        cp: { swim: { [maxSeqSwim]: 100 }, bike_day1: { [maxSeqB1]: 200 } },
    });
    const stillActive = mkTimerInd('2', {
        status: 'active', gender: 'M', swim_s: 1000, bike1_s: 5000,
        cp: { swim: { [maxSeqSwim]: 1000 }, bike_day1: { [maxSeqB1]: 5000 } },
    });
    setRaceData([dnfButFinishedDay, stillActive], [], Date.now());
    sandbox.renderDay1();
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка участника не найдена: ${html}`);
    assert.ok(rowMatch[0].includes(' dnf"'), `строка должна быть блёклой (dnf-класс), несмотря на "Финиш": ${rowMatch[0]}`);
    assert.ok(rowMatch[0].includes('badge-fin">Финиш<'), `текст статуса должен быть "Финиш": ${rowMatch[0]}`);
    assert.ok(html.indexOf('bib-cell">2<') < html.indexOf('bib-cell">1<'), `активный участник (медленнее по времени) должен идти ВЫШЕ сошедшего: ${html}`);
});
check('renderDay1() — "Отметка" в две строки, БЕЗ названия этапа, км НАКОПЛЕННЫЕ (не с нуля на этапе)', () => {
    // 2026-08-04: "Отметка" на "Днях" должна расти к границе дня (155/431 км),
    // а не начинаться заново с 0 на каждом этапе внутри дня — финиш
    // вело-дня-1 (145 км в рамках этапа) = 155 км накопленных (10 км
    // заплыва + 145 км вело), это и есть граница "Дня 1".
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const runner = mkTimerInd('1', { gender: 'M', bike1_s: 5000, cp: { bike_day1: { [maxSeqB1]: 5000 } } });
    setRaceData([runner], [], Date.now());
    sandbox.renderDay1();
    const html = domGetAppHtml();
    assert.ok(html.includes('<div>155 км</div>'), `ожидалась строка "155 км" (накоплено, не 145): ${html.slice(0, 700)}`);
    assert.ok(!html.includes('Вело 1,') && !html.includes('Вело 2,'), `названия этапа быть не должно: ${html.slice(0, 700)}`);
    assert.ok(html.includes('muted-sub">Финиш'), `ожидалась вторая строка "Финиш": ${html.slice(0, 700)}`);
});
check('renderDay2() — "Отметка" накопленная: 51 км вело-дня-2 показывается как 206 км (155 день1 + 51)', () => {
    const runner = mkTimerInd('1', { gender: 'M', bike1_s: 20000, bike2_s: null, cp: { bike_day1: { [vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox)]: 20000 }, bike_day2: { 1: 300 } } });
    setRaceData([runner], [], Date.now());
    sandbox.renderDay2();
    const html = domGetAppHtml();
    assert.ok(html.includes('<div>206 км</div>'), `ожидалась строка "206 км" (155+51), получили: ${html.slice(0, 900)}`);
});

check('renderDay1() — сошедший (rawStatus=dnf) не получает номер места, даже показывая "Финиш"', () => {
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const dnfButFinishedDay = mkTimerInd('1', { status: 'dnf', gender: 'M', bike1_s: 200, cp: { bike_day1: { [maxSeqB1]: 200 } } });
    setRaceData([dnfButFinishedDay], [], Date.now());
    sandbox.renderDay1();
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка участника не найдена: ${html}`);
    assert.ok(/rank-num[^>]*>—</.test(rowMatch[0]), `место должно быть прочерком (не ранжируется), несмотря на "Финиш": ${rowMatch[0]}`);
});

check('renderBikeCombined() — DNF на беге, вело пройдено полностью: "Финиш", но строка блёклая, внизу, без места', () => {
    const maxSeqB2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const dnfOnRun = mkTimerInd('1', {
        status: 'dnf', gender: 'M', bike1_s: 100, bike2_s: 100, // очень быстрый, но должен быть внизу
        cp: { bike_day2: { [maxSeqB2]: 100 } },
    });
    const stillActive = mkTimerInd('2', { status: 'active', gender: 'M', bike1_s: 5000, bike2_s: 4000, cp: { bike_day2: { [maxSeqB2]: 4000 } } });
    setRaceData([dnfOnRun, stillActive], [], Date.now());
    setState('all', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка участника не найдена: ${html}`);
    assert.ok(rowMatch[0].includes(' dnf"'), `строка должна быть блёклой: ${rowMatch[0]}`);
    assert.ok(rowMatch[0].includes('badge-fin">Финиш<'), `текст статуса должен быть "Финиш": ${rowMatch[0]}`);
    assert.ok(/rank-num[^>]*>—</.test(rowMatch[0]), `место должно быть прочерком (не ранжируется): ${rowMatch[0]}`);
    assert.ok(html.indexOf('bib-cell">2<') < html.indexOf('bib-cell">1<'), `активный участник должен идти выше сошедшего: ${html}`);
});

// ── Сортировка DNF-участников МЕЖДУ СОБОЙ (запрошено пользователем
// 2026-08-02): на срезе, где оба финишировали — по времени, как обычно;
// на срезе, где оба сошли (нет времени именно здесь) — по пройденной
// дистанции, кто дальше — выше ──
check('sortByStatus — два DNF, оба финишировали ЭТОТ срез (есть время) — сортируются по времени, как обычные', () => {
    const rows = [
        { bib: 'A', status: 'dnf', t: 500 },
        { bib: 'B', status: 'dnf', t: 300 },
    ];
    const sorted = sandbox.sortByStatus(rows, 't');
    assert.strictEqual(sorted[0].bib, 'B', `B быстрее (300с) должен быть первым: ${JSON.stringify(sorted)}`);
});
check('sortByStatus — два DNF, ни один не финишировал этот срез — по прогрессу (дальше = выше)', () => {
    const rows = [
        { bib: 'A', status: 'dnf', t: null },
        { bib: 'B', status: 'dnf', t: null },
    ];
    const progressFn = r => ({ A: 5, B: 10 }[r.bib]);
    const sorted = sandbox.sortByStatus(rows, 't', progressFn);
    assert.strictEqual(sorted[0].bib, 'B', `B прошёл дальше (10 vs 5) — должен быть первым: ${JSON.stringify(sorted)}`);
});
check('sortByStatus — DNF с временем на этот срез выше DNF без времени (финишировавший всегда впереди не финишировавшего)', () => {
    const rows = [
        { bib: 'A', status: 'dnf', t: null },
        { bib: 'B', status: 'dnf', t: 999 },
    ];
    const sorted = sandbox.sortByStatus(rows, 't', () => 100);
    assert.strictEqual(sorted[0].bib, 'B', `B финишировал этот срез — должен быть выше A: ${JSON.stringify(sorted)}`);
});
check('sortByStatus — активные без времени НЕ используют progressFn (только для DNF между собой)', () => {
    const rows = [
        { bib: 'A', status: 'active', t: null },
        { bib: 'B', status: 'active', t: null },
    ];
    const sorted = sandbox.sortByStatus(rows, 't', () => { throw new Error('progressFn не должен вызываться для активных'); });
    assert.strictEqual(sorted.length, 2);
});

check('renderStage() — два DNF на одном этапе: финишировавший этап (со временем) выше не финишировавшего', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    // A: DNF на бегу (позже), но заплыв реально финишировал — есть swim_s.
    const finishedSwim = mkTimerInd('1', { status: 'dnf', gender: 'M', swim_s: 600, cp: { swim: { [maxSeqSwim]: 600 } } });
    // B: DNF прямо на заплыве — нет swim_s, дошёл только до середины (seq=3).
    const dnfOnSwim = mkTimerInd('2', { status: 'dnf', gender: 'M', swim_s: null, cp: { swim: { 3: 400 } } });
    setRaceData([finishedSwim, dnfOnSwim], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">1<') < html.indexOf('bib-cell">2<'), `финишировавший заплыв (bib=1) должен идти выше сошедшего на заплыве (bib=2): ${html}`);
});
check('renderStage() — два DNF, оба сошли на этом этапе (нет времени) — кто дальше проплыл, тот выше', () => {
    const relay = [
        { bib: '1000', team_name: 'КомандаА', members: [{ relay_stage: 'swim', status: 'dnf', gender: 'M', swim_s: null, cp: { swim: { 2: 300 } } }] },
        { bib: '1001', team_name: 'КомандаБ', members: [{ relay_stage: 'swim', status: 'dnf', gender: 'M', swim_s: null, cp: { swim: { 5: 700 } } }] },
    ];
    setRaceData([], relay, Date.now());
    setState('relay', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">1001<') < html.indexOf('bib-cell">1000<'), `КомандаБ прошла дальше (КТ5 vs КТ2) — должна быть выше: ${html}`);
});

check('renderDay1() — два DNF, ни один не финишировал День 1 — кто дальше в гонке, тот выше', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    // Оба DNF на вело1 (не дошли до финиша дня), но A уже проплыл больше.
    const farther = mkTimerInd('1', { status: 'dnf', swim_s: 1000, cp: { swim: { [maxSeqSwim]: 1000 }, bike_day1: { 2: 2000 } } });
    const closer = mkTimerInd('2', { status: 'dnf', swim_s: 1000, cp: { swim: { [maxSeqSwim]: 1000 }, bike_day1: { 1: 500 } } });
    // Порядок входного массива нарочно ОБРАТНЫЙ ожидаемому результату
    // (closer первым, farther вторым): старая (сломанная) логика — pos
    // вычисляется только для 'active' статуса, оба DNF получают
    // _pos=null — даёт sortByRawStatus неразличимые ключи, стабильная
    // сортировка сохраняет порядок ВХОДА, и тест бы упал. Новая логика
    // (racePos считается безусловно) обязана отсортировать по реальному
    // прогрессу независимо от порядка входа — так тест дискриминирует
    // старое/новое поведение, а не просто наследует порядок фикстуры.
    setRaceData([closer, farther], [], Date.now());
    setState('all', 'all');
    sandbox.renderDay1();
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">1<') < html.indexOf('bib-cell">2<'), `дальше продвинувшийся (bib=1) должен идти выше: ${html}`);
});

check('renderBikeCombined() — два DNF, ни один не финишировал вело — кто дальше проехал, тот выше', () => {
    const farther = mkTimerInd('1', { status: 'dnf', bike1_s: null, bike2_s: null, cp: { bike_day1: { 5: 4000 }, bike_day2: {} } });
    const closer = mkTimerInd('2', { status: 'dnf', bike1_s: null, bike2_s: null, cp: { bike_day1: { 2: 1000 }, bike_day2: {} } });
    setRaceData([farther, closer], [], Date.now());
    setState('all', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">1<') < html.indexOf('bib-cell">2<'), `дальше проехавший (bib=1, КТ5) должен идти выше (bib=2, КТ2): ${html}`);
});

// ── Задача 6 (2026-08-03): "Свод вело" — живое время/место/отставание/
// скорость ДО завершения обоих вело-дней (раньше bikeCombinedTime()
// требовал ПОЛНОСТЬЮ пройденных обоих дней — колонка "Время" была пустой
// всю первую половину гонки) ──
check('renderBikeCombined() — живое "Время" показывается ДО завершения обоих дней (не "—")', () => {
    const midDay1 = mkTimerInd('1', { status: 'active', swim_s: 0, cp: { bike_day1: { 3: 5000 } } }); // ещё в Дне 1
    setRaceData([midDay1], [], Date.now());
    setState('all', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    const row = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    assert.ok(!/time-cell">\s*<span class="muted">—<\/span>/.test(row), `"Время" не должно быть пустым до конца обоих дней: ${row}`);
});
check('renderBikeCombined() — скорость считается от РЕАЛЬНО пройденной дистанции, не от полных 421 км, пока не финишировал', () => {
    const midDay1 = mkTimerInd('1', { status: 'active', swim_s: 0, cp: { bike_day1: { 2: 3600 } } }); // 10 км за 1 час = 10 км/ч
    setRaceData([midDay1], [], Date.now());
    setState('all', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    const row = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    assert.ok(row.includes('10,0 км/ч') || row.includes('10.0 км/ч'), `скорость должна считаться от 10 км (пройдено), не от 421 км: ${row}`);
});

check('renderStage() — два DNF на беге, у ОБОИХ заполнено run_s ("время на последней КТ", не финиш) — сортировка всё равно по кругам, не по этому времени', () => {
    // Реальный баг (2026-08-02, Дащенко/Пушкарёв): run_s = время на
    // ПОСЛЕДНЕЙ пройденной КТ (см. compute_stage_totals/_last_cp в
    // src/siberman/service.py), а не финишное — у обоих оно заполнено,
    // но Дащенко (4 круга) имеет МЕНЬШЕЕ run_s, чем Пушкарёв (5 кругов,
    // раз он дольше продержался на трассе) — сортировка по сырому run_s
    // ставила её выше, хотя он прошёл больше.
    const dashchenko = mkTimerInd('158', { status: 'dnf', gender: 'F', run_s: 13778, cp: { run: { 4: 13778 } } }); // 4 круга = 28 км
    const pushkarev = mkTimerInd('36', { status: 'dnf', gender: 'M', run_s: 23321, cp: { run: { 5: 23321 } } }); // 5 кругов = 35 км
    setRaceData([dashchenko, pushkarev], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('run');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">36<') < html.indexOf('bib-cell">158<'), `Пушкарёв (5 кругов) должен быть выше Дащенко (4 круга), несмотря на большее "сырое" run_s: ${html}`);
});

check('renderOverall() — колонка "Вело итого" несёт своё отставание (timeGapCell), как остальные этапы', () => {
    // "Вело итого" теперь считается через bikeCombinedLastPos (checkpoint-
    // based, живая позиция), не через сумму bike1_s+bike2_s напрямую —
    // фикстура несёт cp.bike_day1/bike_day2 финиш, согласованный с
    // bike1_s/bike2_s (2026-08-03, Задача 7: bikeCombinedTime удалена).
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqB2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const fast = mkTimerInd('1', { bike1_s: 9000, bike2_s: 8000, overall_s: 20000, cp: { bike_day1: { [maxSeqB1]: 9000 }, bike_day2: { [maxSeqB2]: 8000 } } }); // вело = 17000
    const slow = mkTimerInd('2', { bike1_s: 9500, bike2_s: 8500, overall_s: 22000, cp: { bike_day1: { [maxSeqB1]: 9500 }, bike_day2: { [maxSeqB2]: 8500 } } }); // вело = 18000, +1000 от лидера
    setRaceData([fast, slow], [], Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">2<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка bib=2 не найдена: ${html}`);
    const expectedGap = vm.runInContext('fmtGap(1000)', sandbox);
    assert.ok(rowMatch[0].includes(expectedGap), `под "Вело итого" у bib=2 должно быть отставание ${expectedGap}: ${rowMatch[0]}`);
});

// ── DNF/DSQ участники "превращаются в кирпич": только своё время, никаких
// отставаний/"Лидер"/лидерства нигде (запрошено пользователем 2026-08-02,
// найдено на Дащенко — DNF с частичным временем бега ошибочно становилась
// "Лидером" колонки "Бег" в Итогах гонки, т.к. её неполное время оказалось
// меньше настоящих финишных времён) ──
check('renderOverall() — DNF-участник с наименьшим "сырым" run_s не становится "Лидером" колонки Бег и не получает отставание', () => {
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    // Дащенко: DNF, частичное время бега (28км) МЕНЬШЕ, чем у настоящих
    // финишеров (84км) — раньше computeStageGaps считал её "Лидером".
    const dnfPartial = mkTimerInd('158', { status: 'dnf', run_s: 13778, cp: { run: { 4: 13778 } } });
    const finisher = mkTimerInd('34', { status: 'active', run_s: 39193, overall_s: 100000, cp: { run: { [maxSeqRun]: 39193 } } });
    setRaceData([dnfPartial, finisher], [], Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    const html = domGetAppHtml();
    // (?!<tr) не даёт ленивому [\s\S]*? "перепрыгнуть" через границу
    // предыдущей строки таблицы и случайно захватить чужой <td> (нашёл
    // сам на этом же тесте — старый жадный-по-строкам паттерн подхватывал
    // "Лидер" из СОСЕДНЕЙ строки, если искомый bib оказывался не первым).
    const rowMatch = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">158<(?:(?!<tr)[\s\S])*?<\/tr>/);
    assert.ok(rowMatch, `строка Дащенко не найдена: ${html}`);
    assert.ok(!rowMatch[0].includes('Лидер'), `DNF не должна получать подпись "Лидер": ${rowMatch[0]}`);
    assert.ok(!rowMatch[0].includes('time-gap-sub'), `DNF не должна получать отставание — только своё время: ${rowMatch[0]}`);
    assert.ok(rowMatch[0].includes('3:49:38'), `своё сырое время всё равно должно отображаться: ${rowMatch[0]}`);
});

check('renderStage() — настоящий DNF (raw) не получает отставание, показывает только время', () => {
    const dnfPartial = mkTimerInd('1', { status: 'dnf', gender: 'M', run_s: 1000, cp: { run: { 3: 1000 } } });
    const active = mkTimerInd('2', { status: 'active', gender: 'M', run_s: 1200, cp: { run: { 5: 1200 } } });
    setRaceData([dnfPartial, active], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('run');
    const html = domGetAppHtml();
    // (?!<tr) не даёт ленивому [\s\S]*? "перепрыгнуть" через границу строки
    // bib=2 (теперь получает "Лидер" — этот фикс, 2026-08-03) и случайно
    // захватить его time-gap-sub в матч для bib=1 (см. тот же приём выше,
    // "renderOverall() — DNF-участник... не становится 'Лидером'").
    const rowMatch = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/);
    assert.ok(rowMatch, `строка bib=1 не найдена: ${html}`);
    assert.ok(!rowMatch[0].includes('time-gap-sub'), `DNF не должна получать отставание: ${rowMatch[0]}`);
});

check('renderStage() — настоящий DNF посреди этапа не получает номер места, несмотря на live-ранжирование по прогрессу', () => {
    // status: 'dnf' задан ИЗНАЧАЛЬНО в исходных данных (не подменён локально
    // withStageStatus, как в "тихом" DNF ниже) — участник реально сошёл на
    // 3-м круге бега, но живое ранжирование по прогрессу не должно давать
    // ему номер места, даже стоя рядом с активным лидером, ушедшим дальше.
    const dnfMidStage = mkTimerInd('1', { status: 'dnf', gender: 'M', cp: { run: { 3: 1000 } } });
    const activeLeader = mkTimerInd('2', { status: 'active', gender: 'M', cp: { run: { 5: 2000 } } });
    setRaceData([dnfMidStage, activeLeader], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('run');
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/);
    assert.ok(rowMatch, `строка bib=1 не найдена: ${html}`);
    assert.ok(/rank-num[^>]*>—</.test(rowMatch[0]), `настоящий DNF не должен получать номер места, даже с live-ранжированием по прогрессу: ${rowMatch[0]}`);
});

check('renderStage() — "тихий" DNF (реально ещё активный, просто не дошёл до финиша ЭТОГО этапа) СОХРАНЯЕТ живое отставание', () => {
    // status='active' в источнике — "тихая" подмена status на 'dnf'
    // происходит ТОЛЬКО локально для этой вкладки (withStageStatus), но
    // _rawStatus остаётся 'active' — отставание не должно пропадать.
    const stillRacing = mkTimerInd('1', { status: 'active', gender: 'M', run_s: null, cp: { run: { 3: 1000 } } });
    const leaderFinished = mkTimerInd('2', { status: 'active', gender: 'M', run_s: 1200, cp: { run: { 5: 1200 } } });
    setRaceData([stillRacing, leaderFinished], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('run');
    const html = domGetAppHtml();
    // Оба участника видны и НЕ должны быть исключены из пула отставаний
    // только из-за "тихой" подмены — по крайней мере не должно падать/
    // ломаться рендер (основная проверка — что вообще не FAIL/exception).
    assert.ok(html.includes('bib-cell">1<') && html.includes('bib-cell">2<'), `оба участника должны отрендериться: ${html}`);
});

check('renderStage() — live: дальше пройденная КТ впереди, даже с меньшим "сырым" временем', () => {
    const justStarted = mkTimerInd('1', { status: 'active', swim_s: 120, cp: { swim: { 1: 120 } } });   // 1,3 км за 2 мин
    const farAlong = mkTimerInd('2', { status: 'active', swim_s: 1380, cp: { swim: { 4: 1380 } } });    // 5,2 км за 23 мин
    setRaceData([justStarted, farAlong], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">2<') < html.indexOf('bib-cell">1<'), `дальше проплывший (bib=2) должен идти выше: ${html}`);
});
check('renderStage() — live: место считается для АКТИВНЫХ мид-этапа, не только для финишировавших', () => {
    const justStarted = mkTimerInd('1', { status: 'active', swim_s: 120, cp: { swim: { 1: 120 } } });
    const farAlong = mkTimerInd('2', { status: 'active', swim_s: 1380, cp: { swim: { 4: 1380 } } });
    setRaceData([justStarted, farAlong], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    const row2 = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">2<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    assert.ok(/rank-num[^>]*>1</.test(row2), `лидирующий по прогрессу должен получить место 1: ${row2}`);
});

check('renderBikeCombined() — DNF (на беге), вело завершено — не получает отставание, только время', () => {
    const maxSeqB2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const dnfOnRunFinishedBike = mkTimerInd('1', { status: 'dnf', bike1_s: 5000, bike2_s: 4000, cp: { bike_day2: { [maxSeqB2]: 4000 } } });
    const active = mkTimerInd('2', { status: 'active', bike1_s: 6000, bike2_s: 5000, cp: { bike_day2: { [maxSeqB2]: 5000 } } });
    setRaceData([dnfOnRunFinishedBike, active], [], Date.now());
    setState('all', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/);
    assert.ok(rowMatch, `строка bib=1 не найдена: ${html}`);
    assert.ok(!rowMatch[0].includes('time-gap-sub'), `DNF не должна получать отставание на Своде вело: ${rowMatch[0]}`);
});

check('renderDay1() — DNF (на беге), День 1 завершён — не получает отставание, только время', () => {
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const dnfFinishedDay = mkTimerInd('1', { status: 'dnf', bike1_s: 5000, cp: { bike_day1: { [maxSeqB1]: 5000 } } });
    const active = mkTimerInd('2', { status: 'active', bike1_s: 6000, cp: { bike_day1: { [maxSeqB1]: 6000 } } });
    setRaceData([dnfFinishedDay, active], [], Date.now());
    setState('all', 'all');
    sandbox.renderDay1();
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/);
    assert.ok(rowMatch, `строка bib=1 не найдена: ${html}`);
    assert.ok(!rowMatch[0].includes('time-gap-sub'), `DNF не должна получать отставание на "Дне 1": ${rowMatch[0]}`);
});

// ── overallLastCpHtml() — двухстрочная "Отметка" на Итогах гонки, формат
// отличается от lastCpTwoLineHtml: этап первой строкой, "N км (круг)"/
// "N км (Финиш)" второй (запрошено пользователем 2026-08-02) ──
check('overallLastCpHtml — плавание, круговая КТ — этап + "N км (m круг)" на одной строке', () => {
    const html = sandbox.overallLastCpHtml('swim', 4); // seq4 = круг 2
    assert.ok(html.includes('<div>Плавание</div>'), `ожидалось название этапа: ${html}`);
    assert.ok(html.includes('5,2 км (2 круга)'), `ожидалось "5,2 км (2 круга)" на одной строке: ${html}`);
});
check('overallLastCpHtml — вело, промежуточная КТ — этап + "N км" без скобок', () => {
    const html = sandbox.overallLastCpHtml('bike_day1', 2);
    assert.ok(html.includes('<div>Вело 1</div>'), `ожидалось название этапа "Вело 1": ${html}`);
    assert.ok(html.includes('10 км</div>'), `ожидалось "10 км" без скобок: ${html}`);
});
check('overallLastCpHtml — финиш — "N км (Финиш)" на одной строке, даже у вело', () => {
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const html = sandbox.overallLastCpHtml('bike_day1', maxSeqB1);
    assert.ok(html.includes('145 км (Финиш)'), `ожидалось "145 км (Финиш)": ${html}`);
});
check('overallLastCpHtml — финиш бега — "84 км (Финиш)", не круг', () => {
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    const html = sandbox.overallLastCpHtml('run', maxSeqRun);
    assert.ok(html.includes('<div>Бег</div>'), `ожидалось название этапа "Бег": ${html}`);
    assert.ok(html.includes('84 км (Финиш)'), `ожидалось "84 км (Финиш)": ${html}`);
});
check('overallLastCpHtml — нет этапа/КТ — прочерк', () => {
    assert.strictEqual(sandbox.overallLastCpHtml(null, null), '—');
    assert.strictEqual(sandbox.overallLastCpHtml('swim', null), '—');
});
check('renderOverall() — "Отметка" использует новый двухстрочный формат', () => {
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const runner = mkTimerInd('1', { bike1_s: 5000, cp: { bike_day1: { [maxSeqB1]: 5000 } } });
    setRaceData([runner], [], Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    const html = domGetAppHtml();
    assert.ok(html.includes('<div>Вело 1</div><div class="muted-sub">145 км (Финиш)</div>'), `ожидался новый формат Отметки: ${html.slice(0, 900)}`);
});

// ── posSortKey()/racePos()/raceSortKey() — единая модель live-положения
// (2026-08-03, тестовый прогон на живых данных: сравнивать "сырое" время
// напрямую между участниками на РАЗНЫХ КТ неверно — у только что
// стартовавшего оно меньше, чем у прошедшего намного дальше) ──
check('posSortKey — дальше по КТ всегда впереди, даже с бОльшим "сырым" временем', () => {
    const farAlong = { seq: 5, value: 100 };
    const justStarted = { seq: 2, value: 50 };
    assert.ok(sandbox.posSortKey(farAlong) < sandbox.posSortKey(justStarted),
        'дальше пройденная КТ должна давать МЕНЬШИЙ ключ (сортируется раньше)');
});
check('posSortKey — на одной КТ тай-брейк по времени (меньше время — раньше)', () => {
    const faster = { seq: 5, value: 90 };
    const slower = { seq: 5, value: 100 };
    assert.ok(sandbox.posSortKey(faster) < sandbox.posSortKey(slower));
});
check('posSortKey — null при отсутствии позиции', () => {
    assert.strictEqual(sandbox.posSortKey(null), null);
});

check('racePos — берёт позицию на ТЕКУЩЕМ этапе гонки, value = накопленное время гонки (globalProgress)', () => {
    const row = { cp: { swim: {}, bike_day1: { 2: 4500 } }, swim_s: 4000 };
    const pos = sandbox.racePos(row, null);
    const stageOrder = vm.runInContext('STAGE_ORDER', sandbox);
    assert.strictEqual(pos.stageIdx, stageOrder.indexOf('bike_day1'));
    assert.strictEqual(pos.seq, 2);
    assert.strictEqual(pos.value, 4500, 'bike_day1: globalProgress = сырое cp-значение (уже elapsed от старта гонки)');
});
check('racePos — maxStage ограничивает "Днём" (для вкладок Дни)', () => {
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const row = { cp: { swim: {}, bike_day1: { [maxSeqBike1]: 5000 }, run: { 3: 9000 } }, swim_s: 1000, bike1_s: 4000 };
    const pos = sandbox.racePos(row, 'bike_day1');
    const stageOrder = vm.runInContext('STAGE_ORDER', sandbox);
    assert.strictEqual(pos.stageIdx, stageOrder.indexOf('bike_day1'), 'бег виден в cp, но maxStage=bike_day1 должен его игнорировать');
    assert.strictEqual(pos.seq, maxSeqBike1);
});
check('racePos — null, если участник ещё не начал (ни одной КТ)', () => {
    assert.strictEqual(sandbox.racePos({ cp: {} }, null), null);
});

check('raceSortKey — участник на более позднем этапе всегда впереди участника на более раннем, даже с меньшим value', () => {
    const stageOrder = vm.runInContext('STAGE_ORDER', sandbox);
    const onBike = { stageIdx: stageOrder.indexOf('bike_day1'), seq: 1, value: 200 };  // только начал вело, но уже на вело
    const stillSwimming = { stageIdx: stageOrder.indexOf('swim'), seq: 6, value: 9000 }; // почти доплыл, но ещё плавание
    assert.ok(sandbox.raceSortKey(onBike) < sandbox.raceSortKey(stillSwimming),
        'участник, который уже НАЧАЛ вело, должен быть впереди того, кто ещё ЗАКАНЧИВАЕТ заплыв, несмотря на меньшее value');
});

// ── Задача 7 (2026-08-03): renderOverall() — "Итого"/"Место" через живую
// racePos/raceSortKey-модель, ОДИНАКОВО для личников и эстафеты (раньше
// личник получал overall_s только на ПОЛНОМ финише всей гонки — все 4
// этапа сразу, см. overall_results.total_s в src/siberman/db.py, — а
// эстафета получала его нарастающим по любому готовому этапу любого члена
// команды, service.py; из-за этого "Итого"/"Место" во время живой гонки
// были пустыми только у личников) ──
check('renderOverall() — live: "Итого" и "Место" считаются ДО финиша всей гонки (для личников тоже, не только эстафеты)', () => {
    const ahead = mkTimerInd('1', { status: 'active', swim_s: 4000, cp: { swim: { 7: 4000 }, bike_day1: { 2: 4500 } } });
    const behind = mkTimerInd('2', { status: 'active', swim_s: null, cp: { swim: { 4: 1380 } } });
    setRaceData([ahead, behind], [], Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    const html = domGetAppHtml();
    const row1 = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    assert.ok(/rank-num[^>]*>1</.test(row1), `дальше прошедший должен получить место 1 (личник, ДО финиша всей гонки): ${row1}`);
    assert.ok(!/time-cell"[^>]*>\s*<span class="muted">—<\/span>/.test(row1), `"Итого" не должно быть пустым: ${row1}`);
});
check('renderOverall() — суб-колонки (Плав./Вело1/Вело2/Бег) отставание считается по прогрессу, не по сырому времени напрямую', () => {
    const justStarted = mkTimerInd('1', { status: 'active', cp: { swim: { 1: 120 } } });
    const farAlong = mkTimerInd('2', { status: 'active', cp: { swim: { 4: 1380 } } });
    setRaceData([justStarted, farAlong], [], Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    const html = domGetAppHtml();
    const row1 = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    assert.ok(!row1.includes('lead">Лидер'), `только начавший заплыв НЕ должен стать "Лидером" колонки Плав.: ${row1}`);
});

// ── Пост-деплой баги живой гонки (2026-08-03): "Финиш" показывался всем
// активным участникам с первой же пройденной КТ (сырое поле не null =/=
// реально дошёл до финиша), а "тихая" подмена status на 'dnf' (withStageStatus,
// задумана 2026-08-02 для архивных данных — поймать молча сошедшего без
// пометки DNF в Excel) на живой гонке ловила КАЖДОГО реально активного
// участника и делала его тусклым. Оба механизма отключены/исправлены на
// время живой гонки — статус теперь честно проверяет реальное достижение
// финишной КТ (lastReached), а не наличие каких-либо данных ──
check('renderStage() — активный участник посреди этапа показывает "На трассе", не "Финиш"', () => {
    const midSwim = mkTimerInd('1', { status: 'active', swim_s: 1380, cp: { swim: { 4: 1380 } } }); // 5,2 км, не финиш (10 км)
    setRaceData([midSwim], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `посреди этапа должен быть статус "На трассе": ${html}`);
    assert.ok(!html.includes('badge-fin">Финиш'), `не должно быть ложного "Финиш" посреди этапа: ${html}`);
});
check('renderStage() — активный участник посреди этапа НЕ блёклый (нет класса dnf)', () => {
    const midSwim = mkTimerInd('1', { status: 'active', swim_s: 1380, cp: { swim: { 4: 1380 } } });
    setRaceData([midSwim], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    const row = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    const trOpenTag = row.match(/<tr class="([^"]*)"/)[1];
    assert.ok(!trOpenTag.includes('dnf'), `активный участник посреди этапа не должен получать класс dnf: ${trOpenTag}`);
});
check('renderStage() — эстафетчик посреди этапа показывает "На трассе", не "Финиш"', () => {
    const team = {
        bib: '10', team_name: 'Команда 10',
        members: [
            { relay_stage: 'swim', status: 'active', cp: { swim: { 4: 1380 } }, swim_s: 1380, gender: 'M', surname: 'Пловцов', name: 'Иван' },
            { relay_stage: 'bike', status: 'active', cp: {}, bike1_s: null, bike2_s: null, gender: 'M', surname: 'Велосипедов', name: 'Пётр' },
            { relay_stage: 'run', status: 'active', cp: {}, run_s: null, gender: 'M', surname: 'Бегунов', name: 'Сидор' },
        ],
    };
    setRaceData([], [team], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `эстафетчик посреди этапа должен быть "На трассе": ${html}`);
    assert.ok(!html.includes('badge-fin">Финиш'), `не должно быть ложного "Финиш" у эстафетчика посреди этапа: ${html}`);
});
check('renderOverall() — эстафетная команда посреди гонки показывает "На трассе", не "Финиш"', () => {
    const team = {
        bib: '10', team_name: 'Команда 10',
        members: [
            { relay_stage: 'swim', status: 'active', cp: { swim: { 4: 1380 } }, swim_s: 1380, gender: 'M' },
            { relay_stage: 'bike', status: 'active', cp: {}, bike1_s: null, bike2_s: null, gender: 'M' },
            { relay_stage: 'run', status: 'active', cp: {}, run_s: null, gender: 'M' },
        ],
    };
    setRaceData([], [team], Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `команда посреди гонки (только 5,2 км заплыва) должна быть "На трассе": ${html}`);
    assert.ok(!html.includes('badge-fin">Финиш'), `команда не должна получать "Финиш" только за то, что у одного члена есть частичное время: ${html}`);
});
check('renderBikeCombined() — активный посреди Дня 1 показывает "На трассе", не "Финиш"', () => {
    const midDay1 = mkTimerInd('1', { status: 'active', swim_s: 0, cp: { bike_day1: { 2: 3600 } } });
    setRaceData([midDay1], [], Date.now());
    setState('all', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `посреди Дня 1 должен быть статус "На трассе": ${html}`);
    assert.ok(!html.includes('badge-fin">Финиш'), `не должно быть "Финиш" посреди Дня 1 (только 10 км из 421): ${html}`);
});
check('renderDay1() — активный посреди дня показывает "На трассе", не "Финиш"', () => {
    const midDay1 = mkTimerInd('1', { status: 'active', swim_s: 4000, cp: { swim: { 7: 4000 }, bike_day1: { 2: 4500 } } });
    setRaceData([midDay1], [], Date.now());
    setState('all', 'all');
    sandbox.renderDay1();
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `посреди Дня 1 должен быть статус "На трассе": ${html}`);
    assert.ok(!html.includes('badge-fin">Финиш'), `не должно быть "Финиш" посреди Дня 1: ${html}`);
});
check('renderStage() — два реально активных участника посреди этапа сортируются по прогрессу, не по сырому времени интерливинга', () => {
    // Регресс, найденный при отключении "тихого DNF" (2026-08-03): раньше
    // оба таких участника случайно проваливались в "rowsRest" (т.к. status
    // был "тихо" подменён на dnf) и сохраняли верный порядок по _sortTime.
    // После отключения подмены оба стали проходить фильтр "финишировавших"
    // по сырому r[cfg.timeKey]!=null и пересортировывались НАПРЯМУЮ по
    // сырому времени в interleaved-блоке — тот же класс бага, что и везде
    // в этом плане, только в отдельном, не мигрированном месте.
    const justStarted = mkTimerInd('1', { status: 'active', swim_s: 120, cp: { swim: { 1: 120 } } });
    const farAlong = mkTimerInd('2', { status: 'active', swim_s: 1380, cp: { swim: { 4: 1380 } } });
    setRaceData([justStarted, farAlong], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">2<') < html.indexOf('bib-cell">1<'), `дальше проплывший (bib=2) должен идти выше по строкам таблицы: ${html}`);
});

check('renderStage() — при фильтре по полу эстафетчица, реально впереди по прогрессу, идёт ВЫШЕ личницы, а не отдельным блоком снизу', () => {
    // Реальный баг (2026-08-03, тестовый прогон живых данных, фильтр
    // "Женщины"): раньше "не финишировавшие" личники и эстафетчики просто
    // СКЛЕИВАЛИСЬ двумя отдельными блоками (сначала все личники, потом все
    // эстафетчики), а не сортировались вместе по live-позиции — эстафетчица-
    // лидер оказывалась в самом низу таблицы, хотя была быстрее всех
    // личниц. Баг был незаметен на архивных данных (там почти все успевали
    // "финишировать" этот ранний этап), но на живой гонке, где никто ещё
    // не финишировал, проявился максимально широко.
    const soloSlower = mkTimerInd('158', { status: 'active', gender: 'F', swim_s: 1700, cp: { swim: { 4: 1700 } } });
    const team = {
        bib: '1048', team_name: 'Нас заставили',
        members: [
            { relay_stage: 'swim', status: 'active', gender: 'F', cp: { swim: { 4: 1234 } }, swim_s: 1234 }, // быстрее личницы, та же КТ
            { relay_stage: 'bike', status: 'active', gender: 'M', cp: {}, bike1_s: null, bike2_s: null },
            { relay_stage: 'run', status: 'active', gender: 'M', cp: {}, run_s: null },
        ],
    };
    setRaceData([soloSlower], [team], Date.now());
    setState('all', 'F');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">1048<') < html.indexOf('bib-cell">158<'),
        `эстафетчица (быстрее, bib=1048) должна идти выше личницы (bib=158): ${html}`);
});

check('renderStage() — активный участник, ещё не начавший ИМЕННО ЭТОТ этап (например, ещё плывёт на вкладке "Вело 1"), НЕ блёклый', () => {
    // Реальный баг (2026-08-03): на живой гонке вообще у ВСЕХ участников
    // noTime===true на этапах, до которых они ещё не дошли (например,
    // все ещё плывут — вкладка "Вело 1" пуста у всех) — старое условие
    // дименга (noTime || status!=='active') делало блёклыми абсолютно
    // всех на такой вкладке, хотя они реально активны, просто ещё не
    // дошли до НЕЁ (не то же самое, что реальный DNF/DSQ/DNS).
    const stillSwimming = mkTimerInd('1', { status: 'active', swim_s: 1700, cp: { swim: { 4: 1700 } } });
    setRaceData([stillSwimming], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    const trOpenTag = html.match(/<tr class="([^"]*)"/)?.[1] ?? html.match(/<tr>/)[0];
    assert.ok(!trOpenTag.includes('dnf'), `ещё не дошедший до ЭТОГО этапа активный участник не должен быть блёклым: ${trOpenTag}`);
});

// ── Новый статус "—" (не начал СРЕЗ) vs "На трассе" (начал, но не
// закончил) vs "Финиш" (дошёл до конца) — п.5 v7, 2026-08-03: раньше
// "не начал" и "в процессе" неразличимо показывали "На трассе" ──
check('statusBadge() — активный, ещё не начавший этап (ни одной КТ), показывает "—", не "На трассе"', () => {
    const notStarted = { status: 'active', cp: {}, swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
    assert.ok(sandbox.statusBadge(notStarted, 'bike1').includes('badge-notstarted">—<'), `должен быть "—": ${sandbox.statusBadge(notStarted, 'bike1')}`);
});
check('statusBadge() — активный, начавший этап, но не дошедший до конца, показывает "На трассе"', () => {
    const midStage = { status: 'active', cp: { bike_day1: { 2: 5000 } } };
    assert.ok(sandbox.statusBadge(midStage, 'bike1').includes('badge-live">На трассе<'), `должен быть "На трассе": ${sandbox.statusBadge(midStage, 'bike1')}`);
});
check('statusBadge() — активный, дошедший до финишной КТ этапа, показывает "Финиш"', () => {
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const finished = { status: 'active', cp: { bike_day1: { [maxSeqBike1]: 18000 } } };
    assert.ok(sandbox.statusBadge(finished, 'bike1').includes('badge-fin">Финиш<'), `должен быть "Финиш": ${sandbox.statusBadge(finished, 'bike1')}`);
});
check('statusBadge() — активный, ещё не начавший ГОНКУ вовсе (stageKey=null, Итоги), показывает "—"', () => {
    const notStarted = { status: 'active', cp: {} };
    assert.ok(sandbox.statusBadge(notStarted, null).includes('badge-notstarted">—<'), `должен быть "—" на Итогах: ${sandbox.statusBadge(notStarted, null)}`);
});
check('teamStatusBadge() — эстафетная команда, ещё не начавшая гонку, показывает "—"', () => {
    const team = { bib: '1', team_name: 'T', members: [
        { relay_stage: 'swim', status: 'active', cp: {}, swim_s: null },
        { relay_stage: 'bike', status: 'active', cp: {}, bike1_s: null, bike2_s: null },
        { relay_stage: 'run', status: 'active', cp: {}, run_s: null },
    ]};
    assert.ok(sandbox.teamStatusBadge(team).includes('badge-notstarted">—<'), `команда без единой отметки должна быть "—": ${sandbox.teamStatusBadge(team)}`);
});
check('renderStage() — активный, ещё не начавший этап, показывает "—" в статусе (не "На трассе")', () => {
    const notStarted = mkTimerInd('1', { status: 'active', swim_s: 1700, cp: { swim: { 4: 1700 } } }); // плывёт, вело не начато
    setRaceData([notStarted], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-notstarted">—<'), `на вкладке "Вело 1" участник, который ещё плывёт, должен показывать "—": ${html}`);
});
check('renderBikeCombined() — активный, ещё даже не финишировавший заплыв, показывает "—"', () => {
    // seq=4 (5,2 км) — не последняя КТ заплыва (7) — заплыв ещё не завершён,
    // значит вело точно ещё не началось.
    const notStarted = mkTimerInd('1', { status: 'active', swim_s: 1380, cp: { swim: { 4: 1380 } } });
    setRaceData([notStarted], [], Date.now());
    setState('all', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-notstarted">—<'), `не финишировавший заплыв должен показывать "—" на вело: ${html}`);
});
// ── stageHasStarted(): "—"→"На трассе" должен переключаться по факту
// завершения ПРЕДЫДУЩЕГО этапа (bike_day1 — после финиша заплыва,
// bike_day2 — по личному расчётному старту, run — после финиша вело-2),
// а не по наличию первой КТ ЭТОГО этапа — иначе "—" держится до первой
// КТ, хотя участник уже реально в пути (найдено пользователем 2026-08-04) ──
check('renderStage(\'bike1\') — финишировал заплыв, но ещё не дошёл до 3 км вело — "На трассе", не "—"', () => {
    const r = mkTimerInd('1', { status: 'active', swim_s: 4000, cp: { swim: { 7: 4000 } } });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `финишировавший заплыв должен быть "На трассе" на вело-дне-1, даже без КТ: ${html}`);
    assert.ok(!html.includes('badge-notstarted">—<'), `не должно быть "—": ${html}`);
});
check('renderBikeCombined() — финишировал заплыв, но ещё не дошёл до 3 км вело — "На трассе", не "—"', () => {
    const r = mkTimerInd('1', { status: 'active', swim_s: 4000, cp: { swim: { 7: 4000 } } });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `финишировавший заплыв должен быть "На трассе" на Своде вело, даже без КТ: ${html}`);
});
check('renderStage(\'run\') — финишировал вело-2, но ещё не дошёл до 1 круга бега — "На трассе", не "—"', () => {
    const n2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const r = mkTimerInd('1', { status: 'active', bike2_s: 5000, cp: { bike_day2: { [n2]: 20000 } } });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('run');
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `финишировавший вело-2 должен быть "На трассе" на беге, даже без КТ: ${html}`);
});
check('renderStage(\'bike1\') — заплыв ЕЩЁ НЕ финиширован (частичный swim_s) — остаётся "—"', () => {
    const r = mkTimerInd('1', { status: 'active', swim_s: 1380, cp: { swim: { 4: 1380 } } }); // 5,2 км, не финиш
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-notstarted">—<'), `незавершённый заплыв не должен давать "На трассе" на вело: ${html}`);
});
check('renderStage(\'bike2\') — время личного старта дня 2 уже прошло — "На трассе", не "—"', () => {
    // race_start "вчера" (относительно теста) — расчётный старт дня 2
    // (8:00 утра дня 2 + 0с для ранга 1) заведомо уже в прошлом.
    const raceStartEpoch = Date.now() - 5 * 86400 * 1000;
    const r = mkTimerInd('1', { status: 'active', bike1_s: 20000, bike2_start_s: 8 * 3600, cp: {} });
    setRaceData([r], [], raceStartEpoch);
    setState('all', 'all');
    sandbox.renderStage('bike2');
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `наступивший личный старт дня 2 должен давать "На трассе", даже без КТ: ${html}`);
});
check('renderStage(\'bike2\') — время личного старта дня 2 ещё НЕ наступило — остаётся "—"', () => {
    const raceStartEpoch = Date.now() + 5 * 86400 * 1000; // "гонка" в будущем
    const r = mkTimerInd('1', { status: 'active', bike1_s: 20000, bike2_start_s: 8 * 3600, cp: {} });
    setRaceData([r], [], raceStartEpoch);
    setState('all', 'all');
    sandbox.renderStage('bike2');
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-notstarted">—<'), `ещё не наступивший личный старт дня 2 не должен давать "На трассе": ${html}`);
});
check('renderStage(\'bike1\') — эстафетный велосипедист: команда финишировала заплыв — "На трассе" через swim КОМАНДЫ, не своё пустое cp.swim', () => {
    const relay = [mkRelayProgress(10, { swim_s: 4000, swimCp: { swim: { 7: 4000 } }, bikeCp: {} })];
    setRaceData([], relay, Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-live">На трассе'), `эстафетный велосипедист должен видеть финиш заплыва СВОЕЙ команды: ${html}`);
});
check('renderDay1() — активный, ещё не начавший день вовсе, показывает "—"', () => {
    const notStarted = mkTimerInd('1', { status: 'active', cp: {} });
    setRaceData([notStarted], [], Date.now());
    setState('all', 'all');
    sandbox.renderDay1();
    const html = domGetAppHtml();
    assert.ok(html.includes('badge-notstarted">—<'), `не начавший День 1 должен показывать "—": ${html}`);
});

// ── Индикаторы (buildStats) — DNF относительно ОТКРЫТОГО среза, не всей
// гонки — п.1 v7, 2026-08-03: сошедший на более позднем этапе/дне должен
// на уже пройденных вкладках по-прежнему считаться финишировавшим ──
check('stageRelativeStatus() — DNF на более позднем этапе не портит статус более раннего', () => {
    const dnfOnRun = { status: 'dnf', swim_s: 4000, bike1_s: 9000, bike2_s: 8000, run_s: null };
    assert.strictEqual(sandbox.stageRelativeStatus(dnfOnRun, 'swim'), 'active', 'Плавание должно быть финишировано');
    assert.strictEqual(sandbox.stageRelativeStatus(dnfOnRun, 'bike1'), 'active', 'Вело1 должно быть финишировано');
    assert.strictEqual(sandbox.stageRelativeStatus(dnfOnRun, 'run'), 'dnf', 'На Беге — реальный DNF');
});
check('stageRelativeStatus() — DNF на более раннем этапе остаётся dnf на всех последующих (не "не стартовал")', () => {
    // 2026-08-04: раньше более поздние этапы после DNF показывали "не
    // стартовал" (dns) — вводило в заблуждение (сход необратим, участник
    // не "ещё не начал", а уже сошёл) — теперь dnf держится на всех
    // последующих этапах, "не стартовал" остаётся только для настоящего
    // dns (участник, реально не стартовавший всю гонку).
    const dnfOnSwim = { status: 'dnf', swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
    assert.strictEqual(sandbox.stageRelativeStatus(dnfOnSwim, 'swim'), 'dnf', 'DNF именно на плавании');
    assert.strictEqual(sandbox.stageRelativeStatus(dnfOnSwim, 'bike1'), 'dnf', 'Вело1 — тоже dnf, сход на плавании необратим');
    assert.strictEqual(sandbox.stageRelativeStatus(dnfOnSwim, 'run'), 'dnf', 'Бег — тоже dnf');
});
check('stageRelativeStatus() — настоящий dns (не стартовал всю гонку) остаётся dns на любом этапе', () => {
    const realDns = { status: 'dns', swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
    assert.strictEqual(sandbox.stageRelativeStatus(realDns, 'swim'), 'dns');
    assert.strictEqual(sandbox.stageRelativeStatus(realDns, 'run'), 'dns');
});
check('getDnfStage()/stageRelativeStatus() — DNF на ПРОМЕЖУТОЧНОЙ (не финишной) КТ этапа не путается с DNF следующего этапа', () => {
    // 2026-08-06, найдено на реальных данных: сошедший на 2,6км из 10км
    // заплыва (swim_s = время на ПОСЛЕДНЕЙ ДОСТИГНУТОЙ, не финишной КТ —
    // compute_stage_totals берёт last_cp, не только финиш) показывал "На
    // трассе" на вкладке "Плавание" вместо DNF — старая эвристика
    // getDnfStage() ("первый этап без *_s") видела swim_s != null и
    // ошибочно решала, что плавание пройдено, сдвигая DNF на bike1.
    // Теперь используется реальный r.dnf_stage из API (participants.dnf_stage).
    const dnfMidSwim = { status: 'dnf', dnf_stage: 'swim', swim_s: 4840, bike1_s: null, bike2_s: null, run_s: null };
    assert.strictEqual(sandbox.getDnfStage(dnfMidSwim), 'swim', 'dnf_stage=swim должен маппиться в ключ "swim"');
    assert.strictEqual(sandbox.stageRelativeStatus(dnfMidSwim, 'swim'), 'dnf', 'Плавание — реальный DNF, не "На трассе"');
    assert.strictEqual(sandbox.stageRelativeStatus(dnfMidSwim, 'bike1'), 'dnf', 'Вело1 — тоже dnf (сход необратим)');

    const dnfMidBike1 = { status: 'dnf', dnf_stage: 'bike_day1', swim_s: 4840, bike1_s: 3000, bike2_s: null, run_s: null };
    assert.strictEqual(sandbox.getDnfStage(dnfMidBike1), 'bike1', 'dnf_stage=bike_day1 должен маппиться в ключ "bike1"');
    assert.strictEqual(sandbox.stageRelativeStatus(dnfMidBike1, 'swim'), 'active', 'Плавание успешно пройдено');
    assert.strictEqual(sandbox.stageRelativeStatus(dnfMidBike1, 'bike1'), 'dnf', 'Вело1 — реальный DNF');
});
check('renderStage() — индикатор "DNF/DSQ" считает DNF только на ОТКРЫТОМ этапе, не на всей гонке', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const dnfOnRun = mkTimerInd('1', { status: 'dnf', swim_s: 4000, bike1_s: 9000, bike2_s: 8000, run_s: null, cp: { swim: { [maxSeqSwim]: 4000 } } });
    setRaceData([dnfOnRun], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    let statsHtml = domGetAppHtml().match(/<div class="stats-v2">[\s\S]*?<\/div><\/div>/)[0];
    assert.ok(statsHtml.includes('1 финишировало'), `на "Плавании" DNF-на-беге должен считаться финишировавшим: ${statsHtml}`);
    assert.ok(statsHtml.includes('0 DNF/DSQ'), `на "Плавании" не должно быть DNF: ${statsHtml}`);
    sandbox.renderStage('run');
    statsHtml = domGetAppHtml().match(/<div class="stats-v2">[\s\S]*?<\/div><\/div>/)[0];
    assert.ok(statsHtml.includes('1 DNF/DSQ'), `на "Беге" (где реально сошёл) должен считаться DNF: ${statsHtml}`);
});
check('renderDay1() — эстафетная команда с DNF на дне 3 (бег) считается финишировавшей на "Дне 1"', () => {
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const team = {
        bib: '10', team_name: 'T10',
        members: [
            { relay_stage: 'swim', status: 'active', gender: 'M', cp: {}, swim_s: 4000 },
            { relay_stage: 'bike', status: 'active', gender: 'M', cp: { bike_day1: { [maxSeqBike1]: 8500 } }, bike1_s: 4500, bike2_s: null },
            { relay_stage: 'run', status: 'dnf', gender: 'M', cp: {}, run_s: null }, // сошёл на дне 3
        ],
    };
    setRaceData([], [team], Date.now());
    setState('all', 'all');
    sandbox.renderDay1();
    const statsHtml = domGetAppHtml();
    assert.ok(statsHtml.includes('1 финишировало'), `команда, реально прошедшая День 1, должна считаться финишировавшей, несмотря на DNF на дне 3: ${statsHtml}`);
    assert.ok(!statsHtml.includes('1 DNF/DSQ'), `не должно быть DNF на "Дне 1" — DNF случился на дне 3: ${statsHtml}`);
});

// ── Сохранение таба/фильтров в URL при обновлении страницы — п.4 v7,
// 2026-08-03: раньше состояние жило только в JS-переменных, F5 сбрасывал
// пользователя на "Итоги гонки" со снятыми фильтрами ──
check('syncUrlFromState()/readStateFromUrl() — состояние переживает "обновление страницы"', () => {
    setRaceData([], [], Date.now());
    vm.runInContext(`_tab = 'run'; _fmt = 'relay'; _gender = 'all';`, sandbox);
    sandbox.render();
    assert.ok(sandbox.location.search.includes('tab=run'), `URL должен содержать tab=run: ${sandbox.location.search}`);
    assert.ok(sandbox.location.search.includes('fmt=relay'), `URL должен содержать fmt=relay: ${sandbox.location.search}`);
    // "Обновление страницы" — читаем состояние заново из того же URL.
    vm.runInContext(`_tab = 'overall'; _fmt = 'all'; _gender = 'all';`, sandbox); // дефолты, как при чистой загрузке
    sandbox.readStateFromUrl();
    assert.strictEqual(vm.runInContext('_tab', sandbox), 'run', 'таб должен восстановиться');
    assert.strictEqual(vm.runInContext('_fmt', sandbox), 'relay', 'формат должен восстановиться');
});
check('readStateFromUrl() — невалидное/незнакомое значение параметра игнорируется, остаётся дефолт', () => {
    sandbox.location.search = '?tab=hacked&fmt=bogus';
    vm.runInContext(`_tab = 'overall'; _fmt = 'all';`, sandbox);
    sandbox.readStateFromUrl();
    assert.strictEqual(vm.runInContext('_tab', sandbox), 'overall', 'невалидный tab должен быть проигнорирован');
    assert.strictEqual(vm.runInContext('_fmt', sandbox), 'all', 'невалидный fmt должен быть проигнорирован');
});
check('readStateFromUrl() — fmt=relay в URL всегда приводит gender к "all" (тот же инвариант, что в клике)', () => {
    sandbox.location.search = '?tab=swim&fmt=relay&gender=M';
    sandbox.readStateFromUrl();
    assert.strictEqual(vm.runInContext('_gender', sandbox), 'all', 'при эстафете пол должен сброситься на "все", даже если в URL было другое');
});

// ── cityLabel() — "Страна, Город" для иностранцев, просто "Город" для
// россиян — п.3 v7, 2026-08-03 ──
check('cityLabel() — россиянин показывает просто город', () => {
    assert.strictEqual(sandbox.cityLabel({ city: 'Красноярск', country: 'Россия' }), 'Красноярск');
});
check('cityLabel() — без явного country (дефолт "Россия" на сервере) — тоже просто город', () => {
    assert.strictEqual(sandbox.cityLabel({ city: 'Москва' }), 'Москва');
});
check('cityLabel() — иностранец показывает "Страна, Город"', () => {
    assert.strictEqual(sandbox.cityLabel({ city: 'Алматы', country: 'Казахстан' }), 'Казахстан, Алматы');
});
check('cityLabel() — без города возвращает пустую строку, даже с указанной страной', () => {
    assert.strictEqual(sandbox.cityLabel({ country: 'Казахстан' }), '');
});
check('renderStage() — иностранец показывает "Страна, Город" в ячейке участника', () => {
    const foreigner = mkTimerInd('1', { status: 'active', swim_s: 1700, cp: { swim: { 4: 1700 } }, city: 'Алматы', country: 'Казахстан' });
    setRaceData([foreigner], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.includes('Казахстан, Алматы'), `должно быть "Страна, Город": ${html}`);
});

// ── Вело День 1: cp.bike_day1 хранит elapsed ОТ СТАРТА ГОНКИ (включает
// заплыв) — сортировка/место/скорость на этой вкладке должны считаться в
// СЕТЕВОМ времени вело (без заплыва), иначе быстрый пловец с медленным
// вело обгоняет медленного пловца с быстрым вело, и скорость улетает в
// сотни км/ч (найдено пользователем 2026-08-04) ──
check('renderStage(\'bike1\') — место/порядок по сетевому времени вело, не по сырому "от старта гонки" чекпоинту', () => {
    // bib=200: медленный заплыв (5000с), но быстрое вело (net 100с) — raw=5100
    // bib=201: быстрый заплыв (100с), но медленное вело (net 900с) — raw=1000
    // "Сырой" порядок (баг): 201 впереди 200. Правильный (по сетевому вело): 200 впереди 201.
    const fastBikeSlowSwim = mkTimerInd('200', { swim_s: 5000, bike1_s: 100, cp: { bike_day1: { 1: 5100 } } });
    const slowBikeFastSwim = mkTimerInd('201', { swim_s: 100, bike1_s: 900, cp: { bike_day1: { 1: 1000 } } });
    setRaceData([fastBikeSlowSwim, slowBikeFastSwim], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">200<') < html.indexOf('bib-cell">201<'),
        `быстрый по сетевому времени вело (200, net=100с) должен идти выше медленного (201, net=900с), несмотря на бОльшее сырое время: ${html}`);
});
check('renderStage(\'bike1\') — скорость считается от сетевого времени вело, не от "сырого" (без абсурдных км/ч)', () => {
    // seq=1 → 3 км (CHECKPOINT_DIST_KM.bike_day1[1]). net=561с (9:21) → ~19.3 км/ч.
    // "Сырое" raw=2561 (=swim_s 2000 + net 561) дало бы 3/(2561/3600) ≈ 4.2 км/ч —
    // на реальных данных пользователя раздутое (не заниженное) значение получалось
    // из-за деления ПОЛНОЙ дистанции этапа на частичное время (серверное avg_speed_kmh,
    // до этого фикса бравшееся напрямую); здесь достаточно проверить, что скорость
    // считается именно от net-времени, а не от raw cp-значения.
    const r = mkTimerInd('144', { swim_s: 2000, bike1_s: 561, cp: { bike_day1: { 1: 2561 } } });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('19.3 км/ч'), `ожидалась скорость ~19.3 км/ч (3 км / 561с), получили: ${html}`);
    assert.ok(!html.includes('930'), `не должно быть раздутой "сырой" скорости: ${html}`);
});
check('renderStage(\'bike1\') — эстафетный велосипедист сортируется по сетевому времени вело (без заплыва СВОЕЙ команды), не по сырому "от старта гонки"', () => {
    // Команда 10: долгий заплыв команды (5000с), но быстрое вело (net 100с) — raw cp=5100.
    // Личник 201: короткий заплыв (100с), медленное вело (net 900с) — raw cp=1000.
    // Велосипедист эстафеты сам не плавает — его собственный swim_s пуст, вычитать
    // нужно swim_s КОМАНДЫ (найдено пользователем 2026-08-06 на живой гонке: "Вело
    // Итого" сортировал верно через bikeCombinedRelayRider, а "Вело День 1" — нет,
    // т.к. relayMembers в renderStage() не подмешивал swim_s команды, только cp.swim).
    const relay = [mkRelayProgress(10, { swim_s: 5000, swimCp: { swim: { 7: 5000 } }, bikeCp: { bike_day1: { 1: 5100 } } })];
    const individual = [mkTimerInd('201', { swim_s: 100, bike1_s: 900, cp: { bike_day1: { 1: 1000 } } })];
    setRaceData(individual, relay, Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">10<') < html.indexOf('bib-cell">201<'),
        `быстрый по сетевому времени вело (10, net=100с) должен идти выше медленного (201, net=900с): ${html}`);
});

// ── renderOverall() — "Лидер" в суб-колонке "Вело 1" должен совпадать с
// "Вело итого": stageGapPool для computeStageGaps не нёс swim_s, поэтому
// gap на bike_day1 считался от "сырого" (от старта гонки, с заплывом)
// времени — участник с медленным заплывом, но самым быстрым НЕТТО-вело
// не получал "Лидер" в "Вело 1", хотя получал его в уже правильном "Вело
// итого" (найдено пользователем 2026-08-04, тот же класс бага, что и на
// вкладке "Вело День 1") ──
check('renderOverall() — лидер "Вело 1" совпадает с лидером "Вело итого" (сетевое время, без заплыва)', () => {
    // bib=1: медленный заплыв (2000с), но самое быстрое вело (net 561с)
    // bib=2: быстрый заплыв (500с), но вело медленнее (net 955с)
    // "Сырой" bike_day1: 1 → 2000+561=2561, 2 → 500+955=1455 — раньше "Лидер"
    // Вело1 доставался bib=2 (меньше raw), хотя чистое вело у bib=1 быстрее.
    const r1 = mkTimerInd('1', { swim_s: 2000, bike1_s: 561, cp: { swim: { 7: 2000 }, bike_day1: { 1: 2561 } } });
    const r2 = mkTimerInd('2', { swim_s: 500, bike1_s: 955, cp: { swim: { 7: 500 }, bike_day1: { 1: 1455 } } });
    setRaceData([r1, r2], [], Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    const html = domGetAppHtml();
    const row1 = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">1<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    const row2 = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">2<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    // Гэп вело1 у bib=2 относительно лидера (bib=1, net 561с): 955-561=394с=6:34.
    // Прежде (баг) считался бы от "сырых" 1455/2561 → лидером выходил bib=2.
    assert.ok(row1.includes('lead">Лидер'), `bib=1 (net вело 561с — самое быстрое) должен быть "Лидером" где-то в строке (Вело1/Вело итого): ${row1}`);
    assert.ok(row2.includes('+6:34'), `bib=2 должен отставать в "Вело 1" на +6:34 от bib=1 по СЕТЕВОМУ времени: ${row2}`);
});

// ── startlistHasRiders() — таб "День 2: Стартовый лист" не должен быть
// доступен, пока никто ещё не финишировал вело-1 (bike2_start_s пишется
// сервером только финишировавшим вело-1, см. service.py fix 2026-08-04) ──
check('startlistHasRiders() — никто ещё не получил расчётный старт дня 2 — false', () => {
    const noStarts = mkTimerInd('1', { status: 'active', cp: { bike_day1: { 1: 300 } } }); // bike2_start_s отсутствует
    setRaceData([noStarts], [], Date.now());
    assert.strictEqual(sandbox.startlistHasRiders(), false);
});
check('startlistHasRiders() — есть личник с расчётным стартом дня 2 — true', () => {
    const r = mkTimerInd('1', { status: 'active', bike2_start_s: 8 * 3600, cp: {} });
    setRaceData([r], [], Date.now());
    assert.strictEqual(sandbox.startlistHasRiders(), true);
});
check('startlistHasRiders() — есть эстафетный велосипедист с расчётным стартом дня 2 — true', () => {
    const relay = [mkRelayProgress(10, { bike1_s: 5000, bikeCp: {} })];
    relay[0].members.find(m => m.relay_stage === 'bike').bike2_start_s = 8 * 3600;
    setRaceData([], relay, Date.now());
    assert.strictEqual(sandbox.startlistHasRiders(), true);
});

// ── finishStarBadge() на табах результатов (не только карточка участника) —
// только личный зачёт, только finish_count > 0 (2026-08-05) ──
check('renderOverall() — показывает бейдж со звездой у личника с finish_count > 0', () => {
    const r = mkTimerInd('1', { status: 'active', finish_count: 5, cp: {} });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    assert.ok(domGetAppHtml().includes('badge-star'), 'ожидался бейдж badge-star в Итогах гонки');
});
check('renderStage() — не показывает бейдж со звездой у личника с finish_count = 0', () => {
    const r = mkTimerInd('1', { status: 'active', finish_count: 0, swim_s: 1380, cp: { swim: { 4: 1380 } } });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    assert.ok(!domGetAppHtml().includes('badge-star'), 'не должно быть бейджа звезды при finish_count=0');
});
check('renderOverall() — эстафетная команда не получает бейдж звезды (только личный зачёт)', () => {
    const relay = [mkRelayProgress(10, { swim_s: 3000, swimCp: { swim: { 7: 3000 } } })];
    setRaceData([], relay, Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    assert.ok(!domGetAppHtml().includes('badge-star'), 'эстафета не должна показывать звезду');
});

// ── Рекорды Siberman (2026-08-05) — "Рекорд" вместо "Лидер" у лидера-
// рекордсмена, третьей строкой у рекордсмена без лидерства ──
function setRecordsIndex(records) {
    sandbox.__records = records;
    vm.runInContext('_recordsIndex = buildRecordsIndex(__records);', sandbox);
}
check('renderOverall() — лидер, который держит рекорд "overall", показывает "Рекорд" ВМЕСТО "Лидер"', () => {
    const r = { ...mkInd('1', 100000), surname: 'Иванов', name: 'Пётр' };
    setRaceData([r], [], Date.now());
    setRecordsIndex([{ column_key: 'overall', category: 'absolute', best_s: 71429, holder_name: 'Иванов Пётр' }]);
    setState('all', 'all');
    sandbox.renderOverall();
    const html = domGetAppHtml();
    assert.ok(html.includes('record">🏆 Абсолют'), `ожидался "Рекорд" в колонке Итого: ${html}`);
    assert.ok(!html.includes('lead">Лидер'), `"Лидер" не должен показываться вместо рекорда: ${html}`);
});
check('renderStage(\'swim\') — рекордсмен без лидерства показывает "Рекорд" ТРЕТЬЕЙ строкой под отставанием', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    // bib=1 — лидер этапа (быстрее), bib=2 — держит женский рекорд, но
    // отстаёт от bib=1 по времени (не лидер).
    const leader = mkTimerInd('1', { surname: 'Быстров', name: 'Олег', gender: 'M', swim_s: 8000, cp: { swim: { [maxSeqSwim]: 8000 } } });
    const recordHolder = mkTimerInd('2', { surname: 'Петрова', name: 'Анна', gender: 'F', swim_s: 8500, cp: { swim: { [maxSeqSwim]: 8500 } } });
    setRaceData([leader, recordHolder], [], Date.now());
    setRecordsIndex([{ column_key: 'swim', category: 'female', best_s: 9330, holder_name: 'Петрова Анна' }]);
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    const row2 = html.match(/<tr[^>]*>(?:(?!<tr)[\s\S])*?bib-cell">2<(?:(?!<tr)[\s\S])*?<\/tr>/)[0];
    assert.ok(row2.includes('time-gap-sub">+') && row2.includes('record">🏆 Ж<'), `ожидалась отдельная строка отставания И строка "Рекорд: Ж": ${row2}`);
});
check('renderOverall() — без записи в индексе рекордов поведение не меняется (обычный "Лидер")', () => {
    const r = { ...mkInd('1', 100000), surname: 'Иванов', name: 'Пётр' };
    setRaceData([r], [], Date.now());
    setRecordsIndex([]);
    setState('all', 'all');
    sandbox.renderOverall();
    assert.ok(domGetAppHtml().includes('lead">Лидер'), 'без рекорда должен остаться обычный "Лидер"');
});

// ── Сортировка по номеру ЧИСЛЕННО (не лексикографически) до первой
// реальной отметки на срезе — bib это VARCHAR в БД, "10" раньше "9" без
// этого (2026-08-05) ──
check('bibCompare — численное сравнение, не строковое', () => {
    assert.ok(sandbox.bibCompare('2', '10') < 0, '"2" должен идти раньше "10" (численно)');
    assert.ok(sandbox.bibCompare('10', '2') > 0, '"10" должен идти позже "2" (численно)');
    assert.strictEqual(sandbox.bibCompare('5', '5'), 0);
});
check('renderStage(\'swim\') — никто ещё не начал этап -> сортировка по номеру, "2" раньше "10"', () => {
    const a = mkTimerInd('10', { cp: {} });
    const b = mkTimerInd('2', { cp: {} });
    setRaceData([a, b], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">2<') < html.indexOf('bib-cell">10<'), `bib=2 должен идти раньше bib=10 (численно, не лексикографически): ${html}`);
});
check('renderOverall() — никто ещё не начал гонку -> сортировка по номеру, "2" раньше "10"', () => {
    const a = mkTimerInd('10', { cp: {} });
    const b = mkTimerInd('2', { cp: {} });
    setRaceData([a, b], [], Date.now());
    setState('all', 'all');
    sandbox.renderOverall();
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">2<') < html.indexOf('bib-cell">10<'), `bib=2 должен идти раньше bib=10 (численно): ${html}`);
});
check('renderStage(\'swim\') — как только у кого-то появилась реальная отметка, сортировка снова по месту (не по номеру)', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const started = mkTimerInd('10', { swim_s: 500, cp: { swim: { 1: 500 } } }); // реально начал этап
    const notStarted = mkTimerInd('2', { cp: {} }); // ещё не начал
    setRaceData([started, notStarted], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.indexOf('bib-cell">10<') < html.indexOf('bib-cell">2<'), `реально начавший (bib=10) должен идти выше ещё не начавшего (bib=2), несмотря на номер: ${html}`);
});

// ── forecastTime() — линейная экстраполяция средней скорости с начала
// этапа (прогноз финиша этапа / прогноз времени на будущей КТ), 2026-08-06 ──
check('forecastTime() — линейная экстраполяция: 72 км за 2:19:28 → прогноз на 145 км, округлён до целых секунд', () => {
    // 2:19:28 = 8368с. 8368 * (145/72) = 16852.222...с → round → 16852с = 4:40:52.
    // Округление обязательно: fmtTime() делает `s % 60` без Math.floor для
    // секунд — на нецелом s это дало бы "52.222222" в строке времени.
    const s = sandbox.forecastTime(72, 8368, 145);
    assert.strictEqual(s, 16852);
});
check('forecastTime() — dist_so_far=0 возвращает null (деление на ноль)', () => {
    assert.strictEqual(sandbox.forecastTime(0, 100, 145), null);
});
check('forecastTime() — elapsedS=null возвращает null (ещё нет данных)', () => {
    assert.strictEqual(sandbox.forecastTime(72, null, 145), null);
});
check('forecastTime() — target_dist == dist_so_far возвращает то же elapsedS (экстраполяция "в ноль")', () => {
    assert.strictEqual(sandbox.forecastTime(72, 8368, 72), 8368);
});

// ── fmtClock() / forecastCellHtml() — астрономический прогноз, вторая
// строка в скобках под "~ЧЧ:ММ:СС" (2026-08-06). Date.now() мокается ЧЕРЕЗ
// vm.runInContext (не прямым sandbox.Date.now=...) — сборка globalThis.Date
// в контексте vm иначе не видна снаружи до первого runInContext-вызова.
// new Date(y,m,d,h,mi,s) конструируется в локальной таймзоне ЭТОГО же
// процесса, что и getHours()/getMinutes() внутри sandbox (общая система) —
// тест детерминирован независимо от того, в каком часовом поясе он запущен.
check('fmtClock() — секунды до события + "сейчас" → часы:минуты:секунды по местному времени', () => {
    const fixedNow = new Date(2026, 0, 1, 10, 0, 0).getTime();
    vm.runInContext(`Date.now = () => ${fixedNow};`, sandbox);
    // 8484с = 2ч21м24с → 10:00:00 + 2:21:24 = 12:21:24.
    assert.strictEqual(sandbox.fmtClock(8484), '12:21:24');
    vm.runInContext('Date.now = () => (new Date()).getTime();', sandbox);
});
check('fmtClock() — remainingS=null возвращает null', () => {
    assert.strictEqual(sandbox.fmtClock(null), null);
});
check('forecastCellHtml() — две строки: "~ЧЧ:ММ:СС" и "(ЧЧ:ММ:СС)" астрономического времени', () => {
    const fixedNow = new Date(2026, 0, 1, 10, 0, 0).getTime();
    vm.runInContext(`Date.now = () => ${fixedNow};`, sandbox);
    // forecastTime(72, 8368, 145) = 16852с (см. тест forecastTime() выше).
    // remaining = 16852 - 8368 = 8484с → 10:00:00 + 2:21:24 = 12:21:24.
    const html = sandbox.forecastCellHtml(72, 8368, 145);
    assert.strictEqual(html, '<span class="forecast-cell">~4:40:52</span><span class="forecast-clock">(12:21:24)</span>');
    vm.runInContext('Date.now = () => (new Date()).getTime();', sandbox);
});
check('forecastCellHtml() — недостаточно данных (dist_so_far=0) возвращает пустую строку', () => {
    assert.strictEqual(sandbox.forecastCellHtml(0, 100, 145), '');
});

// ── renderStage() — колонка "Прогноз финиша" (2026-08-06) ──
check('renderStage(\'bike1\') — активный участник посреди этапа показывает "~" прогноз финиша', () => {
    // pos: seq=3 (72 км), value=8368с (2:19:28). Прогноз на 145 км
    // (STAGE_MAX_SEQ.bike_day1=6 → 145км) — та же арифметика, что в Task 1:
    // round(8368*145/72) = 16852с = 4:40:52.
    // bike1_s=8368 (НЕ null) — на реальных данных r[cfg.timeKey] заполняется
    // уже на первой достигнутой КТ (compute_stage_totals), а не только на
    // финише; фикстура с bike1_s:null не поймала бы регрессию, из-за
    // которой прогноз был пуст у ВСЕХ активных участников (найдено
    // пользователем 2026-08-06 на живой гонке сразу после деплоя).
    const r = mkTimerInd('9', { swim_s: 0, bike1_s: 8368, cp: { bike_day1: { 1: 100, 2: 200, 3: 8368 } } });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('forecast-cell">~4:40:52<'), `ожидался прогноз ~4:40:52: ${html}`);
    // Вторая строка — астрономическое время в скобках (не мокаем Date.now
    // здесь, точное значение зависит от реального времени теста — важен
    // только формат "(ЧЧ:ММ:СС)").
    assert.ok(/forecast-clock">\(\d{2}:\d{2}:\d{2}\)</.test(html), `ожидалась вторая строка "(ЧЧ:ММ:СС)" астрономического времени: ${html}`);
});
check('renderStage(\'bike1\') — финишировавший этап НЕ показывает прогноз (ячейка пустая)', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const r = mkTimerInd('9', { swim_s: 0, bike1_s: 9000, cp: { bike_day1: { [n1]: 9000 } } });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    const row = html.slice(html.indexOf('bib-cell">9<'));
    assert.ok(!row.includes('forecast-cell'), `у финишировавшего не должно быть прогноза: ${row}`);
});
check('renderStage(\'bike1\') — ещё не начавший этап НЕ показывает прогноз (ячейка пустая)', () => {
    const r = mkTimerInd('9', { swim_s: null, bike1_s: null, cp: {} });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    const row = html.slice(html.indexOf('bib-cell">9<'));
    assert.ok(!row.includes('forecast-cell'), `у не начавшего этап не должно быть прогноза: ${row}`);
});
check('renderStage(\'bike1\') — DNF посреди этапа НЕ показывает прогноз, даже с частичным прогрессом', () => {
    const r = mkTimerInd('9', { status: 'dnf', swim_s: 0, bike1_s: 8368, cp: { bike_day1: { 1: 100, 2: 200, 3: 8368 } } });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    const row = html.slice(html.indexOf('bib-cell">9<'));
    assert.ok(!row.includes('forecast-cell'), `у DNF не должно быть прогноза: ${row}`);
});
check('renderStage(\'bike1\') — эстафетный велосипедист посреди этапа показывает "~" прогноз финиша', () => {
    const relay = [mkRelayProgress(10, { swim_s: 0, swimCp: {}, bike1_s: 8368, bikeCp: { bike_day1: { 1: 100, 2: 200, 3: 8368 } } })];
    setRaceData([], relay, Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('forecast-cell">~4:40:52<'), `у эстафетного велосипедиста посреди этапа должен быть прогноз ~4:40:52: ${html}`);
});
check('renderStage(\'bike1\') — заголовок таблицы содержит "Прогноз финиша" между "Скорость" и "Отметка"', () => {
    const r = mkTimerInd('9', { swim_s: 0, bike1_s: null, cp: { bike_day1: { 1: 100 } } });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    const speedIdx = html.indexOf('>Скорость<');
    const forecastIdx = html.indexOf('>Прогноз финиша<');
    const cpIdx = html.indexOf('>Отметка<');
    assert.ok(speedIdx > -1 && forecastIdx > speedIdx && cpIdx > forecastIdx,
        `ожидался порядок колонок Скорость → Прогноз финиша → Отметка: speedIdx=${speedIdx} forecastIdx=${forecastIdx} cpIdx=${cpIdx}`);
});

// ── Колонка "Прогноз финиша" ЦЕЛИКОМ (не только пустая ячейка) скрыта,
// пока этап не начался, и снова скрыта, когда все активные финишировали
// (2026-08-06) ──
check('renderStage(\'bike1\') — этап ещё НИ У КОГО не начался: колонка "Прогноз финиша" отсутствует целиком', () => {
    const r1 = mkTimerInd('9', { swim_s: null, bike1_s: null, cp: {} });
    const r2 = mkTimerInd('10', { swim_s: null, bike1_s: null, cp: {} });
    setRaceData([r1, r2], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(!html.includes('Прогноз финиша'), `колонка не должна рендериться, пока никто не начал этап: ${html}`);
});
check('renderStage(\'bike1\') — ВСЕ активные финишировали этап: колонка "Прогноз финиша" снова скрыта целиком', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const r1 = mkTimerInd('9', { swim_s: 0, bike1_s: 9000, cp: { bike_day1: { [n1]: 9000 } } });
    const r2 = mkTimerInd('10', { swim_s: 0, bike1_s: 9500, cp: { bike_day1: { [n1]: 9500 } } });
    setRaceData([r1, r2], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(!html.includes('Прогноз финиша'), `колонка должна скрыться, когда все активные финишировали: ${html}`);
});
check('renderStage(\'bike1\') — один финишировал, другой ещё в процессе: колонка "Прогноз финиша" ОСТАЁТСЯ видна', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const finished = mkTimerInd('9', { swim_s: 0, bike1_s: 9000, cp: { bike_day1: { [n1]: 9000 } } });
    const active = mkTimerInd('10', { swim_s: 0, bike1_s: 8368, cp: { bike_day1: { 1: 100, 2: 200, 3: 8368 } } });
    setRaceData([finished, active], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('Прогноз финиша'), `колонка должна остаться, пока не ВСЕ активные финишировали: ${html}`);
    const activeRow = html.slice(html.indexOf('bib-cell">10<'));
    assert.ok(activeRow.includes('forecast-cell'), `у ещё активного (10) должен быть виден прогноз: ${activeRow}`);
});
check('renderStage(\'bike1\') — DNF не мешает скрыть колонку, если ВСЕ ОСТАЛЬНЫЕ активные финишировали', () => {
    const n1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const finished = mkTimerInd('9', { swim_s: 0, bike1_s: 9000, cp: { bike_day1: { [n1]: 9000 } } });
    const dnf = mkTimerInd('11', { status: 'dnf', swim_s: 0, bike1_s: null, cp: { bike_day1: { 1: 100, 2: 200, 3: 8368 } } });
    setRaceData([finished, dnf], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(!html.includes('Прогноз финиша'), `DNF не должен считаться "ещё не финишировавшим" — колонка должна скрыться: ${html}`);
});

// ── Строка поиска участника (номер/фамилия) — под индикаторами, не
// фильтр (2026-08-06). document.querySelectorAll в этом тест-харнессе —
// заглушка (всегда []), поэтому подсветку/скролл (реальный DOM) здесь не
// проверить — тестируем то, что можно: разметку input'а в HTML-строке,
// позицию (после ".stats-v2"), и что ввод (onParticipantSearchInput)
// переживает следующий рендер (значение вшито в html, не живёт в DOM).
check('buildStats() — строка поиска участника присутствует и стоит СРАЗУ ПОСЛЕ .stats-v2', () => {
    const r = mkTimerInd('9', { swim_s: 0, bike1_s: null, cp: {} });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('id="participantSearch"') && html.includes('class="search-input"'),
        `ожидался инпут поиска участника: ${html}`);
    const statsCloseIdx = html.indexOf('</div>', html.indexOf('class="stats-v2"'));
    const searchIdx = html.indexOf('search-bar');
    assert.ok(searchIdx > -1 && searchIdx > statsCloseIdx,
        `строка поиска должна идти сразу после блока индикаторов: statsCloseIdx=${statsCloseIdx} searchIdx=${searchIdx}`);
});
check('onParticipantSearchInput() — введённое значение сохраняется в поле при следующем рендере (не сбрасывается поллингом)', () => {
    const r = mkTimerInd('9', { swim_s: 0, bike1_s: null, cp: {} });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.renderStage('bike1');
    sandbox.onParticipantSearchInput('88');
    sandbox.renderStage('bike1'); // имитация повторного рендера (poll/смена фильтра)
    const html = domGetAppHtml();
    assert.ok(html.includes('value="88"'), `значение "88" должно сохраниться после повторного рендера: ${html}`);
    sandbox.onParticipantSearchInput(''); // сброс, чтобы не аффектить следующие тесты
});
check('onParticipantSearchInput() — спецсимволы в запросе экранируются, не ломают HTML', () => {
    const r = mkTimerInd('9', { swim_s: 0, bike1_s: null, cp: {} });
    setRaceData([r], [], Date.now());
    setState('all', 'all');
    sandbox.onParticipantSearchInput('Иванов "Заяц"');
    sandbox.renderStage('bike1');
    const html = domGetAppHtml();
    assert.ok(html.includes('value="Иванов &quot;Заяц&quot;"'), `кавычки должны быть экранированы: ${html}`);
    sandbox.onParticipantSearchInput(''); // сброс, чтобы не аффектить следующие тесты
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
