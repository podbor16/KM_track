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
function rankClass(rank) {
    if (rank === 1) return 'rank-1';
    if (rank === 2) return 'rank-2';
    if (rank === 3) return 'rank-3';
    return '';
}

/* ──────────────── Статус ──────────────── */
const STATUS_ORDER = { active: 0, dnf: 1, dsq: 2, dns: 3 };
function sortByStatus(rows, timeKey) {
    return [...rows].sort((a, b) => {
        const sa = STATUS_ORDER[a.status] ?? 4, sb = STATUS_ORDER[b.status] ?? 4;
        if (sa !== sb) return sa - sb;
        if (a.status !== 'active') return 0;
        const ta = a[timeKey], tb = b[timeKey];
        if (ta == null && tb == null) return 0;
        if (ta == null) return 1;
        if (tb == null) return -1;
        return ta - tb;
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
        if (diff < 0)  return '<span class="badge badge-fin">Финишировал</span>';
        if (diff === 0) return '<span class="badge badge-dnf">DNF</span>';
        return '<span class="badge badge-dns">Не стартовал</span>';
    }
    // active
    const hasTime = stageKey ? r[stageKey + '_s'] != null : r.overall_s != null;
    return hasTime
        ? '<span class="badge badge-fin">Финишировал</span>'
        : '<span class="badge badge-live">В гонке</span>';
}
function relayMemberStatusBadge(m) {
    if (m.status === 'dnf') return '<span class="badge badge-dnf">DNF</span>';
    if (m.status === 'dns') return '<span class="badge badge-dns">Не стартовал</span>';
    if (m.status === 'dsq') return '<span class="badge badge-dsq">DSQ</span>';
    return '<span class="badge badge-fin">Финишировал</span>';
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

function currentStage(row) {
    // Последний этап (в порядке гонки), по которому есть хоть какие-то данные
    for (let i = STAGE_ORDER.length - 1; i >= 0; i--) {
        if (lastReached(row.cp, STAGE_ORDER[i])) return STAGE_ORDER[i];
    }
    return null;
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

// Аналог computeStageRanks, но в терминах "глобального прогресса гонки"
// (см. computeOverallGaps) — место среди тех, кто реально финишировал ВСЮ
// гонку. Нужно для "текущего места" на странице участника до финиша.
function computeOverallRanks(rows) {
    const withPos = rows.map(r => {
        const stage = currentStage(r);
        if (!stage) return null;
        const pos = lastReached(r.cp, stage);
        const value = globalProgress(r, stage, pos.seq);
        return value == null ? null : { key: r.key, stage, seq: pos.seq, value };
    }).filter(Boolean);
    const finishers = withPos
        .filter(r => r.stage === 'run' && r.seq === STAGE_MAX_SEQ.run)
        .sort((a, b) => a.value - b.value);
    const ranks = {};
    finishers.forEach((r, i) => {
        ranks[r.key] = (i > 0 && r.value === finishers[i - 1].value)
            ? ranks[finishers[i - 1].key]
            : i + 1;
    });
    return ranks;
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
