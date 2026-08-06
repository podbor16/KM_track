// Тест participant.html — индикаторы места в шапке карточки (Итого/
// Отставание/Место (абсолют)/Место (по полу) или Место (формат)).
// Раньше для этой страницы не было постоянных JS-тестов (только
// разовые scratchpad-проверки) — паттерн node:vm тот же, что и в
// test_siberman_results_merge.js. Запуск: node tests/js/test_siberman_participant.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const commonJs = fs.readFileSync(path.join(ROOT, 'static/js/siberman-common.js'), 'utf-8');
const html = fs.readFileSync(path.join(ROOT, 'templates/siberman/participant.html'), 'utf-8');
const inlineScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1])[0];

const appEl = { innerHTML: '', style: {} };
const domStub = () => ({ innerHTML: '', style: {}, textContent: '', value: '2025', appendChild: () => {}, addEventListener: () => {}, dataset: {}, querySelector: () => domStub() });
const sandbox = {
    console,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    document: {
        getElementById: (id) => id === 'app' ? appEl : domStub(),
        querySelectorAll: () => [],
        querySelector: () => domStub(),
        addEventListener: () => {},
        documentElement: { setAttribute: () => {}, getAttribute: () => 'dark' },
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    window: {},
};
sandbox.window = sandbox;
const filledScript = inlineScript.replace('{{ bib|tojson }}', '9999').replace('{{ year }}', '2025');
vm.createContext(sandbox);
vm.runInContext(commonJs, sandbox);
vm.runInContext(filledScript, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.stack}`); }
}

function statsRowHtml() {
    const m = appEl.innerHTML.match(/<div class="stats-row">([\s\S]*?)<\/div>\s*(<div class="mode-toggle">|$)/);
    return m ? m[1] : '';
}

const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
const maxSeqBike2 = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);

function mkFinishedInd(bib, overallS, gender, rankG) {
    return {
        bib, gender, status: 'active', overall_s: overallS, overall_rank_g: rankG,
        swim_s: 1000, bike1_s: 9000, bike2_s: 8000, run_s: 2000,
        cp: {
            swim: { [maxSeqSwim]: 1000 }, bike_day1: { [maxSeqBike1]: 10000 },
            bike_day2: { [maxSeqBike2]: 18000 }, run: { [maxSeqRun]: overallS },
        },
    };
}
function mkRelayTeam(bib, teamName, overallS) {
    return {
        bib, team_name: teamName, overall_s: overallS,
        members: [
            { relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 1000, cp: { swim: { [maxSeqSwim]: 1000 } } },
            { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: 9000, bike2_s: 8000, cp: { bike_day1: { [maxSeqBike1]: 10000 }, bike_day2: { [maxSeqBike2]: 18000 } } },
            { relay_stage: 'run', status: 'active', gender: 'M', run_s: overallS - 18000, cp: { run: { [maxSeqRun]: overallS } } },
        ],
    };
}

check('stageBody() — Сплит/Общее время bike_day1 для эстафетного велосипедиста относительно СВОЕГО старта (после T1 пловца), не от старта гонки', () => {
    // 2026-08-06, найдено на живой гонке: cumulative_s bike_day1 в БД —
    // elapsed от старта ГОНКИ (единый таймер со swim), не от старта вело
    // конкретного велосипедиста — команда 1061, пловец финишировал за
    // 2:50:05 (10205с), велосипедист достиг 3км в raw 2:56:32 (10592с) от
    // старта гонки — реальное время НА вело всего 0:06:27 (387с), но
    // карточка показывала raw "2:56:32" в "Общее время".
    vm.runInContext(`_mode = 'stage';`, sandbox);
    const r = {
        relay_stage: 'bike', gender: 'M', status: 'active',
        swim_s: null, _teamSwimS: 10205,
        cp: { bike_day1: { 1: 10592, 2: 11155 } },
        splits: { bike_day1: { 1: 10592, 2: 563 } },
    };
    const rowsHtml = sandbox.stageBody('bike_day1', r, [], 'X', [], 'X');
    assert.ok(rowsHtml.includes('0:06:27'), `ожидался relative "Сплит"/"Общее время" 0:06:27 на 3км: ${rowsHtml}`);
    assert.ok(rowsHtml.includes('0:15:50'), `ожидалось relative "Общее время" 0:15:50 на 10км: ${rowsHtml}`);
    assert.ok(!rowsHtml.includes('2:56:32'), `сырое (не relative) "2:56:32" не должно попадать в вывод: ${rowsHtml}`);
    assert.ok(!rowsHtml.includes('3:05:55'), `сырое (не relative) "3:05:55" не должно попадать в вывод: ${rowsHtml}`);
});

check('renderIndividual() финишировавший — Место (абсолют) + Место (по полу), без дублей мест', () => {
    const data = {
        individual: [
            mkFinishedInd(1, 20000, 'M', 1),
            mkFinishedInd(2, 25000, 'M', 2),
        ],
        relay: [mkRelayTeam(1000, 'КомандаА', 22000)],
    };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, data.individual[0]);
    const stats = statsRowHtml();
    assert.ok(stats.includes('Место (абсолют)'), `нет "Место (абсолют)": ${stats}`);
    assert.ok(stats.includes('Место (по полу)'), `нет "Место (по полу)": ${stats}`);
    // Личник 1 (20000с) быстрее команды (22000с) и личника 2 (25000с) — абсолютное место 1.
    assert.ok(/rank-num[^>]*>1<\/span>|stat-val">1</.test(stats) || stats.includes('>1<'), `ожидалось место 1: ${stats}`);
});

check('renderTeam() — Место (абсолют) + Место (формат), не название команды как индикатор', () => {
    const data = {
        individual: [mkFinishedInd(1, 20000, 'M', 1)],
        relay: [mkRelayTeam(1000, 'КомандаА', 22000), mkRelayTeam(1001, 'КомандаБ', 26000)],
    };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderTeam(data, data.relay[0]);
    const stats = statsRowHtml();
    assert.ok(stats.includes('Место (абсолют)'), `нет "Место (абсолют)": ${stats}`);
    assert.ok(stats.includes('Место (формат)'), `нет "Место (формат)": ${stats}`);
    assert.ok(!stats.includes('Место (по полу)'), 'у команды не должно быть "Место (по полу)"');
});

function progressBarBlockHtml() {
    const m = appEl.innerHTML.match(/<div class="pb-outer">([\s\S]*?)<\/div>\s*<div class="stats-row">/);
    return m ? m[1] : '';
}

check('progressBarHtml() — не стартовал: маркер на 0%, чип с километражем не показан', () => {
    const row = { bib: 1, gender: 'M', status: 'active', cp: {}, swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
    const html = sandbox.progressBarHtml(row);
    assert.ok(html.includes('pb-marker-dot') && html.includes('left:0%'), `маркер должен быть на 0%: ${html}`);
    assert.ok(!html.includes('pb-inline-chip'), `чип не должен показываться для не стартовавшего: ${html}`);
});

check('progressBarHtml() — активен на Вело День 2: чип "km / 515 км" (прогресс ПО ВСЕЙ гонке, не по этапу), маркер на позиции', () => {
    // 2026-08-04: раньше основной бегунок карточки показывал чип с
    // километражем ЭТАПА ("119.0 / 276 км") — путало (выглядело так, будто
    // участник на 119 из 276 км всей гонки). Теперь — прогресс по всей
    // дистанции (0-515 км), этапный чип остаётся только у stageProgressBarHtml.
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const row = {
        bib: 1, gender: 'M', status: 'active',
        swim_s: 1000, bike1_s: 9000, bike2_s: null, run_s: null,
        cp: { swim: { [maxSeqSwim]: 1000 }, bike_day1: { [maxSeqBike1]: 10000 }, bike_day2: { 3: 400 } },
    };
    const html = sandbox.progressBarHtml(row);
    // STAGE_KM_OFFSET.bike_day2 (155) + CHECKPOINT_DIST_KM.bike_day2[3] (119) = 274 км из 515
    assert.ok(html.includes('274.0 / 515 км'), `ожидался чип "274.0 / 515 км": ${html}`);
    const expectedX = vm.runInContext('kmToVirtualX(STAGE_KM_OFFSET.bike_day2 + CHECKPOINT_DIST_KM.bike_day2[3])', sandbox);
    assert.ok(html.includes(`left:${expectedX}%`), `маркер должен быть на ${expectedX}%: ${html}`);
});

check('progressBarHtml() — финишировал: заливка 100%, подпись "Финиш"', () => {
    const html = sandbox.progressBarHtml(mkFinishedInd(1, 20000, 'M', 1));
    assert.ok(html.includes('Финиш'), `ожидалась подпись "Финиш": ${html}`);
    assert.ok(html.includes('width:100%'), `заливка должна быть 100%: ${html}`);
});

check('progressBarHtml() — флажки старта и финиша присутствуют (п.7, 2026-07-23)', () => {
    const html = sandbox.progressBarHtml(mkFinishedInd(1, 20000, 'M', 1));
    assert.ok(html.includes('pb-flag-start'), `ожидался флажок старта: ${html}`);
    assert.ok(html.includes('pb-flag-finish'), `ожидался флажок финиша: ${html}`);
});

check('stageProgressBarHtml() — прогресс ВНУТРИ этапа (0-100% этапа, не всей гонки), п.8 2026-07-23', () => {
    const maxSeqBike2Local = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const row = { cp: { bike_day2: { 3: 400 } } };
    const html = sandbox.stageProgressBarHtml('bike_day2', row);
    // CHECKPOINT_DIST_KM.bike_day2[3] = 119 км, длина этапа = 276 км -> ~43.1%
    const expectedPct = vm.runInContext('(CHECKPOINT_DIST_KM.bike_day2[3] / CHECKPOINT_DIST_KM.bike_day2[STAGE_MAX_SEQ.bike_day2]) * 100', sandbox);
    assert.ok(html.includes(`width:${expectedPct}%`), `заливка должна быть ${expectedPct}% (прогресс внутри этапа): ${html}`);
    assert.ok(html.includes('119.0'), `чип должен показывать километраж внутри этапа: ${html}`);
    assert.ok(html.includes('pb-flag-start') && html.includes('pb-flag-finish'), `флажки должны быть и на этапном бегунке: ${html}`);
});
check('stageProgressBarHtml() — финиш этапа: заливка 100%, подпись "Финиш"', () => {
    const maxSeqBike2Local = vm.runInContext('STAGE_MAX_SEQ.bike_day2', sandbox);
    const row = { cp: { bike_day2: { [maxSeqBike2Local]: 18000 } } };
    const html = sandbox.stageProgressBarHtml('bike_day2', row);
    assert.ok(html.includes('width:100%'), `заливка должна быть 100% на финише этапа: ${html}`);
    assert.ok(html.includes('Финиш'), `ожидалась подпись "Финиш": ${html}`);
});

check('progressBarHtml() — эстафетная команда через teamGapRow (та же функция, без спецкейса)', () => {
    const team = mkRelayTeam(1000, 'КомандаА', 22000);
    const teamRow = vm.runInContext('teamGapRow', sandbox)(team);
    const html = sandbox.progressBarHtml(teamRow);
    assert.ok(html.includes('Финиш'), `команда из mkRelayTeam уже финишировала (run cp = maxSeq): ${html}`);
});

check('progressBarHtml() встроен в renderIndividual() перед .stats-row', () => {
    const data = { individual: [mkFinishedInd(1, 20000, 'M', 1)], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, data.individual[0]);
    const block = progressBarBlockHtml();
    assert.ok(block.includes('pb-track'), `бегунок должен быть отрисован перед stats-row: ${appEl.innerHTML.slice(0, 400)}`);
});
check('progressBarHtml() встроен в renderTeam() перед .stats-row', () => {
    const data = { individual: [], relay: [mkRelayTeam(1000, 'КомандаА', 22000)] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderTeam(data, data.relay[0]);
    const block = progressBarBlockHtml();
    assert.ok(block.includes('pb-track'), `бегунок команды должен быть отрисован перед stats-row: ${appEl.innerHTML.slice(0, 400)}`);
});

check('renderIndividual() — бейдж "Лично" у ФИО в шапке, колонка "Формат" убрана из таблицы КТ (2026-07-22 п.2)', () => {
    const data = { individual: [mkFinishedInd(1, 20000, 'M', 1)], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, data.individual[0]);
    assert.ok(appEl.innerHTML.includes('badge-individual'), 'должен быть бейдж "Индивидуальный" у ФИО');
    assert.ok(!appEl.innerHTML.includes('>Формат<'), `колонка "Формат" должна быть убрана из таблицы КТ: ${appEl.innerHTML.slice(0, 800)}`);
});
check('renderTeam() — бейдж "Эстафета" + статус у названия команды в шапке (2026-07-22 п.2/п.4)', () => {
    const data = { individual: [], relay: [mkRelayTeam(1000, 'КомандаА', 22000)] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderTeam(data, data.relay[0]);
    assert.ok(appEl.innerHTML.includes('badge-relay'), 'должен быть бейдж "Эстафета" у названия команды');
    assert.ok(appEl.innerHTML.includes('badge-fin">Финиш'), `команда из mkRelayTeam финишировала — ожидался бейдж "Финиш": ${appEl.innerHTML.slice(0, 800)}`);
});
check('teamStatusBadge() — DNF любого члена команды даёт бейдж DNF', () => {
    const team = mkRelayTeam(1000, 'КомандаБ', null);
    team.members[1].status = 'dnf';
    const badge = vm.runInContext('teamStatusBadge', sandbox)(team);
    assert.ok(badge.includes('badge-dnf'), `ожидался бейдж DNF: ${badge}`);
});

check('renderIndividual() — Место (по полу) и Место (абсолют) несут СВОЁ отставание (stat-subgap), не одно общее "Отставание" (п.3, 2026-07-22)', () => {
    // М 20000с (лидер абсолюта и мужчин), Ж 21000с (лидер женщин, но не абсолюта — отставание от М),
    // М2 25000с (не лидер ни по чему).
    const data = {
        individual: [
            mkFinishedInd(1, 20000, 'M', 1),
            mkFinishedInd(2, 21000, 'F', 1),
            mkFinishedInd(3, 25000, 'M', 2),
        ],
        relay: [],
    };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, data.individual[1]); // Женщина, 21000с
    const stats = statsRowHtml();
    assert.ok(!stats.includes('>Отставание<'), `общего "Отставание" быть не должно — только внутри Место (по полу)/(абсолют): ${stats}`);
    // Женщина — лидер СРЕДИ ЖЕНЩИН (единственная), отставание по полу = 0 → не показывается (fmtGap(0) falsy).
    // Но отставание ПО АБСОЛЮТУ — от мужчины-лидера (20000с): +1000с = "+16:40".
    assert.ok(stats.includes('+16:40'), `ожидалось отставание по абсолюту +16:40 от лидера 20000с: ${stats}`);
    assert.ok(stats.includes('stat-subgap'), `отставание должно быть внутри блока места (stat-subgap): ${stats}`);
});

check('rankStatHtml() — внутри блока лейбл идёт ПЕРЕД отставанием (число места → лейбл → отставание)', () => {
    const html = vm.runInContext('rankStatHtml', sandbox)(1, '+00:12', 'Место (абсолют)');
    const lblPos = html.indexOf('Место (абсолют)');
    const gapPos = html.indexOf('+00:12');
    assert.ok(lblPos !== -1 && gapPos !== -1, `оба фрагмента должны присутствовать: ${html}`);
    assert.ok(lblPos < gapPos, `лейбл должен идти раньше отставания: ${html}`);
});

check('renderIndividual() — живые "Итого"/"Место" видны ДО финиша всей гонки, а не только после (Задача 9, 2026-08-03)', () => {
    // Не финишировал: плавание пройдено, на вело-дне 1 дошёл до 5-й КТ (не последней).
    const liveRow = {
        bib: 5, gender: 'M', status: 'active', overall_s: null, overall_rank_g: null,
        swim_s: 1000, bike1_s: null, bike2_s: null, run_s: null,
        cp: { swim: { [maxSeqSwim]: 1000 }, bike_day1: { 5: 4000 } },
    };
    const data = {
        individual: [liveRow, mkFinishedInd(2, 25000, 'M', 1)],
        relay: [],
    };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, liveRow);
    const stats = statsRowHtml();
    assert.ok(stats.includes('>Итого<'), `"Итого" должно быть видно ещё до финиша: ${stats}`);
    assert.ok(stats.includes('Место (абсолют)'), `"Место (абсолют)" должно быть видно ещё до финиша: ${stats}`);
    assert.ok(stats.includes('Место (по полу)'), `"Место (по полу)" должно быть видно ещё до финиша: ${stats}`);
    assert.ok(stats.includes('Сейчас на этапе'), `"Сейчас на этапе" должно остаться до финиша: ${stats}`);
    assert.ok(stats.includes('Отметка'), `"Отметка" должно остаться до финиша: ${stats}`);
    // Живой участник (4000с накопленных на 5-й КТ вело) идёт впереди финишировавшего
    // 25000с — единый ранг racePos/raceSortKey ставит "дальше по этапу" впереди "сырого" времени.
    assert.ok(!stats.includes('>Отставание<'), `общего "Отставание" быть не должно — только stat-subgap внутри Место: ${stats}`);
});

check('renderTeam() — "Итого команды" считается живьём (racePos) до финиша, не только team.overall_s', () => {
    const liveTeam = mkRelayTeam(2000, 'КомандаЖивая', 22000);
    liveTeam.members[2].cp = { run: { 3: 300 } }; // бегун на 3-й КТ бега, не на финише
    delete liveTeam.overall_s;
    const data = { individual: [], relay: [liveTeam, mkRelayTeam(1000, 'КомандаФиниш', 22000)] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderTeam(data, liveTeam);
    const stats = statsRowHtml();
    assert.ok(!stats.includes('stat-val">NaN'), `"Итого команды" не должно быть NaN при отсутствии team.overall_s: ${stats}`);
    assert.ok(!stats.includes('stat-val"></div><div class="stat-lbl">Итого команды'), `"Итого команды" должно показывать живое накопленное время: ${stats}`);
});

check('renderIndividual() — этап, который участник ещё не начал вовсе, показывает бейдж "—" (не "Финиш")', () => {
    // Тот же баг, что и в results.html (withStageStatus, п.5 v7,
    // 2026-08-03): раньше локальная копия withStageStatus в этом файле
    // "тихо" подменяла статус на dnf для любого активного, ещё не
    // финишировавшего этап участника — здесь проверяем итоговый бейдж
    // конкретно этапа "Плавание" у того, кто ещё вообще не начал гонку.
    const notStarted = { bib: 3, gender: 'M', status: 'active', cp: {}, swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
    const data = { individual: [notStarted], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, notStarted);
    assert.ok(appEl.innerHTML.includes('badge-notstarted">—<'), `этап "Плавание" у ещё не стартовавшего должен показывать "—": ${appEl.innerHTML}`);
});

// ── stageHasStarted(): та же живая логика "—"→"На трассе", что и в
// results.html (найдено пользователем 2026-08-04) — теперь и на карточке
// участника. Секция этапа ищется по <summary>...</summary><...>Вело День 1
function stageSectionHtml(label) {
    const m = appEl.innerHTML.match(new RegExp(`<span class="stage-title">${label}</span>[\\s\\S]*?</details>`));
    return m ? m[0] : '';
}
check('renderIndividual() — финишировал заплыв, но ещё не дошёл до 3 км вело-дня-1 — "На трассе", не "—"', () => {
    const r = { bib: 3, gender: 'M', status: 'active', cp: { swim: { [maxSeqSwim]: 4000 } }, swim_s: 4000, bike1_s: null, bike2_s: null, run_s: null };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, r);
    const section = stageSectionHtml('Вело День 1');
    assert.ok(section.includes('badge-live">На трассе'), `финишировавший заплыв должен быть "На трассе" на вело-дне-1: ${section}`);
});
check('renderIndividual() — заплыв ещё НЕ финиширован (частичный swim_s) — вело-день-1 остаётся "—"', () => {
    const r = { bib: 3, gender: 'M', status: 'active', cp: { swim: { 4: 1380 } }, swim_s: 1380, bike1_s: null, bike2_s: null, run_s: null };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, r);
    const section = stageSectionHtml('Вело День 1');
    assert.ok(section.includes('badge-notstarted">—<'), `незавершённый заплыв не должен давать "На трассе" на вело-дне-1: ${section}`);
});
check('renderIndividual() — средняя скорость/темп на этапе появляется слева от бейджа после первой отметки', () => {
    // seq=2 → 2.6 км (CHECKPOINT_DIST_KM.swim[2]), value=2600с → 2600/2.6=1000 сек/км
    // → fmtPace100m(1000) = "1:40 /100м" (запрошено пользователем 2026-08-06).
    const r = { bib: 3, gender: 'M', status: 'active', cp: { swim: { 1: 1200, 2: 2600 } }, swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, r);
    const section = stageSectionHtml('Плавание');
    assert.ok(section.includes('stage-pace">1:40 /100м<'), `ожидался темп "1:40 /100м" в секции Плавание: ${section}`);
});
check('renderIndividual() — этап без единой отметки НЕ показывает среднюю скорость/темп', () => {
    const r = { bib: 3, gender: 'M', status: 'active', cp: {}, swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, r);
    const section = stageSectionHtml('Плавание');
    assert.ok(!section.includes('stage-pace'), `без единой отметки не должно быть темпа/скорости: ${section}`);
});
check('renderIndividual() — личный старт дня 2 уже наступил — "На трассе" без КТ', () => {
    const raceStartEpoch = Date.now() - 5 * 86400 * 1000;
    sandbox.__data_raceStart = new Date(raceStartEpoch).toISOString();
    vm.runInContext('_raceStartEpoch = new Date(__data_raceStart).getTime();', sandbox);
    const r = { bib: 3, gender: 'M', status: 'active', cp: {}, swim_s: 4000, bike1_s: 20000, bike2_s: null, run_s: null, bike2_start_s: 8 * 3600 };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, r);
    const section = stageSectionHtml('Вело День 2');
    assert.ok(section.includes('badge-live">На трассе'), `наступивший личный старт дня 2 должен давать "На трассе": ${section}`);
    vm.runInContext('_raceStartEpoch = null;', sandbox);
});
check('renderTeam() — эстафетный велосипедист: команда финишировала заплыв — "На трассе" через swim КОМАНДЫ', () => {
    const team = {
        bib: 1000, team_name: 'КомандаА', overall_s: null,
        members: [
            { relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 4000, cp: { swim: { [maxSeqSwim]: 4000 } } },
            { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: null, bike2_s: null, cp: {} },
            { relay_stage: 'run', status: 'active', gender: 'M', run_s: null, cp: {} },
        ],
    };
    const data = { individual: [], relay: [team] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderTeam(data, team);
    const section = stageSectionHtml('Вело День 1');
    assert.ok(section.includes('badge-live">На трассе'), `эстафетный велосипедист должен видеть финиш заплыва СВОЕЙ команды: ${section}`);
});

// ── Бейдж "N предыдущих финишей Siberman" (звезда) в шапке карточки —
// только личный зачёт, только если finish_count > 0 (2026-08-05) ──
check('renderIndividual() — finish_count > 0 показывает бейдж со звездой и числом', () => {
    const r = { ...mkFinishedInd(1, 20000, 'M', 1), finish_count: 3 };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, r);
    assert.ok(appEl.innerHTML.includes('badge-star'), `ожидался бейдж badge-star: ${appEl.innerHTML.slice(0, 500)}`);
    assert.ok(appEl.innerHTML.includes('>3</span>') || appEl.innerHTML.includes('star.png" alt="">3'), `ожидалось число 3 рядом со звездой: ${appEl.innerHTML.slice(0, 500)}`);
});
check('renderIndividual() — finish_count = 0 (первый раз) — бейдж со звездой не показывается', () => {
    const r = { ...mkFinishedInd(1, 20000, 'M', 1), finish_count: 0 };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, r);
    assert.ok(!appEl.innerHTML.includes('badge-star'), `не должно быть бейджа звезды при finish_count=0: ${appEl.innerHTML.slice(0, 500)}`);
});
check('renderTeam() — бейдж со звездой не показывается у эстафетной команды (только личный зачёт)', () => {
    const team = mkRelayTeam(1000, 'КомандаА', 22000);
    const data = { individual: [], relay: [team] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderTeam(data, team);
    assert.ok(!appEl.innerHTML.includes('badge-star'), `эстафета не должна показывать звезду: ${appEl.innerHTML.slice(0, 500)}`);
});

// ── Рекорды Siberman (2026-08-05) — "🏆 Рекорд: ..." у "Итого" и в
// секции этапа, если ИМЕННО этот участник — держатель ──
check('renderIndividual() — показывает "🏆 Рекорд" у "Итого", если участник держит рекорд "overall"', () => {
    const r = { ...mkFinishedInd(1, 20000, 'M', 1), surname: 'Иванов', name: 'Пётр' };
    const data = { individual: [r], relay: [] };
    vm.runInContext(`_recordsIndex = buildRecordsIndex([{column_key:'overall',category:'absolute',best_s:20000,holder_name:'Иванов Пётр'}]);`, sandbox);
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, r);
    assert.ok(appEl.innerHTML.includes('🏆 Абсолют'), `ожидался бейдж рекорда: ${appEl.innerHTML.slice(0, 600)}`);
    vm.runInContext(`_recordsIndex = {};`, sandbox);
});
check('renderIndividual() — без записи в индексе рекордов бейдж не показывается', () => {
    const r = { ...mkFinishedInd(1, 20000, 'M', 1), surname: 'Иванов', name: 'Пётр' };
    const data = { individual: [r], relay: [] };
    vm.runInContext(`_recordsIndex = {};`, sandbox);
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'race';`, sandbox);
    sandbox.renderIndividual(data, r);
    assert.ok(!appEl.innerHTML.includes('stage-record') && !appEl.innerHTML.includes('🏆'), `не должно быть значка рекорда: ${appEl.innerHTML.slice(0, 600)}`);
});

// ── stageBody() — прогноз в колонке "Общее время" для будущих КТ (2026-08-06) ──
check('renderIndividual() — будущие КТ показывают "~" прогноз в "Общее время", "Сплит"/"Темп" остаются "—"', () => {
    // pos: seq=2 (10 км), value=1000с. Прогноз на seq=3 (72 км, bike_day1):
    // 1000 * (72/10) = 7200с = 2:00:00. Прогноз на финиш (seq=6, 145 км):
    // 1000 * (145/10) = 14500с = 4:01:40.
    const r = { bib: 3, gender: 'M', status: 'active', cp: { bike_day1: { 1: 500, 2: 1000 } }, swim_s: 0, bike1_s: null, bike2_s: null, run_s: null };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'stage';`, sandbox);
    sandbox.renderIndividual(data, r);
    const section = stageSectionHtml('Вело День 1');
    assert.ok(section.includes('forecast-cell">~2:00:00<'), `ожидался прогноз ~2:00:00 на 72 км: ${section}`);
    assert.ok(section.includes('forecast-cell">~4:01:40<'), `ожидался прогноз ~4:01:40 на финиш (145 км): ${section}`);
    // Строка с прогнозом всё равно "pending" — Сплит/Темп остаются "—".
    const row72 = section.slice(section.indexOf('72 км'));
    assert.ok(row72.slice(0, 200).includes('>—<'), `Сплит/Темп у будущей КТ должны остаться "—": ${row72.slice(0, 200)}`);
});
check('renderIndividual() — этап ещё не начат вовсе: все будущие КТ остаются "—" без прогноза', () => {
    const r = { bib: 3, gender: 'M', status: 'active', cp: {}, swim_s: null, bike1_s: null, bike2_s: null, run_s: null };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'stage';`, sandbox);
    sandbox.renderIndividual(data, r);
    const section = stageSectionHtml('Вело День 1');
    assert.ok(!section.includes('forecast-cell'), `без единой отметки прогноза быть не должно: ${section}`);
});
check('renderIndividual() — пройденная КТ показывает РЕАЛЬНОЕ время, не прогноз', () => {
    const r = { bib: 3, gender: 'M', status: 'active', cp: { bike_day1: { 1: 500, 2: 1000 } }, swim_s: 0, bike1_s: null, bike2_s: null, run_s: null };
    const data = { individual: [r], relay: [] };
    appEl.innerHTML = '';
    vm.runInContext(`_mode = 'stage';`, sandbox);
    sandbox.renderIndividual(data, r);
    const section = stageSectionHtml('Вело День 1');
    const row10 = section.slice(section.indexOf('10 км'), section.indexOf('72 км'));
    assert.ok(row10.includes('>16:40<') || row10.includes('0:16:40'), `у пройденной КТ (10 км, 1000с=16:40) должно быть реальное время, не прогноз: ${row10}`);
    assert.ok(!row10.includes('forecast-cell'), `у пройденной КТ не должно быть forecast-cell: ${row10}`);
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
