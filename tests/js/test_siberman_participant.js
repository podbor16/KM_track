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

check('progressBarHtml() — активен на Вело День 2: чип "km / len км", маркер на позиции', () => {
    const maxSeqBike1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const row = {
        bib: 1, gender: 'M', status: 'active',
        swim_s: 1000, bike1_s: 9000, bike2_s: null, run_s: null,
        cp: { swim: { [maxSeqSwim]: 1000 }, bike_day1: { [maxSeqBike1]: 10000 }, bike_day2: { 3: 400 } },
    };
    const html = sandbox.progressBarHtml(row);
    // CHECKPOINT_DIST_KM.bike_day2[3] = 119 км, длина этапа = 276 км
    assert.ok(html.includes('119.0 / 276 км'), `ожидался чип "119.0 / 276 км": ${html}`);
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

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
