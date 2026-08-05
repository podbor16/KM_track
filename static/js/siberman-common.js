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
// Город участника — просто "Город" для россиян (country по умолчанию
// "Россия" на сервере, парсер/миграция), "Страна, Город" для иностранцев
// (запрошено пользователем 2026-08-03, п.3 v7). '', если города нет
// вовсе — вызывающий код сам решает, показывать ли пустую строку.
function cityLabel(r) {
    if (!r.city) return '';
    if (r.country && r.country !== 'Россия') return `${r.country}, ${r.city}`;
    return r.city;
}
// Бейдж "N предыдущих финишей Siberman" (звезда) — только личный зачёт
// (r.finish_count пишется сервером только для individual, см. db.py), и
// только если > 0 (новички звезду не получают). Общий для карточки
// участника и всех табов результатов (2026-08-05).
function finishStarBadge(r) {
    if (!(r.finish_count > 0)) return '';
    return `<span class="badge badge-star" title="Количество финишей Siberman до этого года"><img src="/static/images/siberman/star.png" alt="">${r.finish_count}</span>`;
}
/* ──────────────── Рекорды Siberman ────────────────
   siberman_records (не привязана к году) — 4 колонки (overall/swim/
   bike_total/run), до 5 категорий каждая. Кандидатом на ЛЮБОЙ рекорд
   может быть только тот, кто реально дошёл до конца ВСЕЙ гонки —
   проверяется и обновляется сервером (_update_records в service.py) на
   каждый apply; фронт только ОТОБРАЖАЕТ уже посчитанное состояние.
   Сопоставление "эта строка = держатель рекорда" — по нормализованному
   имени (surname+name), той же техникой, что и finishStarBadge/
   finish_counts — нет ID-связи с историческими рекордсменами, которых
   может не быть в текущем ростере года (2026-08-05). */
const RECORD_CATEGORY_LABEL = {
    absolute: 'Абсолют', male: 'М', female: 'Ж',
    male_individual: 'М (л)', female_individual: 'Ж (л)',
};
const RECORD_CATEGORIES = ['absolute', 'male', 'female', 'male_individual', 'female_individual'];
function buildRecordsIndex(records) {
    const idx = {};
    (records || []).forEach(r => { idx[`${r.column_key}:${r.category}`] = r; });
    return idx;
}
function _normPersonName(s) {
    return String(s ?? '').trim().toLowerCase().replace(/\s+/g, ' ');
}
// Категории, которые ИМЕННО ЭТА строка (личник или конкретный член
// эстафеты — у него личное имя, не название команды) держит на колонке
// columnKey ПРЯМО СЕЙЧАС.
function recordCategoriesFor(recordsIndex, columnKey, surname, name) {
    const key = _normPersonName(`${surname} ${name}`);
    if (!key) return [];
    return RECORD_CATEGORIES.filter(cat => {
        const rec = recordsIndex[`${columnKey}:${cat}`];
        return rec && _normPersonName(rec.holder_name) === key;
    });
}
function recordLabelText(cats) {
    return cats.map(c => RECORD_CATEGORY_LABEL[c] ?? c).join(', ');
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
// bib — VARCHAR в БД (относится и к личникам, и к эстафетным командам),
// без численного сравнения "10" оказался бы раньше "9" (лексикографически).
// Нужен как fallback-сортировка ДО того, как на срезе появилось хоть одно
// реальное время — до этого live-ключ (posSortKey/raceSortKey/_liveSortKey)
// у ВСЕХ участников null, и без явного тай-брейка порядок строк был бы
// "как пришло с сервера" — неопределённый для зрителя (запрошено
// пользователем 2026-08-05: "сортировка по возрастанию стартовых номеров"
// до первой реальной отметки на срезе, дальше — обычная сортировка по месту).
function bibCompare(a, b) {
    const na = parseInt(a, 10), nb = parseInt(b, 10);
    if (!isNaN(na) && !isNaN(nb) && na !== nb) return na - nb;
    return String(a).localeCompare(String(b));
}
function sortByStatus(rows, timeKey, progressFn) {
    return [...rows].sort((a, b) => {
        const sa = STATUS_ORDER[a.status] ?? 4, sb = STATUS_ORDER[b.status] ?? 4;
        if (sa !== sb) return sa - sb;
        const ta = a[timeKey], tb = b[timeKey];
        if (ta == null && tb == null) {
            if (a.status !== 'active' && progressFn) return progressFn(b) - progressFn(a);
            return bibCompare(a.bib, b.bib);
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
// "Плавание" через sortByStatus + statusBadge). keyFn(item) — ЗАКОДИРОВАННЫЙ
// ключ прогресса (posSortKey/raceSortKey), а не сырое .v напрямую — с
// новой live-моделью .v остаётся только для ОТОБРАЖЕНИЯ/расчёта отставания,
// сравнивать между участниками на разных КТ по нему нельзя (см. шапку
// файла, найдено 2026-08-03 на тестовом прогоне). keyFn сам решает, что
// возвращать null для DNF/DSQ без прогресса — единая точка сравнения вместо
// прежних отдельных .v и progressFn.
// bibFn(item) — по умолчанию читает entry.bib напрямую; переопределяется
// там, где bib эстафетчика лежит в другом поле (_bib, а не entry.bib —
// см. renderStage()/relayMembers, где entry — сырой объект члена команды,
// не команда целиком).
function sortByRawStatus(items, keyFn, bibFn = item => item.entry?.bib) {
    return [...items].sort((a, b) => {
        const aActive = a.rawStatus === 'active', bActive = b.rawStatus === 'active';
        if (aActive !== bActive) return aActive ? -1 : 1;
        const ka = keyFn(a), kb = keyFn(b);
        if (ka == null && kb == null) return bibCompare(bibFn(a), bibFn(b));
        if (ka == null) return 1;
        if (kb == null) return -1;
        return ka - kb;
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
// Статус УЧАСТНИКА ОТНОСИТЕЛЬНО КОНКРЕТНОГО ЭТАПА (stageKey) — не общий
// статус всей гонки. DNF засчитывается на этапе, где произошёл сход, И на
// ВСЕХ последующих (сошедший на вело-1 — dnf на вело-2/бег тоже, а не
// "не стартовал": сход необратим, участник больше не вернётся в гонку);
// если сошёл РАНЬШЕ этого этапа — этот этап он успешно финишировал
// ("active"). "Не стартовал" (dns) — статус только ДО старта гонки/этапа/
// дня, никогда не после DNF (2026-08-04, найдено пользователем: "не
// стартовал" на вело-2/беге у участника, сошедшего на вело-1, вводило в
// заблуждение — он не "ещё не начал", он уже сошёл). dns/dsq/active не
// зависят от этапа, возвращаются как есть (настоящий dns — участник,
// реально не стартовавший всю гонку, из исходных данных).
// Используется и в statusBadge() (бейдж строки), и в buildStats()
// (карточка индикаторов) — раньше индикаторы считали DNF по статусу ВСЕЙ
// гонки одинаково на КАЖДОЙ вкладке (2026-08-03, п.1 v7, найдено
// пользователем на реальном использовании).
function stageRelativeStatus(r, stageKey) {
    if (r.status !== 'dnf' || stageKey === null) return r.status;
    const dnfStage = getDnfStage(r);
    const diff = STAGE_ORD[stageKey] - STAGE_ORD[dnfStage];
    return diff < 0 ? 'active' : 'dnf';
}
// Бейдж для АКТИВНОГО (не dnf/dsq/dns) участника на конкретном СРЕЗЕ
// (этап/гонка/день/Свод вело) — три состояния в зависимости от прогресса
// именно на этом срезе: ещё не начал (ни одной КТ среза) → "—" (не
// "На трассе" — раньше не различали "ещё не стартовал" и "уже в
// процессе", 2026-08-03, запрошено пользователем); начал, но не дошёл до
// конца среза → "На трассе"; дошёл до последней КТ среза → "Финиш".
// pos — {seq,...}-подобный объект (или null) для ЭТОГО среза (например,
// lastReached(cp, dbStage) для этапа, racePos(row, maxStage) для гонки/
// дня, bikeCombinedLastPos(row) для Свода вело) — null означает "ещё не
// начал". isFinished(pos) — предикат "это и есть последняя КТ среза".
// started — участник уже вошёл в этот срез, даже если ЕЩЁ НЕ дошёл до
// первой КТ (иначе "—" держится до первой КТ этапа, хотя человек уже
// реально в пути — заметный разрыв на "Вело День 1"/"Бег", найдено
// пользователем 2026-08-04). См. stageHasStarted().
function activeProgressBadge(pos, isFinished, started) {
    if (pos && isFinished(pos)) return '<span class="badge badge-fin">Финиш</span>';
    if (pos || started) return '<span class="badge badge-live">На трассе</span>';
    return '<span class="badge badge-notstarted">—</span>';
}
function statusBadge(r, stageKey, started) {
    const s = stageRelativeStatus(r, stageKey);
    if (s === 'dns') return '<span class="badge badge-dns">Не стартовал</span>';
    if (s === 'dsq') return '<span class="badge badge-dsq">DSQ</span>';
    if (s === 'dnf') return '<span class="badge badge-dnf">DNF</span>';
    // active
    if (stageKey === null) {
        const pos = racePos(r, null);
        return activeProgressBadge(pos, p => p.stageIdx === STAGE_ORDER.indexOf('run') && p.seq === STAGE_MAX_SEQ.run);
    }
    const dbStage = TAB_TO_DB_STAGE[stageKey];
    return activeProgressBadge(lastReached(r.cp, dbStage), p => p.seq === STAGE_MAX_SEQ[dbStage], started);
}
function relayMemberStatusBadge(m, pos, maxSeq, started) {
    if (m.status === 'dnf') return '<span class="badge badge-dnf">DNF</span>';
    if (m.status === 'dns') return '<span class="badge badge-dns">Не стартовал</span>';
    if (m.status === 'dsq') return '<span class="badge badge-dsq">DSQ</span>';
    return activeProgressBadge(pos, p => p.seq === maxSeq, started);
}
// Статус ЭСТАФЕТНОЙ КОМАНДЫ целиком (не отдельного участника) — тот же
// бейдж, что уже был у личников (statusBadge), но команда не несёт своего
// "status" в API — используем упрощённый teamGapRow().status (dnf любого
// члена → dnf команды) + реальную позицию в гонке (racePos), НЕ
// team.overall_s (это просто сумма любых уже готовых времён трёх разных
// членов команды, растёт с первого же законченного участка — становится
// ненулевым задолго до реального финиша всей команды, см. 2026-08-03).
function teamStatusBadge(team) {
    const tr = teamGapRow(team);
    if (tr.status === 'dnf') return '<span class="badge badge-dnf">DNF</span>';
    if (tr.status !== 'active') return '<span class="badge badge-live">На трассе</span>';
    return activeProgressBadge(racePos(tr, null), p => p.stageIdx === STAGE_ORDER.indexOf('run') && p.seq === STAGE_MAX_SEQ.run);
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

// Субметки бега "-500м до круга" (Copernico live, задача 6 Live v2, seq
// 101..112 — см. миграцию 009). ВНЕ диапазона 1..STAGE_MAX_SEQ.run,
// поэтому невидимы для lastReached()/currentStage()/finish-детекции по
// конструкции (те функции идут только 1..STAGE_MAX_SEQ) — участвуют
// ТОЛЬКО в колонке "Последняя отметка" через lastReachedIncludingSubmarks().
const RUN_SUBMARK_SEQS = Array.from({ length: 12 }, (_, i) => 100 + i + 1);
for (const seq of RUN_SUBMARK_SEQS) {
    CHECKPOINT_DIST_KM.run[seq] = (seq - 100) * 7 - 0.5;
}

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
// Полная дистанция гонки (км) — конец последнего этапа (Бег).
const RACE_TOTAL_KM = STAGE_KM_OFFSET.run + CHECKPOINT_DIST_KM.run[STAGE_MAX_SEQ.run];

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
// На финише второй строкой всегда "Финиш", независимо от этапа. Формат
// одинаковый везде, включая "Дни" — без названия этапа (запрошено
// пользователем 2026-08-02, идентично вкладкам этапов).
function lastCpTwoLineHtml(dbStage, seq) {
    if (seq == null) return '—';
    const km = CHECKPOINT_DIST_KM[dbStage][seq];
    const kmLine = `<div>${String(km).replace('.', ',')} км</div>`;
    if (seq === STAGE_MAX_SEQ[dbStage]) return kmLine + '<div class="muted-sub">Финиш</div>';
    if (dbStage === 'run' && seq > 100) {
        // Субметка "-500м до круга" — seq не равен реальному номеру круга.
        const lap = seq - 100;
        return kmLine + `<div class="muted-sub">${lap} ${_circleWord(lap)} (-500м)</div>`;
    }
    const lapN = dbStage === 'swim' ? SWIM_LAP_SEQS[seq] : dbStage === 'run' ? seq : null;
    return lapN ? kmLine + `<div class="muted-sub">${lapN} ${_circleWord(lapN)}</div>` : kmLine;
}

// Как lastCpTwoLineHtml, но км — НАКОПЛЕННЫЕ по всей гонке (+ STAGE_KM_OFFSET),
// а не в рамках текущего этапа — нужно на "Днях" (Итог 1/2 дня), где
// "Отметка" должна отражать прогресс к границе ДНЯ (155/431 км), а не
// заново с нуля на каждом этапе внутри дня (найдено пользователем
// 2026-08-04: на "Итог 2 дней" показывалось "51 км" вместо "206 км" =
// 155 (день 1 целиком) + 51 (прогресс на вело-дне-2 к этой КТ)).
function cumulativeLastCpHtml(dbStage, seq) {
    if (seq == null) return '—';
    const km = STAGE_KM_OFFSET[dbStage] + CHECKPOINT_DIST_KM[dbStage][seq];
    const kmLine = `<div>${String(km).replace('.', ',')} км</div>`;
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

// Как lastReached(), но для 'run' дополнительно учитывает субметки "-500м
// до круга" (Copernico, seq 101..112) — выбор ПО РАССТОЯНИЮ, а не по seq
// (субметки идут "вперемешку" с круговыми хронологически, а не после них
// по номеру). Используется ТОЛЬКО в колонке "Последняя отметка" на
// вкладке "Бег" — везде остальном (ранги/статус/currentStage/finish) —
// как и раньше, lastReached() без субметок.
function lastReachedIncludingSubmarks(cp, stage) {
    if (stage !== 'run') return lastReached(cp, stage);
    if (!cp || !cp[stage]) return null;
    let best = null;
    for (const seq of [...Array.from({ length: STAGE_MAX_SEQ.run }, (_, i) => i + 1), ...RUN_SUBMARK_SEQS]) {
        const v = cp[stage][seq];
        if (v == null) continue;
        const km = CHECKPOINT_DIST_KM.run[seq];
        if (best == null || km > best.km) best = { seq, value: v, km };
    }
    return best ? { seq: best.seq, value: best.value } : null;
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
// роль). Статус проверяем — чтобы явно дисквалифицированный/DNF не мог стать
// лидером, даже дойдя до финиша. Gap при этом считается для всех, включая
// недошедших — от той же КТ, которую они последней прошли.
function computeStageGaps(rows, dbStage) {
    // rows: [{key, cp, swim_s, status}] — swim_s нужен только для
    // dbStage==='bike_day1' (см. stagePos/stageAdjustedValue).
    const withPos = rows
        .map(r => ({ key: r.key, cp: r.cp, swim_s: r.swim_s, status: r.status ?? 'active', pos: stagePos(r, dbStage) }))
        .filter(r => r.pos);
    if (withPos.length === 0) return {};
    // Лидер — участник, дальше всех продвинувшийся по этапу ПРЯМО СЕЙЧАС
    // (posSortKey — дальше КТ всегда впереди), а не обязательно тот, кто
    // уже дошёл до финиша этапа — иначе отставание оставалось бы пустым
    // {} всю гонку, пока хоть кто-то не финиширует (найдено 2026-08-03 на
    // тестовом прогоне живых данных). DNF/DSQ по-прежнему не может быть
    // лидером (см. status-фильтр ниже).
    const candidates = withPos.filter(r => r.status === 'active');
    if (candidates.length === 0) return {};
    const leader = candidates.reduce((a, b) => (posSortKey(a.pos) <= posSortKey(b.pos) ? a : b));
    const gaps = {};
    withPos.forEach(r => {
        if (r.key === leader.key) { gaps[r.key] = 0; return; }
        const leaderVal = stageAdjustedValue(leader, dbStage, valueAtOrBefore(leader.cp, dbStage, r.pos.seq));
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
// финальной позиции"). gap===0 у лидера точки. stageAdjustedValue —
// та же поправка на заплыв для bike_day1, что и в computeStageGaps/
// stagePos (rows должны нести swim_s) — иначе "на этапе" для Вело 1
// сравнивало бы сырое время от старта гонки (найдено пользователем
// 2026-08-04, тот же класс бага на графике "Позиция" и в постах трансляции).
function computeCheckpointGaps(rows, dbStage, maxSeq) {
    return _checkpointGapsByValueFn(rows, (r, seq) => stageAdjustedValue(r, dbStage, r.cp?.[dbStage]?.[seq]), maxSeq);
}
function computeCheckpointRanks(rows, dbStage, maxSeq) {
    return _checkpointRanksByValueFn(rows, (r, seq) => stageAdjustedValue(r, dbStage, r.cp?.[dbStage]?.[seq]), maxSeq);
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
    if (vseq <= n1) {
        const v1 = row.cp?.bike_day1?.[vseq];
        // cp.bike_day1 — elapsed ОТ СТАРТА ГОНКИ (включает заплыв, см.
        // convert_bike_times_to_elapsed в src/siberman/service.py) —
        // "объединённое вело" 0..421 км должно быть БЕЗ заплыва, та же
        // база, что и у bike1_s (bike1_abs - swim). Раньше день1 (эта
        // ветка) и день2 (ветка ниже, явно без заплыва через bike1_s)
        // считались в разных базах — нашли при переходе на live-время
        // Свода вело (2026-08-03).
        return v1 == null ? v1 : v1 - (row.swim_s ?? 0);
    }
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

// Позиция на ОБЪЕДИНЁННОМ вело (день1+день2 как один этап 0..421 км) —
// {seq: виртуальный seq, value: elapsed с начала вело, БЕЗ заплыва} —
// нужна для live-времени/ранга/отставания Свода вело (2026-08-03,
// раньше требовалось ПОЛНОСТЬЮ пройти оба дня — см. bikeCombinedTime,
// удалена в этом плане). Аналог lastReached() для обычного этапа, но
// через сквозную виртуальную нумерацию КТ.
function bikeCombinedLastPos(row) {
    const vseq = bikeCombinedLastSeq(row.cp);
    if (vseq == null) return null;
    const value = bikeCombinedRawCp(row, vseq);
    return value == null ? null : { seq: vseq, value };
}

// Аналог valueAtOrBefore(), но через виртуальную нумерацию КТ Свода вело —
// нужен bikeCombinedGaps(): лидер, уже уехавший вперёд, обычно НЕ имеет
// сырого значения ТОЧНО на виртуальной КТ отстающего (например, лидер
// давно в Дне 2, а из Дня 1 в его данных сохранён только финиш дня, а не
// каждая промежуточная КТ) — нужно взять его последнее известное значение
// НЕ ПОЗЖЕ этой виртуальной КТ, как это делает valueAtOrBefore для
// обычного этапа в computeStageGaps. Если раньше этой КТ вообще нет
// данных — значение лидера на этой точке неизвестно (не 0 — это было бы
// заниженной оценкой и завысило бы итоговое отставание, поскольку
// bikeCombinedGaps считает gap = follower.value - leaderVal); возвращаем
// null, и вызывающая сторона (как и computeStageGaps) просто пропускает
// отставание для этой записи, а не показывает фиктивное число.
function _bikeCombinedValueAtOrBefore(entry, vseq) {
    for (let s = vseq; s >= 1; s--) {
        const v = bikeCombinedRawCp(entry, s);
        if (v != null) return v;
    }
    return null;
}

// Отставание на Своде вело — та же модель, что computeStageGaps (лидер =
// дальше всех продвинувшийся ПРЯМО СЕЙЧАС, не обязательно финишировавший
// весь Свод вело), но через виртуальные КТ bikeCombinedRawCp/
// bikeCombinedLastPos, а не прямой cp[stage][seq]. rows: [{key, entry,
// status}] — entry несёт cp/swim_s/bike1_s, как ожидает bikeCombinedRawCp.
function bikeCombinedGaps(rows) {
    const withPos = rows
        .map(r => ({ key: r.key, entry: r.entry, status: r.status ?? 'active', pos: bikeCombinedLastPos(r.entry) }))
        .filter(r => r.pos);
    if (withPos.length === 0) return {};
    const candidates = withPos.filter(r => r.status === 'active');
    if (candidates.length === 0) return {};
    const leader = candidates.reduce((a, b) => (posSortKey(a.pos) <= posSortKey(b.pos) ? a : b));
    const gaps = {};
    withPos.forEach(r => {
        if (r.key === leader.key) { gaps[r.key] = 0; return; }
        const leaderVal = _bikeCombinedValueAtOrBefore(leader.entry, r.pos.seq);
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

// Кодирует "положение" {seq, value} (номер КТ + накопленное время НА
// НЕЙ) в ОДНО число, пригодное для обычного числового сравнения a-b —
// используется везде, где раньше сравнивали "сырое" время напрямую
// (найдено 2026-08-03 на тестовом прогоне 2025 данных: участник, только
// что стартовавший этап, имеет МЕНЬШЕЕ накопленное время, чем тот, кто
// прошёл намного дальше — прямое сравнение ставило его "впереди").
// COEF заведомо больше любого реалистичного числа секунд в гонке (515 км,
// самый медленный участник — не больше нескольких суток = максимум
// десятки тысяч секунд), поэтому разряд КТ никогда не "перетекает" в
// разряд времени. Минус у seq — чтобы БОЛЬШАЯ КТ (дальше по дистанции)
// давала МЕНЬШИЙ ключ (сортируется раньше при обычном возрастающем
// сравнении). Вырождается в обычное сравнение по времени, когда оба
// участника на одной КТ (в т.ч. оба финишировали — seq одинаковый максимум).
const _POS_SORT_COEF = 1e7;
function posSortKey(pos) {
    return pos ? -pos.seq * _POS_SORT_COEF + pos.value : null;
}

// cp.bike_day1 хранит elapsed ОТ СТАРТА ГОНКИ (включает заплыв, см.
// convert_bike_times_to_elapsed) — для сравнения "внутри вело-дня-1"
// (сортировка/место/отставание/скорость на вкладке "Вело День 1") нужно
// сетевое время БЕЗ заплыва, та же база, что и у серверного bike1_s
// (bike1_abs - swim, compute_stage_totals) и уже используется для
// "объединённого вело" в bikeCombinedRawCp. Раньше вкладка "Вело День 1"
// сравнивала сырые (не сетевые) значения — участник с быстрым заплывом
// получал заниженную позицию/скорость на вело, даже опережая по факту
// (найдено пользователем 2026-08-04).
function stageAdjustedValue(row, dbStage, rawValue) {
    if (rawValue == null || dbStage !== 'bike_day1') return rawValue;
    return rawValue - (row.swim_s ?? 0);
}
function stagePos(row, dbStage) {
    const pos = lastReached(row.cp, dbStage);
    return pos ? { seq: pos.seq, value: stageAdjustedValue(row, dbStage, pos.value) } : null;
}

// bike2_start_s — секунды ОТ ПОЛУНОЧИ дня 2 (расчётный личный старт по
// рангу вело-дня-1, см. convert_bike_times_to_elapsed/BIKE_DAY2_BASE_START_S)
// — переводим в абсолютный epoch (мс) для сравнения с "сейчас". День 2 —
// календарные сутки СРАЗУ ПОСЛЕ дня старта гонки (двухдневная гонка).
function bike2StartEpoch(raceStartEpoch, bike2StartS) {
    if (raceStartEpoch == null || bike2StartS == null) return null;
    const day1 = new Date(raceStartEpoch);
    const day2Midnight = new Date(day1.getFullYear(), day1.getMonth(), day1.getDate() + 1).getTime();
    return day2Midnight + bike2StartS * 1000;
}

// Вошёл ли участник в этап, даже если ЕЩЁ НЕ дошёл до первой КТ этого
// этапа — иначе статус держится на "—" до первой КТ (например, 3 км
// вело-дня-1), хотя участник уже реально едет (найдено пользователем
// 2026-08-04). swim не входит сюда — масс-старт всей гонки, определяется
// отдельно (не запрошено сейчас). bike_day1/run — предыдущий этап РЕАЛЬНО
// завершён (последняя КТ, не просто "есть какое-то значение" — swim_s/
// bike2_s заполняются уже на первой достигнутой КТ, см. compute_stage_totals
// в service.py, а не только на финише). bike_day2 — у каждого участника
// свой личный расчётный старт (bike2_start_s) — "начал", когда живое время
// его прошло, вне зависимости от checkpoint-данных.
const STAGE_PRIOR_FINISH = { bike_day1: 'swim', run: 'bike_day2' };
function stageHasStarted(row, dbStage, raceStartEpoch, nowEpoch) {
    if (dbStage === 'bike_day2') {
        const epoch = bike2StartEpoch(raceStartEpoch, row.bike2_start_s);
        return epoch != null && nowEpoch != null && nowEpoch >= epoch;
    }
    const priorStage = STAGE_PRIOR_FINISH[dbStage];
    if (!priorStage) return false;
    const priorPos = lastReached(row.cp, priorStage);
    return !!(priorPos && priorPos.seq === STAGE_MAX_SEQ[priorStage]);
}

// Положение участника В ГОНКЕ (кросс-этапное) — в отличие от posSortKey
// одного этапа, здесь нужно сравнивать людей, которые могут быть на
// РАЗНЫХ этапах гонки ПРЯМО СЕЙЧАС (кто на вело всегда впереди того, кто
// ещё плывёт, независимо от "сырых" секунд). {stageIdx, seq, value}:
// stageIdx — индекс этапа в STAGE_ORDER, seq — КТ внутри него, value —
// накопленное время ГОНКИ на этой точке (globalProgress — уже сравнимо
// между этапами, но ТОЛЬКО как тай-брейк при равном stageIdx+seq, не
// само по себе — см. raceSortKey). maxStage — см. currentStage: ограничить
// "Днём" на вкладках "Дни". null, если участник ещё не начал ни одной КТ.
function racePos(row, maxStage) {
    const stage = currentStage(row, maxStage);
    if (!stage) return null;
    const pos = lastReached(row.cp, stage);
    return { stageIdx: STAGE_ORDER.indexOf(stage), seq: pos.seq, value: globalProgress(row, stage, pos.seq) };
}

// Как posSortKey, но для racePos() — сворачивает stageIdx в тот же
// разряд, что и seq (индекс этапа 0..3, КТ до ~12 — максимум
// stageIdx*100+seq = 312, тот же порядок величины, тот же COEF).
function raceSortKey(pos) {
    return pos ? posSortKey({ seq: pos.stageIdx * 100 + pos.seq, value: pos.value }) : null;
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

function computeOverallGaps(rows, maxStage) {
    const withPos = rows.map(r => {
        const stage = currentStage(r, maxStage);
        if (!stage) return null;
        // racePos() пересчитывает currentStage() ещё раз внутри себя — та же
        // дешёвая функция, дублирующий вызов не оптимизируется намеренно
        // (см. её комментарий); stage оставлен отдельной переменной, т.к.
        // racePos() не возвращает имя этапа, только его индекс.
        const pos = racePos(r, maxStage);
        return pos.value == null ? null : { key: r.key, cp: r.cp, row: r, status: r.status ?? 'active', stage, stageIdx: pos.stageIdx, seq: pos.seq, value: pos.value };
    }).filter(Boolean);
    if (withPos.length === 0) return {};
    // Лидер — участник, дальше всех продвинувшийся ПРЯМО СЕЙЧАС по всей
    // гонке (или по "Дню", если maxStage задан) — та же живая модель, что
    // и в computeStageGaps (2026-08-03): раньше "Отставание" в Итогах
    // гонки оставалось пустым {} всю гонку до первого финишера 515 км.
    const candidates = withPos.filter(r => r.status === 'active');
    if (candidates.length === 0) return {};
    // raceSortKey() читает только .stageIdx/.seq/.value — withPos-элементы
    // уже содержат их напрямую, пересборка отдельного объекта не нужна.
    const leader = candidates.reduce((a, b) => (raceSortKey(a) <= raceSortKey(b) ? a : b));
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
// {key, row, status}, где row — "виртуальный участник" (сырая строка
// личника или teamGapRow() команды), пригодный для racePos()/raceSortKey.
// Личники (rank_overall) и эстафета (считается на клиенте) раньше
// ранжировались раздельно — единого "абсолютного" места по всей гонке
// (личники+эстафета вместе) не было нигде. Эта пара функций его вводит.
function combinedOverallRankRows(individual, relay) {
    return [
        ...individual.map(r => ({ key: r.bib, row: r, status: r.status })),
        ...relay.map(t => ({ key: t.bib, row: teamGapRow(t), status: teamGapRow(t).status })),
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
// Единое место по всей гонке (или по "Дню", если maxStage задан) —
// личники+эстафета вместе, по ЖИВОЙ позиции в гонке (racePos/raceSortKey
// — дальше по маршруту всегда впереди, сравнимо и до, и после финиша).
// Раньше требовался overall_s — у личника null всю гонку до полного
// финиша всех 4 этапов сразу (2026-08-03: места не считались вообще, ни
// одного, пока никто не закончил гонку целиком).
function computeCombinedOverallRanks(rows, maxStage) {
    return computeRanksByValue(rows.map(r => ({ key: r.key, val: raceSortKey(racePos(r.row, maxStage)), status: r.status })));
}
