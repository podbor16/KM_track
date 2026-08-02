/* ────────────────────────────────────────────────────────────────────────
 * Siberman — общие хелперы для results.html и participant.html.
 *
 * Вынесено из results.html в задаче 5 ("страница участника"), т.к. обеим
 * страницам нужны одни и те же расчёты (gap/статус/форматирование), и
 * дублирование этой логики уже приводило к нескольким раундам расхождений
 * между копиями (см. sessions/2026-07-09-siberman-gap.md).
 * ──────────────────────────────────────────────────────────────────────── */

/* ──────────────── Theme ──────────────── */
function siInitTheme() {
    const saved = localStorage.getItem('siberman-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    const btn = document.getElementById('themeBtn');
    if (btn) btn.textContent = saved === 'dark' ? '☀️' : '🌙';
}

function toggleTheme() {
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    const btn = document.getElementById('themeBtn');
    if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
    localStorage.setItem('siberman-theme', next);
}

/* ──────────────── Formatters ──────────────── */
function fmtTime(s) {
    if (s == null) return '—';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
}
function fmtPace(s) {
    if (s == null) return '—';
    return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')} /км`;
}
function fmtPace100m(secPerKm) {
    if (secPerKm == null) return '—';
    const s = Math.round(secPerKm / 10);
    return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')} /100м`;
}
function fmtSpeed(v) {
    if (v == null) return '—';
    return `${Number(v).toFixed(1)} км/ч`;
}
function genderBadge(g) {
    if (g === 'M') return '<span class="badge badge-m">М</span>';
    if (g === 'F') return '<span class="badge badge-f">Ж</span>';
    return '';
}
function formatBadge() {
    return '<span class="badge badge-e">Э</span>';
}
function rankClass(rank) {
    if (rank === 1) return 'rank-1';
    if (rank === 2) return 'rank-2';
    if (rank === 3) return 'rank-3';
    return '';
}

/* ──────────────── Статус ──────────────── */
const STATUS_ORDER = { active: 0, dnf: 1, dsq: 2, dns: 3 };
// progressFn(row) — опционально, "сколько прошёл" (км/дистанция), только
// как тай-брейк МЕЖДУ участниками одного НЕ-активного статуса (dnf-vs-dnf,
// dsq-vs-dsq...), у которых нет времени именно на этом срезе (timeKey===
// null у обоих) — кто прошёл больше, тот выше (запрошено пользователем
// 2026-08-02: раньше такие пары не досортировывались вовсе и шли в
// произвольном/исходном порядке). Если у обоих участников этого статуса
// есть время на этом срезе (реально финишировали ИМЕННО его, несмотря на
// DNF в целом по гонке) — сортируются как обычные, по времени. Для
// активных участников поведение не меняется (только для DNF/DSQ/DNS
// между собой, как и просил пользователь).
function sortByStatus(rows, timeKey, progressFn) {
    return [...rows].sort((a, b) => {
        const sa = STATUS_ORDER[a.status] ?? 4, sb = STATUS_ORDER[b.status] ?? 4;
        if (sa !== sb) return sa - sb;
        const ta = a[timeKey], tb = b[timeKey];
        if (ta == null && tb == null) {
            return (a.status !== 'active' && progressFn) ? progressFn(b) - progressFn(a) : 0;
        }
        if (ta == null) return 1;
        if (tb == null) return -1;
        return ta - tb;
    });
}
// Как sortByStatus, но для уже посчитанного значения в отдельном поле .v
// (не именованное свойство строки) — используется там, где значение не
// просто читается из объекта, а вычисляется (buildRankedEntries/
// renderBikeCombined). rawStatus — ИМЕННО общий статус участника за всю
// гонку, а не статус конкретного дня/этапа (dayStatus/bikeCombinedStatus,
// которые решают только что показать в ячейке времени/статуса) — сошедший
// позже (напр. на беге) должен "тонуть" вниз списка и блёкнуть, даже если
// на ЭТОМ дне/этапе у него есть время и статус "Финиш" (найдено
// пользователем 2026-08-02, тот же принцип, что уже работает на вкладке
// "Плавание" через sortByStatus + statusBadge). progressFn — тот же
// тай-брейк между НЕ-активными без значения на этом срезе, см. sortByStatus.
function sortByRawStatus(items, progressFn) {
    return [...items].sort((a, b) => {
        const aActive = a.rawStatus === 'active', bActive = b.rawStatus === 'active';
        if (aActive !== bActive) return aActive ? -1 : 1;
        if (a.v == null && b.v == null) {
            return (!aActive && progressFn) ? progressFn(b) - progressFn(a) : 0;
        }
        if (a.v == null) return 1;
        if (b.v == null) return -1;
        return a.v - b.v;
    });
}

/* stageKey: null = Финал, иначе 'swim'|'bike1'|'bike2'|'run' */
const STAGE_ORD = { swim: 0, bike1: 1, bike2: 2, run: 3 };
function getDnfStage(r) {
    // Этап, на котором произошёл DNF = первый этап без финишного времени
    if (r.swim_s  == null) return 'swim';
    if (r.bike1_s == null) return 'bike1';
    if (r.bike2_s == null) return 'bike2';
    return 'run';
}
function statusBadge(r, stageKey) {
    const s = r.status;
    if (s === 'dns') return '<span class="badge badge-dns">Не стартовал</span>';
    if (s === 'dsq') return '<span class="badge badge-dsq">DSQ</span>';
    if (s === 'dnf') {
        if (stageKey === null) return '<span class="badge badge-dnf">DNF</span>'; // Финал
        const dnfStage = getDnfStage(r);
        const diff = STAGE_ORD[stageKey] - STAGE_ORD[dnfStage];
        if (diff < 0)  return '<span class="badge badge-fin">Финиш</span>';
        if (diff === 0) return '<span class="badge badge-dnf">DNF</span>';
        return '<span class="badge badge-dns">Не стартовал</span>';
    }
    // active
    const hasTime = stageKey ? r[stageKey + '_s'] != null : r.overall_s != null;
    return hasTime
        ? '<span class="badge badge-fin">Финиш</span>'
        : '<span class="badge badge-live">На трассе</span>';
}
function relayMemberStatusBadge(m) {
    if (m.status === 'dnf') return '<span class="badge badge-dnf">DNF</span>';
    if (m.status === 'dns') return '<span class="badge badge-dns">Не стартовал</span>';
    if (m.status === 'dsq') return '<span class="badge badge-dsq">DSQ</span>';
    return '<span class="badge badge-fin">Финиш</span>';
}
// Статус ЭСТАФЕТНОЙ КОМАНДЫ целиком (не отдельного участника) — тот же
// 3-состояний бейдж, что уже был у личников (statusBadge), но команда не
// несёт своего "status" в API — используем упрощённый teamGapRow().status
// (dnf любого члена → dnf команды) + team.overall_s как признак финиша.
function teamStatusBadge(team) {
    const tr = teamGapRow(team);
    const notFinished = team.overall_s == null || tr.status !== 'active';
    if (!notFinished) return '<span class="badge badge-fin">Финиш</span>';
    return tr.status === 'dnf' ? '<span class="badge badge-dnf">DNF</span>' : '<span class="badge badge-live">На трассе</span>';
}

/* ──────────────── Этапы / контрольные точки ──────────────── */
const STAGE_MAX_SEQ = { swim: 7, bike_day1: 6, bike_day2: 8, run: 12 };
const STAGE_ORDER = ['swim', 'bike_day1', 'bike_day2', 'run'];
const TAB_TO_DB_STAGE = { swim: 'swim', bike1: 'bike_day1', bike2: 'bike_day2', run: 'run' };

// Заплыв — 4 круга по 2,5 км с буем-разворотом на середине каждого круга
// (см. src/siberman/service.py:SWIM_LAP_SEQS — то же самое зеркалом на
// клиенте). Только "круговые" seq входят в счётчик — "разворот"-КТ нет.
const SWIM_LAP_SEQS = { 2: 1, 4: 2, 6: 3, 7: 4 };

// Человекочитаемые подписи КТ — для колонки "последняя отсечка" и для
// страницы участника (детализация по каждой КТ этапа).
const CHECKPOINT_LABELS = {
    swim: {
        1: 'Разворот 1 (1,3 км)', 2: '1 круг (2,6 км)',
        3: 'Разворот 2 (3,9 км)', 4: '2 круга (5,2 км)',
        5: 'Разворот 3 (6,5 км)', 6: '3 круга (7,8 км)',
        7: 'Финиш (10 км)',
    },
    bike_day1: {
        1: '3 км', 2: '10 км', 3: '72 км (разворот)',
        4: '135 км', 5: '142 км', 6: 'Финиш (145 км)',
    },
    bike_day2: {
        1: '51 км', 2: '82 км', 3: '119 км', 4: '160 км (СШГЭС)',
        5: '190 км (Кольцо Саяногорск)', 6: '203 км', 7: '265 км',
        8: 'Финиш (276 км)',
    },
    run: Object.fromEntries(
        Array.from({ length: 12 }, (_, i) => {
            const n = i + 1;
            return [n, n === 12 ? `Финиш — 12 круг (84 км)` : `${n} круг (${n * 7} км)`];
        })
    ),
};

// Кумулятивная дистанция (км) на каждой КТ — для темпа/скорости на сплите
// между соседними КТ (страница участника).
const CHECKPOINT_DIST_KM = {
    swim: { 1: 1.3, 2: 2.6, 3: 3.9, 4: 5.2, 5: 6.5, 6: 7.8, 7: 10 },
    bike_day1: { 1: 3, 2: 10, 3: 72, 4: 135, 5: 142, 6: 145 },
    bike_day2: { 1: 51, 2: 82, 3: 119, 4: 160, 5: 190, 6: 203, 7: 265, 8: 276 },
    run: Object.fromEntries(Array.from({ length: 12 }, (_, i) => [i + 1, (i + 1) * 7])),
};

// Общая развилка единиц измерения по этапу — плавание темп/100м, вело
// скорость км/ч, бег темп/км. Общий примитив для splitPaceLabel (сплит
// между соседними КТ) и avgPaceLabel (средний темп от старта этапа до КТ,
// нужен генератору постов трансляции) — раньше эта развилка была ТОЛЬКО
// внутри splitPaceLabel, дублировать её для второго случая означало бы
// повторить тот же класс расхождений, что уже чинили в этом проекте
// (см. шапку файла).
function _paceOrSpeedLabel(dbStage, distKm, timeS) {
    if (timeS == null || !(distKm > 0)) return '—';
    if (dbStage === 'swim') return fmtPace100m(timeS / distKm);
    if (dbStage === 'bike_day1' || dbStage === 'bike_day2') return fmtSpeed(distKm / (timeS / 3600));
    return fmtPace(Math.round(timeS / distKm));
}
// Темп/скорость на СПЛИТЕ (между соседними КТ).
function splitPaceLabel(dbStage, seq, splitS) {
    const distTable = CHECKPOINT_DIST_KM[dbStage];
    const distKm = distTable[seq] - (distTable[seq - 1] ?? 0);
    return _paceOrSpeedLabel(dbStage, distKm, splitS);
}
// Средний темп/скорость ОТ СТАРТА ЭТАПА до конкретной КТ (не сплит между
// соседними КТ) — нужен генератору постов трансляции ("темп на отметке X км").
function avgPaceLabel(dbStage, distKm, elapsedS) {
    return _paceOrSpeedLabel(dbStage, distKm, elapsedS);
}

// То же самое, но возвращает ЧИСЛО (не форматированную строку) для графика:
// плавание — сек/100м, вело — км/ч, бег — сек/км. null, если сплит
// отсутствует или дистанция сплита нулевая (не должно случаться, но КТ
// таблица — внешние данные).
function splitPaceValue(dbStage, seq, splitS) {
    if (splitS == null) return null;
    const distTable = CHECKPOINT_DIST_KM[dbStage];
    const distKm = distTable[seq] - (distTable[seq - 1] ?? 0);
    if (!(distKm > 0)) return null;
    if (dbStage === 'swim') return splitS / distKm / 10;
    if (dbStage === 'bike_day1' || dbStage === 'bike_day2') return distKm / (splitS / 3600);
    return splitS / distKm;
}

// Смещение старта этапа в общем километраже гонки (0→515 км) — график
// "Позиция" использует это для оси X через весь забег целиком.
// 10 (плавание) + 145 (вело1) = 155; 155 + 276 (вело2) = 431 (см. также
// STAGE_LABEL_RU/STAGE_CFG в results.html и STAGE_DISTANCES_KM в service.py).
const STAGE_KM_OFFSET = { swim: 0, bike_day1: 10, bike_day2: 155, run: 431 };

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

// "N/4 кругов" для плавания, "N/12 кругов" для бега, null для вело (там нет
// понятия "круг").
function lapLabel(stage, seq) {
    if (stage === 'swim') {
        const lap = SWIM_LAP_SEQS[seq];
        return lap ? `${lap}/4 кругов` : null;
    }
    if (stage === 'run') return `${seq}/12 кругов`;
    return null;
}

// Русское склонение "круг"/"круга"/"кругов" по числу n.
function _circleWord(n) {
    const mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'круг';
    if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return 'круга';
    return 'кругов';
}

// Двухстрочная ячейка "последняя КТ": "N км" + "m круг"/"Финиш" на второй
// строке. Круг показывается только для плавания/бега (SWIM_LAP_SEQS/seq
// напрямую) — у вело нет понятия круга, там на некруговых КТ только "N км".
// На финише второй строкой всегда "Финиш", независимо от этапа. prefix —
// опционально, для "Дней" (results.html:renderRankedProgress), где сам
// этап меняется от строки к строке (не зафиксирован, как на вкладках
// этапов) — "Вело День 1, 135 км" вместо голого "135 км".
function lastCpTwoLineHtml(dbStage, seq, prefix) {
    if (seq == null) return '—';
    const km = CHECKPOINT_DIST_KM[dbStage][seq];
    const kmLine = `<div>${prefix ? prefix + ', ' : ''}${String(km).replace('.', ',')} км</div>`;
    if (seq === STAGE_MAX_SEQ[dbStage]) return kmLine + '<div class="muted-sub">Финиш</div>';
    const lapN = dbStage === 'swim' ? SWIM_LAP_SEQS[seq] : dbStage === 'run' ? seq : null;
    return lapN ? kmLine + `<div class="muted-sub">${lapN} ${_circleWord(lapN)}</div>` : kmLine;
}

function lastReached(cp, stage) {
    // {seq, value} последней непустой КТ этапа для участника, либо null
    if (!cp || !cp[stage]) return null;
    for (let seq = STAGE_MAX_SEQ[stage]; seq >= 1; seq--) {
        const v = cp[stage][seq];
        if (v != null) return { seq, value: v };
    }
    return null;
}

function valueAtOrBefore(cp, stage, seq) {
    if (!cp || !cp[stage]) return null;
    for (let s = seq; s >= 1; s--) {
        const v = cp[stage][s];
        if (v != null) return v;
    }
    return null;
}

function fmtGap(gapS) {
    if (gapS == null || gapS <= 0) return '';
    const h = Math.floor(gapS / 3600), m = Math.floor((gapS % 3600) / 60), s = gapS % 60;
    return h > 0
        ? `+${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
        : `+${m}:${String(s).padStart(2,'0')}`;
}

/* ──────────────── Gap (отставание от лидера) ──────────────── */

// rows: [{key, cp, status?}] — вычисляет {key: gap_s} относительно лидера
// пула (rows уже должны быть отфильтрованы по нужному разрезу: формат/пол/
// роль). Лидером может быть только тот, кто реально ДОШЁЛ до последней КТ
// этапа (pos.seq === maxSeq) — иначе сошедший на середине (без явной пометки
// DNF в файле — status всё ещё 'active') всегда "выигрывал" бы по наименьшему
// сырому времени, хотя прошёл меньше дистанции. Статус тоже проверяем — чтобы
// явно дисквалифицированный/DNF не мог стать лидером, даже дойдя до финиша.
// Gap при этом считается для всех, включая недошедших — от той же КТ,
// которую они последней прошли.
function computeStageGaps(rows, dbStage) {
    const maxSeq = STAGE_MAX_SEQ[dbStage];
    const withPos = rows
        .map(r => ({ key: r.key, cp: r.cp, status: r.status ?? 'active', pos: lastReached(r.cp, dbStage) }))
        .filter(r => r.pos);
    if (withPos.length === 0) return {};
    const candidates = withPos.filter(r => r.status === 'active' && r.pos.seq === maxSeq);
    if (candidates.length === 0) return {};
    const leader = candidates.reduce((a, b) => (a.pos.value <= b.pos.value ? a : b));
    const gaps = {};
    withPos.forEach(r => {
        if (r.key === leader.key) { gaps[r.key] = 0; return; }
        const leaderVal = valueAtOrBefore(leader.cp, dbStage, r.pos.seq);
        if (leaderVal != null) gaps[r.key] = r.pos.value - leaderVal;
    });
    return gaps;
}

// Общий генератор для "gap на каждой КТ" / "место на каждой КТ" — принимает
// valueFn(row, seq), извлекающий сравниваемое значение per-checkpoint.
// "На этапе" (computeCheckpointGaps/Ranks) — valueFn берёт сырой cp[stage][seq]
// (сравнение ТОЛЬКО внутри этого этапа). "В гонке" (computeGlobalCheckpointGaps/Ranks)
// — valueFn = globalProgress(row, stage, seq) (сумма прошлых полных этапов +
// прогресс на текущем — тот, кто медленнее прошёл прошлый этап, будет позади
// по гонке, даже если на ЭТОМ этапе он быстрее всех).
function _checkpointGapsByValueFn(rows, valueFn, maxSeq) {
    const bySeq = {};
    for (let seq = 1; seq <= maxSeq; seq++) {
        const vals = rows
            .map(r => ({ key: r.key, value: valueFn(r, seq) }))
            .filter(r => r.value != null);
        if (vals.length === 0) continue;
        const min = Math.min(...vals.map(v => v.value));
        bySeq[seq] = {};
        vals.forEach(v => { bySeq[seq][v.key] = v.value - min; });
    }
    return bySeq;
}
function _checkpointRanksByValueFn(rows, valueFn, maxSeq) {
    const bySeq = {};
    for (let seq = 1; seq <= maxSeq; seq++) {
        const vals = rows
            .map(r => ({ key: r.key, value: valueFn(r, seq) }))
            .filter(r => r.value != null)
            .sort((a, b) => a.value - b.value);
        if (vals.length === 0) continue;
        const ranks = {};
        vals.forEach((r, i) => {
            ranks[r.key] = (i > 0 && r.value === vals[i - 1].value) ? ranks[vals[i - 1].key] : i + 1;
        });
        bySeq[seq] = ranks;
    }
    return bySeq;
}

// Отставание/место НА КАЖДОЙ отдельной КТ, "на этапе" — сравнение только
// внутри текущего этапа (не учитывает результаты прошлых этапов). Точное
// совпадение seq (не valueAtOrBefore — та функция для "гэпа относительно
// финальной позиции"). gap===0 у лидера точки.
function computeCheckpointGaps(rows, dbStage, maxSeq) {
    return _checkpointGapsByValueFn(rows, (r, seq) => r.cp?.[dbStage]?.[seq], maxSeq);
}
function computeCheckpointRanks(rows, dbStage, maxSeq) {
    return _checkpointRanksByValueFn(rows, (r, seq) => r.cp?.[dbStage]?.[seq], maxSeq);
}

// То же самое, но "в гонке" — сравнение по СОВОКУПНОМУ времени гонки на
// момент этой КТ (globalProgress: прошлые полные этапы + прогресс на
// текущем). rows должны нести swim_s/bike1_s/bike2_s/run_s (как в
// buildOverallGapPool), не просто cp.
function computeGlobalCheckpointGaps(rows, dbStage, maxSeq) {
    return _checkpointGapsByValueFn(rows, (r, seq) => globalProgress(r, dbStage, seq), maxSeq);
}
function computeGlobalCheckpointRanks(rows, dbStage, maxSeq) {
    return _checkpointRanksByValueFn(rows, (r, seq) => globalProgress(r, dbStage, seq), maxSeq);
}

// Сырое elapsed-время на ВИРТУАЛЬНОЙ КТ объединённого вело (день1+день2 как
// один этап 0..421 км) — вынесено из computeBikeCombinedCheckpointRanks
// отдельной функцией, т.к. генератору постов трансляции нужно само значение
// времени (для строки "⏱️ Время на отметке"), не только место/гэп.
function bikeCombinedRawCp(row, vseq) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    if (vseq <= n1) return row.cp?.bike_day1?.[vseq];
    const v2 = row.cp?.bike_day2?.[vseq - n1];
    return v2 == null ? null : (row.bike1_s ?? 0) + v2;
}
// Место "по этапу" для ОБЪЕДИНЁННОГО вело (день1+день2 как один этап,
// 421 км, без разрыва на границе дней) — та же семантика, что и
// computeCheckpointRanks (сравнение только внутри вело-этапа, не по всей
// гонке), но КТ дня2 сравниваются по elapsed-времени ОТ НАЧАЛА ВСЕГО
// вело-этапа (bike1_s + cp.bike_day2[seq]), а не только внутри дня2 —
// иначе участники с разным временем на дне1 сравнивались бы некорректно
// на одинаковых КТ дня2. rows должны нести cp и bike1_s (как в
// computeGlobalCheckpointRanks). Виртуальный seq: 1..STAGE_MAX_SEQ.bike_day1
// — день1, дальше — день2 со сдвигом.
function computeBikeCombinedCheckpointRanks(rows) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    return _checkpointRanksByValueFn(rows, (r, vseq) => bikeCombinedRawCp(r, vseq), n1 + STAGE_MAX_SEQ.bike_day2);
}
// Гэп-вариант того же самого — нужен генератору постов трансляции (график
// "Позиция" использовал только Ranks, Gaps раньше не было нигде).
function computeBikeCombinedCheckpointGaps(rows) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    return _checkpointGapsByValueFn(rows, (r, vseq) => bikeCombinedRawCp(r, vseq), n1 + STAGE_MAX_SEQ.bike_day2);
}
// Дистанция (км) на виртуальной КТ объединённого вело — для отображения
// "N из 421 км" и для avgPaceLabel в постах трансляции.
function bikeCombinedDistKm(vseq) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    if (vseq <= n1) return CHECKPOINT_DIST_KM.bike_day1[vseq];
    return CHECKPOINT_DIST_KM.bike_day1[n1] + CHECKPOINT_DIST_KM.bike_day2[vseq - n1];
}
// Человекочитаемая подпись виртуальной КТ с пометкой дня — для выпадающего
// списка КТ в форме генератора постов трансляции.
function bikeCombinedCheckpointLabel(vseq) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    return vseq <= n1
        ? `${CHECKPOINT_LABELS.bike_day1[vseq]} (День 1)`
        : `${CHECKPOINT_LABELS.bike_day2[vseq - n1]} (День 2)`;
}

// Последняя достигнутая виртуальная КТ Свода вело (день2 приоритетнее —
// если есть хоть одна КТ дня2, день1 уже полностью пройден). null, если
// участник ещё не начинал вело вовсе.
function bikeCombinedLastSeq(cp) {
    const posDay2 = lastReached(cp, 'bike_day2');
    if (posDay2) return STAGE_MAX_SEQ.bike_day1 + posDay2.seq;
    const posDay1 = lastReached(cp, 'bike_day1');
    return posDay1 ? posDay1.seq : null;
}
// Двухстрочная ячейка "последняя КТ" для Свода вело — только "N км" (у
// вело нет круга), "Финиш" второй строкой на самой последней виртуальной КТ.
function bikeCombinedLastCpHtml(cp) {
    const vseq = bikeCombinedLastSeq(cp);
    if (vseq == null) return '—';
    const km = bikeCombinedDistKm(vseq);
    const kmLine = `<div>${String(km).replace('.', ',')} км</div>`;
    const maxVseq = STAGE_MAX_SEQ.bike_day1 + STAGE_MAX_SEQ.bike_day2;
    return vseq === maxVseq ? kmLine + '<div class="muted-sub">Финиш</div>' : kmLine;
}

// То же самое, но возвращает МЕСТО (1,2,3...) внутри пула вместо gap —
// только среди тех, кто реально дошёл до последней КТ этапа (та же логика
// финиша, что и в computeStageGaps), с учётом ничьих (как rank_by в
// service.py). Нужно для "текущего места" на странице участника, когда
// участник ещё не финишировал (серверный rank_stage посчитан только для
// финишировавших).
function computeStageRanks(rows, dbStage) {
    const maxSeq = STAGE_MAX_SEQ[dbStage];
    const finishers = rows
        .map(r => ({ key: r.key, pos: lastReached(r.cp, dbStage) }))
        .filter(r => r.pos && r.pos.seq === maxSeq)
        .sort((a, b) => a.pos.value - b.pos.value);
    const ranks = {};
    finishers.forEach((r, i) => {
        ranks[r.key] = (i > 0 && r.pos.value === finishers[i - 1].pos.value)
            ? ranks[finishers[i - 1].key]
            : i + 1;
    });
    return ranks;
}

// rows: [{key, cp, swim_s, bike1_s, bike2_s, run_s}] — то же самое, но в
// "глобальном" времени гонки (не в рамках одного этапа). Глобальное время
// на конкретной (stage, seq) = сумма ПОЛНЫХ итогов уже пройденных этапов
// + значение cp[stage][seq] (для swim/bike_day1 оно уже elapsed от старта
// гонки, для bike_day2/run — elapsed от старта СВОЕГО этапа, поэтому и
// нужно прибавлять итоги предыдущих этапов).
function globalProgress(row, stage, seq) {
    const v = row.cp?.[stage]?.[seq];
    if (v == null) return null;
    if (stage === 'swim' || stage === 'bike_day1') return v;
    if (stage === 'bike_day2') return (row.swim_s ?? 0) + (row.bike1_s ?? 0) + v;
    return (row.swim_s ?? 0) + (row.bike1_s ?? 0) + (row.bike2_s ?? 0) + v; // run
}

// maxStage — не заходить дальше этого этапа (используется на вкладках
// "Дни", где прогресс должен ограничиваться границей дня, а не реальным
// текущим этапом гонки — см. renderRankedProgress). Без maxStage — как
// раньше, последний этап по всей гонке (Итоги/Свод вело).
function currentStage(row, maxStage) {
    const maxIdx = maxStage ? STAGE_ORDER.indexOf(maxStage) : STAGE_ORDER.length - 1;
    for (let i = maxIdx; i >= 0; i--) {
        if (lastReached(row.cp, STAGE_ORDER[i])) return STAGE_ORDER[i];
    }
    return null;
}

// Статус ИМЕННО этого дня (не всей гонки) — по факту достижения последней
// КТ дневного этапа maxStage, а не по общему row.status. DNF, случившийся
// ПОСЛЕ этого дня (например, на беге в день 3), не должен помечать уже
// пройденный день как не пройденный — тот же класс бага/фикса, что и
// bikeCombinedStatus (results.html) для Свода вело, найдено пользователем
// 2026-08-02 на Дащенко/Пушкарёве (DNF на беге, но "Итог 1/2 дня" внутри
// показывал DNF, хотя вело-дни пройдены полностью). Без maxStage — status
// как есть (не влияет на другие вызовы).
function dayStatus(row, maxStage) {
    if (!maxStage || row.status === 'active') return row.status;
    const pos = lastReached(row.cp, maxStage);
    return (pos && pos.seq === STAGE_MAX_SEQ[maxStage]) ? 'active' : row.status;
}

// "Сколько км в гонке прошёл" (ограничено maxStage, если задан) — для
// сортировки DNF-участников МЕЖДУ СОБОЙ на "Днях", когда ни у кого из них
// нет времени на этот день (никто из них его не завершил): кто дальше
// продвинулся, тот выше (запрошено пользователем 2026-08-02) — тот же
// принцип, что и STAGE_KM_OFFSET использует для оси графика "Позиция".
function dayProgressKm(row, maxStage) {
    const stage = currentStage(row, maxStage);
    if (!stage) return 0;
    const pos = lastReached(row.cp, stage);
    return pos ? STAGE_KM_OFFSET[stage] + CHECKPOINT_DIST_KM[stage][pos.seq] : 0;
}

function computeOverallGaps(rows) {
    const withPos = rows.map(r => {
        const stage = currentStage(r);
        if (!stage) return null;
        const pos = lastReached(r.cp, stage);
        const value = globalProgress(r, stage, pos.seq);
        return value == null ? null : { key: r.key, cp: r.cp, row: r, status: r.status ?? 'active', stage, seq: pos.seq, value };
    }).filter(Boolean);
    if (withPos.length === 0) return {};
    // Лидер — только среди тех, кто реально финишировал ВСЮ гонку (дошёл до
    // последней КТ бега), тот же резон, что и в computeStageGaps: иначе
    // сошедший рано (без явной пометки DNF) "выигрывал" бы по наименьшему
    // сырому времени.
    const candidates = withPos.filter(r => r.status === 'active' && r.stage === 'run' && r.seq === STAGE_MAX_SEQ.run);
    if (candidates.length === 0) return {};
    const leader = candidates.reduce((a, b) => (a.value <= b.value ? a : b));
    const gaps = {};
    withPos.forEach(r => {
        if (r.key === leader.key) { gaps[r.key] = 0; return; }
        const leaderValAtStage = globalProgress(leader.row, r.stage, r.seq);
        if (leaderValAtStage != null) gaps[r.key] = r.value - leaderValAtStage;
    });
    return gaps;
}

// Собрать "виртуального участника" эстафетной команды для computeOverallGaps —
// swim/bike/run у неё разбросаны по трём разным членам команды.
function teamGapRow(team) {
    const bySwim = team.members.find(m => m.relay_stage === 'swim');
    const byBike = team.members.find(m => m.relay_stage === 'bike');
    const byRun  = team.members.find(m => m.relay_stage === 'run');
    return {
        key: team.bib,
        cp: {
            swim: bySwim?.cp?.swim,
            bike_day1: byBike?.cp?.bike_day1,
            bike_day2: byBike?.cp?.bike_day2,
            run: byRun?.cp?.run,
        },
        swim_s: bySwim?.swim_s, bike1_s: byBike?.bike1_s,
        bike2_s: byBike?.bike2_s, run_s: byRun?.run_s,
        // Команда считается активной, пока хотя бы её текущий "рабочий" член
        // не сошёл — упрощение: DNF любого члена трактуем как DNF команды.
        status: team.members.some(m => m.status === 'dnf') ? 'dnf' : 'active',
    };
}

// rows для computeCombinedOverallRanks — личники и эстафета в одной форме
// {key, overall_s, status}. Личники (rank_overall) и эстафета (считается
// на клиенте) раньше ранжировались раздельно — единого "абсолютного" места
// по всей гонке (личники+эстафета вместе) не было нигде. Эта пара функций
// его вводит.
function combinedOverallRankRows(individual, relay) {
    return [
        ...individual.map(r => ({ key: r.bib, overall_s: r.overall_s, status: r.status })),
        ...relay.map(t => ({ key: t.bib, overall_s: t.overall_s, status: teamGapRow(t).status })),
    ];
}

// Единое место по всей гонке (личники+эстафета вместе), независимо от
// активных фильтров формата/пола — считается по ПОЛНОМУ ростеру (все
// участники года), поэтому значение не "плавает" при переключении
// фильтров таблицы (см. п.14/п.4 задачи 2026-07-19).
// Место 1,2,3... по возрастанию r.val среди rows со status==='active' и
// val!=null (ничьи получают одинаковое место, следующее — пропускается).
// Общий примитив для "единого ранга" объединённого пула (личники+эстафета
// вместе) — переиспользуется и для абсолютного места по всей гонке
// (computeCombinedOverallRanks), и для места на конкретном этапе/по полу
// внутри этапа (results.html:renderStage — раньше личники брали ранг из
// БД, который считает ТОЛЬКО среди личников, а эстафетчики — свой отдельный
// relayPos-счётчик; при интерливинге в единый список это давало
// дублирующиеся места "1, 1, 2, 2..." — тот же баг, что чинили для Итогов
// гонки, п.14/доп.находка задачи 2026-07-19).
function computeRanksByValue(rows) {
    const finishers = rows
        .filter(r => r.status === 'active' && r.val != null)
        .sort((a, b) => a.val - b.val);
    const ranks = {};
    finishers.forEach((r, i) => {
        ranks[r.key] = (i > 0 && r.val === finishers[i - 1].val)
            ? ranks[finishers[i - 1].key]
            : i + 1;
    });
    return ranks;
}
function computeCombinedOverallRanks(rows) {
    return computeRanksByValue(rows.map(r => ({ key: r.key, val: r.overall_s, status: r.status })));
}
