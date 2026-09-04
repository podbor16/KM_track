// Дуатлон 222 — вкладка «График» (Позиция / Темп-скорость). Использует
// глобалы, объявленные в инлайн-скрипте duathlon_results.html (STAGE_KM,
// STAGE_LABEL, allStandings, _genderFilter, fmtS, fmtPaceOrSpeed) — общий
// global scope между classic <script> тегами одной страницы, без модулей
// (см. tests/js/test_duathlon222_chart.js — тот же приём, что и харнесс для
// Siberman). Спека: docs/superpowers/specs/2026-09-04-duathlon222-charts-design.md

const STAGE_ORDER = ['run1', 'bike', 'run2'];

let _chartMode = 'position';       // 'position' | 'pace'
let _chartStage = 'all';           // 'all'|'run1'|'bike'|'run2' (position) или 'run1'|'bike'|'run2' (pace)
let _chartSelectedBibs = [];       // номера участников, выбранных для сравнения
let _chartSearchQuery = '';
let _chartSheetOpen = false;       // мобильный bottom-sheet

// «Раздутые» сегменты оси X в режиме «Вся гонка» (см. спеку, раздел 3) —
// фиксированные доли ширины НЕЗАВИСИМО от реальных км этапа, иначе Бег-1
// (10км) и Бег-2 (42км) схлопнутся в нечитаемые полоски рядом с Вело (170км).
const CHART_VIRTUAL_SEGMENTS = {
    run1: { start: 0, end: 25 },
    bike: { start: 25, end: 75 },
    run2: { start: 75, end: 100 },
};

// Реальный км внутри этапа -> позиция на виртуальной оси X (0-100). Клэмп
// в границы сегмента — защита от кривых данных (км > длины этапа).
function kmToVirtualX(stageCode, km) {
    const seg = CHART_VIRTUAL_SEGMENTS[stageCode];
    const stageKm = STAGE_KM[stageCode];
    const frac = stageKm > 0 ? Math.min(1, Math.max(0, km / stageKm)) : 0;
    return seg.start + frac * (seg.end - seg.start);
}

// Ранг участника в каждой ЕГО СОБСТВЕННОЙ точке — среди всех остальных,
// сравнивая elapsedS на момент этой же позиции (pos). У соперника берётся
// его ПОСЛЕДНЯЯ известная точка с pos <= текущей (интерполяция "назад" —
// тот же принцип, что у _live_gap_map на бэкенде, но здесь не гэп, а ранг).
// participants: [{ bib, points: [{pos, elapsedS, plotX?}, ...] }], points
// должны быть отсортированы по pos по возрастанию (гарантируется тем, что
// checkpoints с бэкенда уже отсортированы по lap_number). plotX, если
// указан, используется в возвращаемых точках вместо pos как x-координата
// (нужно для виртуальных X-сегментов режима "вся гонка" — см. Task 6).
function computeRanksAtPositions(participants) {
    const result = new Map();
    participants.forEach(p => result.set(p.bib, []));
    participants.forEach(p => {
        p.points.forEach(pt => {
            const atPos = participants.map(pp => {
                let val = null;
                for (const c of pp.points) {
                    if (c.pos <= pt.pos) val = c.elapsedS; else break;
                }
                return { bib: pp.bib, elapsedS: val };
            }).filter(e => e.elapsedS != null);
            // При точном совпадении elapsedS (реалистично — тайминг Copernico
            // усечён до целой секунды) порядок между ними не определяется
            // отдельно — стабильная сортировка оставляет их в порядке
            // элементов исходного participants (без смысловой гарантии по
            // месту), это осознанный компромисс: точная поминутная
            // тай-брейк-политика не нужна для визуализации на графике.
            atPos.sort((a, b) => a.elapsedS - b.elapsedS);
            const rank = atPos.findIndex(e => e.bib === p.bib) + 1;
            if (rank > 0) result.get(p.bib).push({ x: pt.plotX != null ? pt.plotX : pt.pos, y: rank });
        });
    });
    return result;
}

// Датасеты для графика "Позиция" (одиночный этап): rows — строки /standings
// (нужны r.start_number/r.surname/r.name/r.checkpoints[stageCode]). x=реальный
// км этапа, y=ранг (см. computeRanksAtPositions). Возврат — то же самое
// {_bib, _name, data} для каждого участника, что и у buildPositionDatasetsWholeRace
// и buildPaceDatasets (Task 7) — общая форма, которую рендер (Task 10) уже
// умеет отрисовывать одинаково для всех трёх.
function buildPositionDatasetsSingleStage(stageCode, rows) {
    const participants = rows.map(r => ({
        bib: r.start_number,
        name: `${r.surname} ${r.name}`,
        points: (r.checkpoints?.[stageCode] || []).map(cp => ({ pos: cp.km, elapsedS: cp.elapsed_s })),
    })).filter(p => p.points.length);
    const ranks = computeRanksAtPositions(participants);
    return participants.map(p => ({ _bib: p.bib, _name: p.name, data: ranks.get(p.bib) }));
}

// То же самое, но для режима "Вся гонка": ранг считается по ГЛОБАЛЬНОМУ км
// (globalBase — накопленная сумма STAGE_KM предыдущих этапов, растёт
// монотонно run1->bike->run2 в порядке STAGE_ORDER), а рисуется точка — по
// виртуальному X (kmToVirtualX) — эти две величины разные и не совпадают.
function buildPositionDatasetsWholeRace(rows) {
    const participants = rows.map(r => {
        const points = [];
        let globalBase = 0;
        STAGE_ORDER.forEach(sc => {
            (r.checkpoints?.[sc] || []).forEach(cp => {
                points.push({
                    pos: globalBase + cp.km,
                    elapsedS: cp.elapsed_s,
                    plotX: kmToVirtualX(sc, cp.km),
                });
            });
            globalBase += STAGE_KM[sc];
        });
        return { bib: r.start_number, name: `${r.surname} ${r.name}`, points };
    }).filter(p => p.points.length);
    const ranks = computeRanksAtPositions(participants);
    return participants.map(p => ({ _bib: p.bib, _name: p.name, data: ranks.get(p.bib) }));
}

// Датасеты для графика "Темп/Скорость" (одиночный этап): rows — строки
// /standings. Y всегда км/ч (даже для беговых этапов) — единообразно с тем,
// как уже хранится _speed_kmh/current_stage_speed_kmh на бэкенде; перевод в
// темп (мин/км) — только на отображении, через уже существующий
// fmtPaceOrSpeed(). Так не нужна условная инверсия оси Y между бегом/вело
// (быстрее = больше км/ч = выше на графике, для обоих типов этапов одинаково).
// x=км (после сплита), y=скорость в км/ч (dKm / (dT / 3600)). Если меньше
// двух отметок на этапе или dKm <= 0 или dT <= 0 — участник не попадает
// в датасеты (нечего рисовать).
function buildPaceDatasets(stageCode, rows) {
    return rows.map(r => {
        const cps = r.checkpoints?.[stageCode] || [];
        const pts = [];
        for (let i = 1; i < cps.length; i++) {
            const dKm = cps[i].km - cps[i - 1].km;
            const dT = cps[i].elapsed_s - cps[i - 1].elapsed_s;
            if (dKm <= 0 || dT <= 0) continue;
            pts.push({ x: cps[i].km, y: dKm / (dT / 3600) });
        }
        return pts.length ? { _bib: r.start_number, _name: `${r.surname} ${r.name}`, data: pts } : null;
    }).filter(Boolean);
}

function chartToggleSelect(bib) {
    const idx = _chartSelectedBibs.indexOf(bib);
    if (idx !== -1) _chartSelectedBibs.splice(idx, 1);
    else _chartSelectedBibs.push(bib);
}
function chartFilteredParticipants(rows) {
    const q = _chartSearchQuery.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(r => (r.surname || '').toLowerCase().includes(q));
}
function toggleSelectAllChart(rows) {
    const filtered = chartFilteredParticipants(rows);
    const allSelected = filtered.length > 0 && filtered.every(r => _chartSelectedBibs.includes(r.start_number));
    if (allSelected) {
        const filteredBibs = new Set(filtered.map(r => r.start_number));
        _chartSelectedBibs = _chartSelectedBibs.filter(bib => !filteredBibs.has(bib));
    } else {
        filtered.forEach(r => { if (!_chartSelectedBibs.includes(r.start_number)) _chartSelectedBibs.push(r.start_number); });
    }
}

const CHART_COLORS = [
    '#FF8562', '#263146', '#18A558', '#DE0000', '#4B7BE5',
    '#F5A623', '#9B59B6', '#1ABC9C', '#E67E22', '#2C3E50',
];
function chartColorForBib(bib, sortedRows) {
    const idx = sortedRows.findIndex(r => r.start_number === bib);
    return CHART_COLORS[(idx >= 0 ? idx : 0) % CHART_COLORS.length];
}
function renderChartParticipantPickers(rows) {
    const sorted = rows.slice().sort((a, b) => a.surname.localeCompare(b.surname, 'ru'));
    const filtered = chartFilteredParticipants(sorted);
    const itemsHtml = filtered.map(r => {
        const color = chartColorForBib(r.start_number, sorted);
        const isActive = _chartSelectedBibs.includes(r.start_number);
        return `<div class="tri-chart-legend-item${isActive ? ' active' : ''}"
                     onclick="chartToggleSelect(${r.start_number});renderActiveChart()">
            <span class="tri-chart-legend-dot" style="background:${color}"></span>
            <span>${r.surname} ${r.name}</span>
        </div>`;
    }).join('') || '<div class="tri-chart-sidebar__hint">Ничего не найдено</div>';
    const selectAllLabel = filtered.length && filtered.every(r => _chartSelectedBibs.includes(r.start_number))
        ? 'Очистить всех' : 'Выбрать всех';

    document.getElementById('chart-legend-list').innerHTML = itemsHtml;
    document.getElementById('chart-sheet-list').innerHTML = itemsHtml;
    document.getElementById('chart-select-all-btn').textContent = selectAllLabel;
    document.getElementById('chart-sheet-select-all-btn').textContent = selectAllLabel;
    document.getElementById('chart-sidebar-hint').style.display = _chartSelectedBibs.length ? 'none' : '';
    document.getElementById('chart-mobile-badge').textContent = _chartSelectedBibs.length;

    const chipsEl = document.getElementById('chart-mobile-chips');
    chipsEl.innerHTML = _chartSelectedBibs.map(bib => {
        const r = sorted.find(rr => rr.start_number === bib);
        if (!r) return '';
        const color = chartColorForBib(bib, sorted);
        return `<div class="tri-chart-mobile-chip">
            <span class="tri-chart-mobile-chip-dot" style="background:${color}"></span>${r.surname}</div>`;
    }).join('');
}
function onChartSearchInput(value) {
    _chartSearchQuery = value;
    renderActiveChart();
}
// toggleSelectAllChart() принимает rows явным параметром (нужно для
// юнит-теста без обращения к allStandings) — разметке нужен вызов без
// аргументов, отсюда обёртка (использует getChartFilteredStandings() —
// появится в Task 10, но вызывается только по клику пользователя, не при
// загрузке скрипта, так что порядок объявления функций в файле не важен —
// function-декларации поднимаются в область видимости целиком).
function toggleSelectAllChartFromUi() {
    toggleSelectAllChart(getChartFilteredStandings());
    renderActiveChart();
}
function openChartSheet() {
    _chartSheetOpen = true;
    document.getElementById('chart-sheet').classList.add('open');
    document.getElementById('chart-sheet-overlay').classList.add('open');
}
function closeChartSheet() {
    _chartSheetOpen = false;
    document.getElementById('chart-sheet').classList.remove('open');
    document.getElementById('chart-sheet-overlay').classList.remove('open');
}

// Какая ЛИНИЯ ближе всего к пикселю курсора/клика — по Y на прямой между
// двумя соседними по X точками ЭТОГО датасета, интерполированной РОВНО в X
// курсора (так же, как Chart.js физически рисует линию), а не по ближайшей
// одиночной точке. Портировано из templates/siberman/results.html
// (nearestDatasetIndexAtPixel) — тот же риск (редкие отметки на этапе
// Дуатлона 222, особенно Бег-1/Бег-2 с 8-25 точками на ~15 участников).
function nearestDatasetIndexAtPixel(chart, xPixel, yPixel, maxDistPx = null) {
    const xScale = chart.scales?.x, yScale = chart.scales?.y;
    if (!xScale || !yScale) return null;
    const cursorX = xScale.getValueForPixel(xPixel);
    let bestIdx = null, bestDist = Infinity;
    chart.data.datasets.forEach((ds, i) => {
        const pts = ds.data;
        if (!pts || pts.length === 0) return;
        let p0 = null, p1 = null;
        for (let k = 0; k < pts.length - 1; k++) {
            if (pts[k].x <= cursorX && cursorX <= pts[k + 1].x) { p0 = pts[k]; p1 = pts[k + 1]; break; }
        }
        let yAtCursor;
        if (p0 && p1) {
            const frac = p1.x === p0.x ? 0 : (cursorX - p0.x) / (p1.x - p0.x);
            yAtCursor = p0.y + frac * (p1.y - p0.y);
        } else {
            const edge = cursorX < pts[0].x ? pts[0] : pts[pts.length - 1];
            yAtCursor = edge.y;
        }
        const dist = Math.abs(yScale.getPixelForValue(yAtCursor) - yPixel);
        if (dist < bestDist) { bestDist = dist; bestIdx = i; }
    });
    if (bestIdx == null) return null;
    return (maxDistPx != null && bestDist > maxDistPx) ? null : bestIdx;
}
