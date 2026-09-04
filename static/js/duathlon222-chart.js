// Дуатлон 222 — вкладка «График» (Позиция / Темп-скорость). Использует
// глобалы, объявленные в инлайн-скрипте duathlon_results.html (STAGE_KM,
// STAGE_LABEL, allStandings, _genderFilter, fmtS, fmtPaceOrSpeed) — общий
// global scope между classic <script> тегами одной страницы, без модулей
// (см. tests/js/test_duathlon222_chart.js — тот же приём, что и харнесс для
// Siberman). Спека: docs/superpowers/specs/2026-09-04-duathlon222-charts-design.md

const STAGE_ORDER = ['run1', 'bike', 'run2'];

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
