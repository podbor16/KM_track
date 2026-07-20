# Место по этапам (график «Позиция») + бегунок прохождения КТ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить переключатель этапа в график «Позиция» на `/siberman/results` (место внутри выбранного этапа вместо/в дополнение к абсолютному месту по всей гонке) и новый компонент-бегунок прохождения КТ на `/siberman/participant/{bib}`.

**Architecture:** Оба пункта — чистый frontend, без изменений backend/БД. Переиспользуются существующие хелперы `siberman-common.js` (`computeCheckpointRanks`, `currentStage`, `lastReached`, `CHECKPOINT_DIST_KM`, `STAGE_KM_OFFSET`, `STAGE_MAX_SEQ`, `STAGE_ORDER`, `teamGapRow`). `POSITION_X_SEGMENTS`/`kmToVirtualX()` переносятся из `results.html` в `siberman-common.js`, т.к. нужны в обоих шаблонах.

**Tech Stack:** Vanilla JS (без фреймворка), Chart.js v4 (`/static/lib/chart4/chart.umd.min.js`), тесты через `node:vm` (в проекте нет JS-тест-фреймворка).

**Спека:** `docs/superpowers/specs/2026-07-20-siberman-stage-position-and-progress-bar-design.md`

---

## Часть A — Место по этапам в графике «Позиция» (`results.html`)

### Task 1: `buildPositionDatasets(stage)` — режим «место внутри этапа»

**Files:**
- Modify: `templates/siberman/results.html:1395-1418` (функция `buildPositionDatasets`)
- Test: `tests/js/test_siberman_results_merge.js`

- [ ] **Step 1: Написать падающий тест**

Локальный ранг (внутри этапа) должен отличаться от глобального в случаях, когда участник впереди по этапу, но позади по совокупному времени гонки. Добавить в конец `tests/js/test_siberman_results_merge.js`, перед строками `console.log(failures === 0 ...`:

```js
check('buildPositionDatasets(stage) — место ВНУТРИ этапа (не по всей гонке), реальный км без экстраполяции x=0', () => {
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
    assert.strictEqual(a.data.length, 1, 'без экстраполяции до x=0 в per-stage режиме');
    assert.strictEqual(a.data[0].x, 7, 'X — реальный км ВНУТРИ этапа (CHECKPOINT_DIST_KM.run[1] = 7)');
    assert.strictEqual(a.data[0].y, 1, 'A локально впереди на бегу (500с < 5000с) — место 1');
    assert.strictEqual(b.data[0].y, 2, 'B локально позади на бегу — место 2');
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
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL buildPositionDatasets(stage) — место ВНУТРИ этапа...` (TypeError или неверный x, т.к. функция ещё не принимает параметр)

- [ ] **Step 3: Реализовать**

Заменить функцию `buildPositionDatasets()` (`templates/siberman/results.html:1395-1418`) на:

```js
function buildPositionDatasets(stage) {
    const { individual, relay } = getFiltered();
    const rows = [
        ...individual.map(r => ({ key: r.bib, name: `${r.surname} ${r.name}`, cp: r.cp, swim_s: r.swim_s, bike1_s: r.bike1_s, bike2_s: r.bike2_s, run_s: r.run_s })),
        ...relay.map(t => { const tr = teamGapRow(t); return { key: t.bib, name: t.team_name, cp: tr.cp, swim_s: tr.swim_s, bike1_s: tr.bike1_s, bike2_s: tr.bike2_s, run_s: tr.run_s }; }),
    ];
    if (stage) {
        // Место ВНУТРИ этапа (не по всей гонке) — сравнение только по
        // сырому времени НА этом этапе (computeCheckpointRanks), не по
        // накопленному времени гонки. X — реальный км этапа, без
        // экстраполяции до x=0 (у каждого этапа своя первая настоящая
        // КТ рядом со стартом, "нулевая" точка тут не нужна).
        const bySeq = computeCheckpointRanks(rows, stage, STAGE_MAX_SEQ[stage]);
        return rows.map(r => {
            const pts = [];
            for (let seq = 1; seq <= STAGE_MAX_SEQ[stage]; seq++) {
                const rank = bySeq[seq]?.[r.key];
                if (rank != null) pts.push({ x: CHECKPOINT_DIST_KM[stage][seq], y: rank });
            }
            return pts.length ? { _bib: r.key, _name: r.name, data: pts } : null;
        }).filter(Boolean);
    }
    const ranksByStage = {};
    STAGE_ORDER.forEach(s => { ranksByStage[s] = computeGlobalCheckpointRanks(rows, s, STAGE_MAX_SEQ[s]); });
    return rows.map(r => {
        const pts = [];
        STAGE_ORDER.forEach(s => {
            const bySeq = ranksByStage[s];
            for (let seq = 1; seq <= STAGE_MAX_SEQ[s]; seq++) {
                const rank = bySeq[seq]?.[r.key];
                if (rank != null) pts.push({ x: STAGE_KM_OFFSET[s] + CHECKPOINT_DIST_KM[s][seq], y: rank });
            }
        });
        if (pts.length && pts[0].x > 0) pts.unshift({ x: 0, y: pts[0].y });
        return pts.length ? { _bib: r.key, _name: r.name, data: pts } : null;
    }).filter(Boolean);
}
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: обе новые проверки `OK`, остальные тесты по-прежнему `OK` (сигнатура вызова без аргумента не сломана — везде, где раньше вызывалось `buildPositionDatasets()`, `stage` будет `undefined`, что фолсово, ветка не сработает)

- [ ] **Step 5: Commit**

```bash
git add templates/siberman/results.html tests/js/test_siberman_results_merge.js
git commit -m "feat(siberman): buildPositionDatasets(stage) — место внутри этапа (п.11)"
```

---

### Task 2: `_positionStage` — состояние и кнопки переключения этапа

**Files:**
- Modify: `templates/siberman/results.html:410` (блок State) и `templates/siberman/results.html:1420-1433` (шапка `renderPositionChart()`)

- [ ] **Step 1: Добавить состояние**

Рядом с `let _paceStage = 'swim';` (`templates/siberman/results.html:410`) добавить:

```js
let _positionStage = null; // null = "Вся гонка"; иначе один из STAGE_ORDER
```

- [ ] **Step 2: Добавить кнопки в разметку `renderPositionChart()`**

В `templates/siberman/results.html`, заменить начало `renderPositionChart()` (строки 1420-1432):

```js
function renderPositionChart() {
    const datasets = buildPositionDatasets(_positionStage);
    _lastChartDatasets = datasets;
    const visibleBibs = new Set(datasets.map(d => d._bib));
    _chartSelectedBibs = _chartSelectedBibs.filter(bib => visibleBibs.has(bib));
    const positionStageOptions = [{ key: 'all', label: 'Вся гонка' }, ...STAGE_ORDER.map(s => ({ key: s, label: STAGE_LABEL_RU[s] }))];
    document.getElementById('app').innerHTML = `
        <div class="filters" style="padding:0 0 12px;border-bottom:none;background:transparent">
            <span class="filter-label">Этап:</span>
            <div class="filter-group" id="positionStageGroup">
                ${positionStageOptions.map(o => `<button class="filter-btn${(o.key === 'all' ? _positionStage === null : o.key === _positionStage) ? ' active' : ''}" data-positionstage="${o.key}">${o.label}</button>`).join('')}
            </div>
        </div>
        <div class="chart-card"><div class="chart-layout">
            ${chartSidebarHtml(datasets)}
            <div class="chart-main">
                <div class="chart-hint">${_chartSelectedBibs.length ? 'Сравнение выбранных участников — снимите отметку слева, чтобы вернуться к общему виду' : (_positionStage ? `Место на этапе «${STAGE_LABEL_RU[_positionStage]}» на каждой пройденной КТ. Наведите/коснитесь линии, чтобы увидеть участника, либо выберите нескольких слева для сравнения` : 'Место в общем зачёте на каждой пройденной КТ по всей дистанции (0–515 км). Наведите/коснитесь линии, чтобы увидеть участника, либо выберите нескольких слева для сравнения')}</div>
                <div class="chart-canvas-wrap chart-canvas-wrap--position"><canvas id="sibermanPositionChart"></canvas></div>
            </div>
        </div></div>`;
    document.querySelectorAll('#positionStageGroup [data-positionstage]').forEach(btn => {
        btn.addEventListener('click', () => { _positionStage = btn.dataset.positionstage === 'all' ? null : btn.dataset.positionstage; renderPositionChart(); });
    });
    attachChartSidebarHandlers();
```

(Остальная часть функции, начиная с `if (_positionChart) { _positionChart.destroy(); ... }`, не меняется на этом шаге.)

- [ ] **Step 3: Ручная проверка кода на синтаксис**

Run: `node -c templates/siberman/results.html` — не сработает напрямую (файл не чистый JS), вместо этого проверить через существующий тестовый харнесс, который уже извлекает inline `<script>` и выполняет его в `node:vm`:

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED` (харнесс парсит весь файл как JS — синтаксическая ошибка проявится как исключение при `vm.runInContext` до первого теста)

- [ ] **Step 4: Commit**

```bash
git add templates/siberman/results.html
git commit -m "feat(siberman): переключатель этапа для графика «Позиция» (UI, без логики осей)"
```

---

### Task 3: Ось X/Y, тултип и hover по режиму (`renderPositionChart`)

**Files:**
- Modify: `templates/siberman/results.html:1434-1523` (тело `renderPositionChart()` после разметки)
- Test: `tests/js/test_siberman_results_merge.js`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_siberman_results_merge.js`:

```js
check('renderPositionChart() per-stage — ось X реальный км этапа, без stageBoundaries-плагина', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { cp: { run: { 1: 500, 2: 1000 } } });
    setRaceData([rowA], [], Date.now());
    vm.runInContext(`_positionStage = 'run'; _chartSelectedBibs = [];`, sandbox);
    sandbox.renderPositionChart();
    const chart = vm.runInContext('_positionChart', sandbox);
    const maxSeqRun = vm.runInContext('STAGE_MAX_SEQ.run', sandbox);
    assert.strictEqual(chart.config.options.scales.x.max, 14, 'CHECKPOINT_DIST_KM.run[2] = 14 (7 * 2)');
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
    chart.options.onHover.call(chart, null, [{ datasetIndex: 0, index: 0 }]);
    assert.ok(chart._hoverInfo.text.includes('7.0 км: место 1'), `неожиданный текст: ${chart._hoverInfo.text}`);
});
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL` на всех трёх новых проверках (ось X всё ещё всегда 0-100, `stageBoundaries` всегда присутствует, hover-текст всегда через `virtualXToKm`)

- [ ] **Step 3: Реализовать**

В `templates/siberman/results.html`, заменить тело `renderPositionChart()` начиная с `if (_positionChart) { _positionChart.destroy(); _positionChart = null; }` (строка 1435) до конца функции (строка 1523) на:

```js
    if (_positionChart) { _positionChart.destroy(); _positionChart = null; }
    if (datasets.length === 0) {
        document.querySelector('.chart-canvas-wrap').innerHTML = '<div class="empty">Нет данных для графика</div>';
        return;
    }
    const maxRank = Math.max(...datasets.flatMap(d => d.data.map(p => p.y)));
    const accent = cssVar('--red');
    const context = cssVar('--chart-context');
    const isCompare = _chartSelectedBibs.length > 0;
    // В per-stage режиме X уже реальный км этапа — виртуальное преобразование
    // (kmToVirtualX/withVirtualX) применимо только к графику "вся гонка".
    const virtualDatasets = _positionStage ? datasets : datasets.map(withVirtualX);
    const chartDatasets = isCompare
        ? virtualDatasets.filter(d => _chartSelectedBibs.includes(d._bib))
            .map(d => buildCompareDataset(d, chartCompareColor(_chartSelectedBibs.indexOf(d._bib))))
        : virtualDatasets.map(d => buildSpaghettiDataset(d, accent, context));

    const stageBoundaryPlugin = {
        id: 'stageBoundaries',
        afterDraw(chart) {
            const { ctx, chartArea, scales } = chart;
            ctx.save();
            ctx.strokeStyle = cssVar('--border');
            ctx.setLineDash([4, 4]);
            ctx.lineWidth = 1;
            ctx.font = '10px system-ui, sans-serif';
            ctx.fillStyle = cssVar('--muted');
            [{ km: 10, label: 'Вело' }, { km: 155, label: null }, { km: 431, label: 'Бег' }].forEach(({ km, label }) => {
                const x = scales.x.getPixelForValue(kmToVirtualX(km));
                ctx.beginPath();
                ctx.moveTo(x, chartArea.top);
                ctx.lineTo(x, chartArea.bottom);
                ctx.stroke();
                if (label) ctx.fillText(label, x + 4, chartArea.top + 12);
            });
            ctx.restore();
        },
    };

    const formatHoverPoint = _positionStage
        ? (x, y) => `${x.toFixed(1)} км: место ${y}`
        : (x, y) => `${virtualXToKm(x).toFixed(1)} км: место ${y}`;

    const ctx = document.getElementById('sibermanPositionChart').getContext('2d');
    _positionChart = new Chart(ctx, {
        type: 'line',
        data: { datasets: chartDatasets },
        plugins: [...(_positionStage ? [] : [stageBoundaryPlugin]), activeLineLabelPlugin],
        options: {
            responsive: true, maintainAspectRatio: false,
            layout: { padding: { top: 36, bottom: 12, left: 4, right: 12 } },
            interaction: { mode: 'nearest', intersect: false, axis: 'xy' },
            plugins: {
                legend: { display: isCompare, position: 'top', labels: { color: cssVar('--text'), boxWidth: 12, font: { size: 11 } } },
                tooltip: isCompare
                    ? { callbacks: { label(item) { const km = _positionStage ? item.parsed.x : virtualXToKm(item.parsed.x); return `${item.dataset.label} — ${km.toFixed(1)} км: место ${item.parsed.y}`; } } }
                    : { enabled: false },
            },
            scales: {
                x: {
                    type: 'linear', min: 0,
                    max: _positionStage ? CHECKPOINT_DIST_KM[_positionStage][STAGE_MAX_SEQ[_positionStage]] : 100,
                    title: { display: true, text: _positionStage ? 'Километраж этапа' : 'Километраж гонки', color: cssVar('--muted') },
                    ticks: { color: cssVar('--muted'), stepSize: _positionStage ? undefined : 10, callback: v => _positionStage ? v.toFixed(0) : Math.round(virtualXToKm(v)) },
                    grid: { color: cssVar('--border') },
                },
                y: {
                    reverse: true,
                    min: -Math.max(2, Math.round(maxRank * 0.12)), max: maxRank + 1.5,
                    afterBuildTicks: axis => {
                        axis.ticks = [];
                        for (let v = 1; v <= maxRank; v++) axis.ticks.push({ value: v });
                    },
                    title: { display: true, text: 'Место', color: cssVar('--muted') },
                    ticks: { color: cssVar('--muted') },
                    grid: { color: cssVar('--border') },
                },
            },
        },
    });
    if (!isCompare) attachSpaghettiHover(_positionChart, accent, context, formatHoverPoint);
}
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add templates/siberman/results.html tests/js/test_siberman_results_merge.js
git commit -m "feat(siberman): график «Позиция» — режим места внутри этапа (п.11, полностью)"
```

---

### Task 4: Проверка на реальных данных и полный прогон тестов (Часть A)

**Files:** нет изменений кода, только верификация

- [ ] **Step 1: Полный JS-прогон**

Run: `node tests/js/test_siberman_results_merge.js && node tests/js/test_siberman_participant.js`
Expected: `ALL PASSED` в обоих

- [ ] **Step 2: Python-тесты (регрессия backend не ожидается, но проверить)**

Run: `conda run -n base python -m pytest tests/unit/ -q`
Expected: все тесты проходят (изменения только во frontend, но правило проекта — прогонять перед коммитом)

- [ ] **Step 3: Проверка на реальных данных прода**

Написать одноразовый скрипт `deploy/verify_position_stage.js` (или scratchpad), который грузит `prod_2025.json` (уже должен быть доступен в проекте по паттерну прошлых сессий — если нет, получить через `curl https://<прод>/api/siberman/results?year=2025 > /tmp/prod_2025.json`), передаёт в `buildPositionDatasets('bike_day1')` внутри того же `node:vm` харнесса, что и тесты, и печатает первые 5 строк датасета — визуально свериться, что km/ранги выглядят разумно (первый участник = 1, км растут монотонно). Удалить скрипт после проверки.

- [ ] **Step 4: Отметить в TodoWrite/сообщить пользователю, что нужна визуальная проверка в браузере**

Открыть `/siberman/results` → «График» → «Позиция», переключить этапы, свериться, что подписи границ этапов пропадают в per-stage режиме и появляются в «Вся гонка».

---

## Часть B — Бегунок прохождения КТ (`participant.html`)

### Task 5: Перенос `POSITION_X_SEGMENTS`/`kmToVirtualX` в `siberman-common.js`

**Files:**
- Modify: `static/js/siberman-common.js` (добавить в конец файла, после `STAGE_KM_OFFSET` на строке 183, либо в конец файла — выбрать место рядом с `STAGE_KM_OFFSET`, т.к. семантически связаны)
- Modify: `templates/siberman/results.html:1364-1377` (удалить перенесённый код)
- Test: `tests/js/test_siberman_results_merge.js` (уже есть тесты на `kmToVirtualX`/`virtualXToKm` — должны продолжать проходить без изменений, т.к. харнесс подгружает `siberman-common.js` ДО инлайн-скрипта `results.html`)

- [ ] **Step 1: Убедиться, что существующие тесты `kmToVirtualX` проходят ДО переноса (baseline)**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED` (в т.ч. `kmToVirtualX — границы сегментов...`, `kmToVirtualX — середина сегмента плавания...`)

- [ ] **Step 2: Перенести код**

В `static/js/siberman-common.js`, сразу после строки `const STAGE_KM_OFFSET = { swim: 0, bike_day1: 10, bike_day2: 155, run: 431 };` (строка 183), добавить:

```js

// Пропорциональная ширина по X для графика "Позиция" и бегунка прохождения
// КТ на странице участника — НЕ реальный километраж (тогда плавание
// 10/515≈2% сжималось бы в почти невидимую полоску), а фиксированные доли
// ширины: Плавание 20% / Вело 50% (вело1+вело2 идут подряд без разрыва в
// километраже, 10→431 км — единый сегмент) / Бег 30%.
const POSITION_X_SEGMENTS = [
    { kmStart: 0,   kmEnd: 10,  xStart: 0,  xEnd: 20 },   // Плавание — 20%
    { kmStart: 10,  kmEnd: 431, xStart: 20, xEnd: 70 },   // Вело (день1+день2) — 50%
    { kmStart: 431, kmEnd: 515, xStart: 70, xEnd: 100 },  // Бег — 30%
];
function kmToVirtualX(km) {
    for (const seg of POSITION_X_SEGMENTS) {
        if (km <= seg.kmEnd) {
            const frac = seg.kmEnd === seg.kmStart ? 0 : (km - seg.kmStart) / (seg.kmEnd - seg.kmStart);
            return seg.xStart + frac * (seg.xEnd - seg.xStart);
        }
    }
    return 100;
}
```

В `templates/siberman/results.html`, удалить блок строк 1358-1377 (комментарий + `POSITION_X_SEGMENTS` + `function kmToVirtualX`), оставив `virtualXToKm`/`withVirtualX` (строки 1378-1393) на месте — они используют `POSITION_X_SEGMENTS`/`kmToVirtualX` как глобальные имена, доступные из `siberman-common.js`, подключённого раньше по `<script>`.

Итоговый вид этого участка `results.html` (после удаления):

```js
function virtualXToKm(x) {
    for (const seg of POSITION_X_SEGMENTS) {
        if (x <= seg.xEnd) {
            const frac = seg.xEnd === seg.xStart ? 0 : (x - seg.xStart) / (seg.xEnd - seg.xStart);
            return seg.kmStart + frac * (seg.kmEnd - seg.kmStart);
        }
    }
    return 515;
}
function withVirtualX(d) {
    return { ...d, data: d.data.map(p => ({ x: kmToVirtualX(p.x), y: p.y })) };
}
```

- [ ] **Step 3: Убедиться, что тесты по-прежнему проходят**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED` (перенос не должен ничего сломать — те же имена в том же общем `vm`-контексте)

- [ ] **Step 4: Commit**

```bash
git add static/js/siberman-common.js templates/siberman/results.html
git commit -m "refactor(siberman): POSITION_X_SEGMENTS/kmToVirtualX в siberman-common.js (нужны и для бегунка на participant.html)"
```

---

### Task 6: `progressBarHtml()` — генерация разметки бегунка

**Files:**
- Modify: `templates/siberman/participant.html` (новая функция, разместить рядом с другими html-билдерами — например, перед `function renderIndividual(data, r) {` на строке 391)
- Test: `tests/js/test_siberman_participant.js`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_siberman_participant.js`, перед `console.log(failures === 0 ...`:

```js
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

check('progressBarHtml() — эстафетная команда через teamGapRow (та же функция, без спецкейса)', () => {
    const team = mkRelayTeam(1000, 'КомандаА', 22000);
    const teamRow = vm.runInContext('teamGapRow', sandbox)(team);
    const html = sandbox.progressBarHtml(teamRow);
    assert.ok(html.includes('Финиш'), `команда из mkRelayTeam уже финишировала (run cp = maxSeq): ${html}`);
});
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `node tests/js/test_siberman_participant.js`
Expected: `FAIL` со всех четырёх — `sandbox.progressBarHtml is not a function`

- [ ] **Step 3: Реализовать**

В `templates/siberman/participant.html`, перед `function renderIndividual(data, r) {` (строка 391), добавить:

```js
// Бегунок прохождения КТ (п.12 бэклога) — единая полоса 0→515 км на
// виртуальных пропорциях (POSITION_X_SEGMENTS/kmToVirtualX из
// siberman-common.js — те же, что использует график "Позиция"). Работает
// одинаково для личников и команд — оба несут cp/swim_s/bike1_s/bike2_s/
// run_s в одинаковой форме (у команды — через teamGapRow()).
function progressBarHtml(row) {
    const stage = currentStage(row);
    const finished = stage === 'run' && lastReached(row.cp, 'run')?.seq === STAGE_MAX_SEQ.run;
    let fillPct = 0, chipText = null, activeStageKey = null;
    if (finished) {
        fillPct = 100;
        chipText = 'Финиш';
        activeStageKey = 'run';
    } else if (stage) {
        const pos = lastReached(row.cp, stage);
        const kmInStage = CHECKPOINT_DIST_KM[stage][pos.seq];
        const stageLenKm = CHECKPOINT_DIST_KM[stage][STAGE_MAX_SEQ[stage]];
        fillPct = kmToVirtualX(STAGE_KM_OFFSET[stage] + kmInStage);
        chipText = `${kmInStage.toFixed(1)} / ${stageLenKm} км`;
        activeStageKey = stage;
    }
    const isBikeActive = activeStageKey === 'bike_day1' || activeStageKey === 'bike_day2';
    const b1 = kmToVirtualX(10), b2 = kmToVirtualX(155), b3 = kmToVirtualX(431);
    return `
    <div class="pb-outer">
        <div class="pb-track-wrap">
            ${chipText != null ? `<div class="pb-inline-chip" style="left:${fillPct}%">${chipText}</div>` : ''}
            <div class="pb-track">
                <div class="pb-seg swim"></div>
                <div class="pb-seg bike"></div>
                <div class="pb-seg run"></div>
                <div class="pb-fill" style="width:${fillPct}%"></div>
                <div class="pb-boundary" style="left:${b1}%"></div>
                <div class="pb-boundary" style="left:${b2}%;opacity:.5"></div>
                <div class="pb-boundary" style="left:${b3}%"></div>
            </div>
            <div class="pb-marker-dot" style="left:${fillPct}%"></div>
        </div>
        <div class="pb-stage-labels">
            <span class="swim${activeStageKey === 'swim' ? ' active' : ''}">Плавание</span>
            <span class="bike${isBikeActive ? ' active' : ''}">Вело</span>
            <span class="run${activeStageKey === 'run' ? ' active' : ''}">Бег</span>
        </div>
    </div>`;
}
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `node tests/js/test_siberman_participant.js`
Expected: `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add templates/siberman/participant.html tests/js/test_siberman_participant.js
git commit -m "feat(siberman): progressBarHtml() — бегунок прохождения КТ (п.12, логика без CSS/вёрстки в карточке)"
```

---

### Task 7: Встраивание бегунка в карточку + CSS

**Files:**
- Modify: `templates/siberman/participant.html:425-436` (`renderIndividual`, вставка перед `.stats-row`)
- Modify: `templates/siberman/participant.html:482-495` (`renderTeam`, вставка перед `.stats-row`)
- Modify: `templates/siberman/participant.html:93-96` (добавить CSS после `.stat-lbl`)
- Modify: `templates/siberman/participant.html:137-156` (мобильный `@media` блок)

- [ ] **Step 1: Добавить CSS**

В `templates/siberman/participant.html`, сразу после строки `.stat-lbl { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; margin-top: 1px; }` (строка 96), добавить:

```css
        /* ── Бегунок прохождения КТ (п.12) ── */
        .pb-outer { padding: 4px 18px 18px; }
        .pb-track-wrap { position: relative; }
        .pb-track { position: relative; height: 10px; border-radius: 5px; overflow: hidden; display: flex; background: var(--bg3); }
        .pb-seg { height: 100%; }
        .pb-seg.swim { width: 20%; background: rgba(106,171,215,.25); }
        .pb-seg.bike { width: 50%; background: rgba(122,122,140,.22); }
        .pb-seg.run  { width: 30%; background: rgba(34,197,94,.18); }
        .pb-fill { position: absolute; top: 0; left: 0; height: 100%; background: var(--red); opacity: .85; }
        .pb-boundary { position: absolute; top: 0; bottom: 0; width: 1px; background: rgba(255,255,255,.3); }
        .pb-marker-dot { position: absolute; top: -2px; width: 10px; height: 10px; border-radius: 50%; background: var(--bg2); border: 2px solid var(--red); transform: translateX(-5px); }
        .pb-inline-chip { position: absolute; top: -24px; transform: translateX(-50%); background: var(--red); color: #fff; padding: 3px 8px; border-radius: 10px; font-size: 11px; white-space: nowrap; }
        .pb-stage-labels { display: flex; margin-top: 6px; font-size: 11px; color: var(--muted); }
        .pb-stage-labels span.swim { width: 20%; }
        .pb-stage-labels span.bike { width: 50%; }
        .pb-stage-labels span.run  { width: 30%; }
        .pb-stage-labels span.active { color: var(--text); font-weight: 700; }
```

- [ ] **Step 2: Добавить мобильное сжатие**

В `@media (max-width: 640px)` (строка 137-156), добавить строку после `.p-city { font-size: 11px; }` (строка 144):

```css
            .pb-outer { padding: 4px 14px 14px; }
            .pb-inline-chip { font-size: 10px; padding: 2px 6px; top: -21px; }
            .pb-stage-labels { font-size: 10px; }
```

- [ ] **Step 3: Вставить в `renderIndividual()`**

В `templates/siberman/participant.html`, найти (строка ~425-436):

```js
    const html = `
    <div class="card">
        <div class="card-hdr">
            <div class="card-hdr-top">
                <span class="p-bib">№${r.bib}</span>
                <span class="p-name">${r.surname} ${r.name}</span>
                ${genderBadge(r.gender)}
                ${statusBadge(r, null)}
            </div>
            ${r.city ? `<div class="p-city">${r.city}</div>` : ''}
        </div>
        <div class="stats-row">${overallStat}</div>
```

Заменить на:

```js
    const html = `
    <div class="card">
        <div class="card-hdr">
            <div class="card-hdr-top">
                <span class="p-bib">№${r.bib}</span>
                <span class="p-name">${r.surname} ${r.name}</span>
                ${genderBadge(r.gender)}
                ${statusBadge(r, null)}
            </div>
            ${r.city ? `<div class="p-city">${r.city}</div>` : ''}
        </div>
        ${progressBarHtml(r)}
        <div class="stats-row">${overallStat}</div>
```

- [ ] **Step 4: Вставить в `renderTeam()`**

В `templates/siberman/participant.html`, найти (строка ~482-495):

```js
    const html = `
    <div class="card">
        <div class="card-hdr">
            <div class="card-hdr-top">
                <span class="p-bib">№${team.bib}</span>
                <span class="p-name">${team.team_name}</span>
            </div>
        </div>
        <div class="stats-row">
```

Заменить на:

```js
    const html = `
    <div class="card">
        <div class="card-hdr">
            <div class="card-hdr-top">
                <span class="p-bib">№${team.bib}</span>
                <span class="p-name">${team.team_name}</span>
            </div>
        </div>
        ${progressBarHtml(teamRow)}
        <div class="stats-row">
```

(`teamRow` уже вычислен на строке 448 функции `renderTeam` — `const teamRow = teamGapRow(team);`, переменная в области видимости.)

- [ ] **Step 5: Убедиться, что существующие тесты не сломаны**

Run: `node tests/js/test_siberman_participant.js`
Expected: `ALL PASSED` — тесты индикаторов мест (`statsRowHtml()`) ищут `<div class="stats-row">...` независимо от того, что теперь стоит ПЕРЕД ним, регекс не завязан на позицию блока

- [ ] **Step 6: Commit**

```bash
git add templates/siberman/participant.html
git commit -m "feat(siberman): бегунок прохождения КТ — встроен в шапку карточки участника/команды (п.12)"
```

---

### Task 8: Финальная верификация, коммит, деплой

**Files:** нет изменений кода, только верификация

- [ ] **Step 1: Полный прогон тестов**

Run: `node tests/js/test_siberman_results_merge.js && node tests/js/test_siberman_participant.js && conda run -n base python -m pytest tests/unit/ -q`
Expected: всё `PASSED`

- [ ] **Step 2: Проверка на реальных данных прода**

Написать одноразовый scratchpad-скрипт, аналогичный прежним `verify_*.js` в этой сессии: загрузить `/api/siberman/results?year=2025` с прода, прогнать `progressBarHtml()` для нескольких реальных участников (один явно финишировавший, один DNF, один активный на момент снепшота) через тот же `node:vm` харнесс, что и `test_siberman_participant.js`, распечатать `fillPct`/`chipText` — свериться, что значения в разумных пределах (0-100%, км растёт монотонно по этапам). Удалить скрипт после проверки.

- [ ] **Step 3: Push**

```bash
git push origin main
```

- [ ] **Step 4: Дождаться деплоя и проверить на проде**

По уже устоявшемуся в этой сессии паттерну: проверить `https://api.github.com/repos/podbor16/KM_track/actions/runs?per_page=3` на `conclusion: success` для последнего коммита, затем SSH через `plink.exe` (см. `deploy/ssh_apply_siberman_migration.py` как образец) — `git -C /opt/km_track rev-parse HEAD` должен совпасть с запушенным коммитом, `curl -sf http://localhost:8000/` — код 200, `grep -c progressBarHtml /opt/km_track/templates/siberman/participant.html` — должно быть > 0.

- [ ] **Step 5: Сообщить пользователю о необходимости визуальной проверки**

Открыть `/siberman/results` («График» → «Позиция», переключить этапы) и `/siberman/participant/{реальный bib}` (разные статусы: активный/DNF/финишировавший, личник и команда) в браузере — desktop и мобильная ширина. Напомнить про хард-рефреш (7-дневный кэш `static/js/*` — хотя в этой задаче правки в основном в `templates/`, которые не кэшируются так же агрессивно, но `siberman-common.js` из Части B — кэшируется).

---

## Порядок выполнения

Часть A (Task 1-4) и Часть B (Task 5-8) независимы друг от друга по коду (пересекаются только на переносе `POSITION_X_SEGMENTS`/`kmToVirtualX`, который является первым шагом Части B и не требует, чтобы Часть A была готова). Можно делать в любом порядке, но логичнее последовательно, т.к. это один связанный блок бэклога — тестировать/коммитить/деплоить одним заходом в конце (Task 8 покрывает обе части).
