# Segments Bar Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить плоскую таблицу всех пар КТ в детальной панели участника на бар-чарт темпа + две компактные таблицы (последовательные отрезки / сплиты от старта).

**Architecture:** Чисто фронтенд — API не меняется. Функция `createSegmentsTable()` в `analytics-results.js` заменяется на `createSegmentsPanel()`. Км-позиции КТ вычисляются из сплитов (время ÷ темп). Цвет баров — линейная интерполяция зелёный→красный по индивидуальной шкале участника.

**Tech Stack:** Vanilla JavaScript, CSS, Jinja2 templates.

---

## File Map

| Файл | Изменение |
|------|-----------|
| `static/js/analytics-results.js` | Заменить `createSegmentsTable()` → `createSegmentsPanel()` + вспомогательные функции |
| `static/css/analytics.css` | Добавить стили для `.pace-chart`, `.pace-bar-col`, `.segment-section-header` |

---

### Task 1: CSS-стили для бар-чарта

**Files:**
- Modify: `static/css/analytics.css` (в конец файла, после существующих segment-стилей)

- [ ] **Step 1: Добавить стили в конец analytics.css**

Открыть `static/css/analytics.css`, найти конец файла и добавить:

```css
/* ── Pace bar chart ─────────────────────────────────────── */
.pace-chart {
    display: flex;
    align-items: flex-end;
    gap: 6px;
    padding: 14px 0 0;
    min-height: 140px;
}

.pace-bar-col {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    min-width: 0;
}

.pace-bar-col__top {
    text-align: center;
    font-size: 8px;
    line-height: 1.35;
    width: 100%;
}

.pace-bar-col__top-time {
    font-weight: bold;
}

.pace-bar-col__top-dist {
    color: #666;
}

.pace-bar-col__bar {
    width: 100%;
    border-radius: 3px 3px 0 0;
    flex-shrink: 0;
    transition: opacity 0.15s;
}

.pace-bar-col__pace {
    font-size: 8px;
    font-weight: bold;
    white-space: nowrap;
    text-align: center;
}

.pace-bar-col__range {
    font-size: 7px;
    color: #555;
    text-align: center;
    line-height: 1.3;
    white-space: nowrap;
}

.pace-chart-legend {
    font-size: 9px;
    color: #444;
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid #1e2a3e;
}

/* ── Segment section header ─────────────────────────────── */
.segment-section-header {
    padding: 5px 0 4px;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-top: 10px;
    border-bottom: 1px solid #2a2a3e;
}
```

- [ ] **Step 2: Проверить что CSS добавился без синтаксических ошибок**

Открыть в браузере DevTools → Console. Убедиться что нет ошибок типа "Unexpected token" в analytics.css.

- [ ] **Step 3: Commit**

```bash
git add static/css/analytics.css
git commit -m "style: add pace-chart and segment-section-header CSS"
```

---

### Task 2: Вспомогательные функции (парсинг, км-карта, цвет)

**Files:**
- Modify: `static/js/analytics-results.js` — добавить 3 функции перед `createSegmentsTable()` (строка ~866)

- [ ] **Step 1: Добавить `parseSegmentCode`, `buildKmMap`, `paceBarColor` перед `createSegmentsTable`**

Найти строку `function createSegmentsTable(segments)` (~строка 866) и вставить перед ней:

```javascript
/**
 * Разбирает сегментный код "start-kt1" → {from: 'start', to: 'kt1'}
 */
function parseSegmentCode(code) {
    const idx = code.lastIndexOf('-');
    return { from: code.slice(0, idx), to: code.slice(idx + 1) };
}

/**
 * Строит карту { 'start': 0, 'kt1': 3.0, 'kt2': 5.3, ..., 'finish': 21.1 }
 * из сегментов с from='start'. Вычисляет to_km = time_sec / pace_sec_per_km.
 * Если данных нет — ключ отсутствует.
 */
function buildKmMap(segments) {
    const map = { start: 0 };
    for (const seg of segments) {
        const { from, to } = parseSegmentCode(seg.segment_code);
        if (from !== 'start') continue;
        const timeStr = seg.sg_time_clear || seg.sg_time_gun;
        const paceStr = seg.sg_pace_avg || seg.sg_pace_avg_gun;
        if (!timeStr || !paceStr) continue;

        // "HH:MM:SS" → seconds
        const tParts = timeStr.split(':').map(Number);
        const timeSec = tParts[0] * 3600 + tParts[1] * 60 + tParts[2];

        // "M:SS" → seconds/km
        const pParts = paceStr.split(':').map(Number);
        const paceSec = pParts[0] * 60 + pParts[1];

        if (paceSec > 0) {
            map[to] = Math.round((timeSec / paceSec) * 10) / 10;
        }
    }
    return map;
}

/**
 * Линейная интерполяция зелёный→красный по ratio [0..1].
 * ratio=0 → #4caf50 (быстрый), ratio=1 → #ef5350 (медленный).
 */
function paceBarColor(ratio) {
    const r = Math.round(76  + ratio * (239 - 76));
    const g = Math.round(175 + ratio * (83  - 175));
    const b = 80;
    return `rgb(${r},${g},${b})`;
}
```

- [ ] **Step 2: Проверить в консоли браузера**

После перезагрузки страницы `/results` выполнить в DevTools Console:

```javascript
parseSegmentCode('start-kt1')   // → {from:'start', to:'kt1'}
parseSegmentCode('kt3-finish')  // → {from:'kt3', to:'finish'}
paceBarColor(0)                 // → 'rgb(76,175,80)'
paceBarColor(1)                 // → 'rgb(239,83,80)'
paceBarColor(0.5)               // → 'rgb(157,129,80)'
```

Все три должны вернуть ожидаемые значения.

- [ ] **Step 3: Commit**

```bash
git add static/js/analytics-results.js
git commit -m "feat: add parseSegmentCode, buildKmMap, paceBarColor helpers"
```

---

### Task 3: Функции фильтрации сегментов

**Files:**
- Modify: `static/js/analytics-results.js` — добавить 2 функции после `paceBarColor`

- [ ] **Step 1: Добавить `filterConsecutiveSegments` и `filterSplitSegments`**

Сразу после `paceBarColor` добавить:

```javascript
/**
 * Возвращает последовательные отрезки: start→kt1, kt1→kt2, ..., ktN→finish.
 * Только сегменты с данными (sg_time_clear или sg_time_gun не null).
 * Результат отсортирован по порядку маршрута.
 */
function filterConsecutiveSegments(segments) {
    const KT_ORDER = ['start', 'kt1', 'kt2', 'kt3', 'kt4', 'kt5', 'kt6', 'kt7', 'finish'];
    return segments.filter(seg => {
        const { from, to } = parseSegmentCode(seg.segment_code);
        const fi = KT_ORDER.indexOf(from);
        const ti = KT_ORDER.indexOf(to);
        const isConsecutive = fi >= 0 && ti === fi + 1;
        const hasData = seg.sg_time_clear || seg.sg_time_gun;
        return isConsecutive && hasData;
    }).sort((a, b) => {
        const ai = KT_ORDER.indexOf(parseSegmentCode(a.segment_code).from);
        const bi = KT_ORDER.indexOf(parseSegmentCode(b.segment_code).from);
        return ai - bi;
    });
}

/**
 * Возвращает сплиты от старта: start→kt1, start→kt2, ..., start→finish.
 * Только сегменты с данными. Отсортированы по to_km (по to в KT_ORDER).
 */
function filterSplitSegments(segments) {
    const KT_ORDER = ['start', 'kt1', 'kt2', 'kt3', 'kt4', 'kt5', 'kt6', 'kt7', 'finish'];
    return segments.filter(seg => {
        const { from } = parseSegmentCode(seg.segment_code);
        const hasData = seg.sg_time_clear || seg.sg_time_gun;
        return from === 'start' && hasData;
    }).sort((a, b) => {
        const ai = KT_ORDER.indexOf(parseSegmentCode(a.segment_code).to);
        const bi = KT_ORDER.indexOf(parseSegmentCode(b.segment_code).to);
        return ai - bi;
    });
}
```

- [ ] **Step 2: Проверить в консоли**

Открыть любой участник с КТ в детальной панели (кликнуть на строку в `/results`), дождаться загрузки сегментов. Затем в консоли:

```javascript
// Fetch segments для любого result_id (взять из URL или Network вкладки)
fetch('/api/result-segments?result_id=1').then(r=>r.json()).then(segs => {
    console.log('consecutive:', filterConsecutiveSegments(segs).map(s=>s.segment_code));
    console.log('splits:', filterSplitSegments(segs).map(s=>s.segment_code));
});
```

Ожидаемый вывод для полумарафона:
```
consecutive: ['start-kt1','kt1-kt2','kt2-kt3','kt3-kt4','kt4-kt5','kt5-kt6','kt6-kt7','kt7-finish']
splits: ['start-kt1','start-kt2','start-kt3','start-kt4','start-kt5','start-kt6','start-kt7','start-finish']
```

- [ ] **Step 3: Commit**

```bash
git add static/js/analytics-results.js
git commit -m "feat: add filterConsecutiveSegments, filterSplitSegments"
```

---

### Task 4: Функция renderPaceChart

**Files:**
- Modify: `static/js/analytics-results.js` — добавить после `filterSplitSegments`

- [ ] **Step 1: Добавить `renderPaceChart`**

```javascript
/**
 * Рендерит бар-чарт темпа по последовательным отрезкам.
 * Цвет и высота — относительная шкала per-participant.
 * @param {Array} consecutive — результат filterConsecutiveSegments()
 * @param {Object} kmMap — результат buildKmMap()
 * @returns {HTMLElement|null} — контейнер чарта или null если нечего показать
 */
function renderPaceChart(consecutive, kmMap) {
    if (!consecutive.length) return null;

    const useGun = timeMode === 'gun';

    // Вычислить темп в секундах/км для каждого отрезка
    const paces = consecutive.map(seg => {
        const paceStr = useGun
            ? (seg.sg_pace_avg_gun || seg.sg_pace_avg)
            : seg.sg_pace_avg;
        if (!paceStr) return null;
        const parts = paceStr.split(':').map(Number);
        return parts[0] * 60 + parts[1]; // seconds/km
    });

    const validPaces = paces.filter(p => p !== null);
    if (!validPaces.length) return null;

    const minPace = Math.min(...validPaces);
    const maxPace = Math.max(...validPaces);
    const MIN_H = 14, MAX_H = 68;

    const chart = document.createElement('div');
    chart.className = 'pace-chart';

    consecutive.forEach((seg, i) => {
        if (paces[i] === null) return;

        const pace = paces[i];
        const ratio = maxPace === minPace ? 0 : (pace - minPace) / (maxPace - minPace);
        const color = paceBarColor(ratio);
        const height = Math.round(MIN_H + ratio * (MAX_H - MIN_H));

        // Время прохождения
        const timeStr = useGun
            ? (seg.sg_time_gun || seg.sg_time_clear)
            : seg.sg_time_clear;
        const timeDisplay = formatTime(timeStr) || '—';

        // Темп строкой
        const paceDisplay = useGun
            ? (seg.sg_pace_avg_gun || seg.sg_pace_avg || '—')
            : (seg.sg_pace_avg || '—');

        // Км-диапазон
        const { from, to } = parseSegmentCode(seg.segment_code);
        const fromKm = kmMap[from] !== undefined ? kmMap[from] : null;
        const toKm   = kmMap[to]   !== undefined ? kmMap[to]   : null;
        const distLabel = (fromKm !== null && toKm !== null)
            ? `${fromKm}–${toKm} км`
            : seg.segment_code;

        // Дистанция участка над баром
        const segKm = (fromKm !== null && toKm !== null)
            ? `${Math.round((toKm - fromKm) * 10) / 10} км`
            : '';

        const col = document.createElement('div');
        col.className = 'pace-bar-col';
        col.innerHTML = `
            <div class="pace-bar-col__top">
                <div class="pace-bar-col__top-time" style="color:${color}">${timeDisplay}</div>
                <div class="pace-bar-col__top-dist">${segKm}</div>
            </div>
            <div class="pace-bar-col__bar" style="background:${color};height:${height}px"></div>
            <div class="pace-bar-col__pace" style="color:${color}">${paceDisplay} мин/км</div>
            <div class="pace-bar-col__range">${distLabel}</div>
        `;
        chart.appendChild(col);
    });

    const wrapper = document.createElement('div');
    wrapper.appendChild(chart);

    const legend = document.createElement('div');
    legend.className = 'pace-chart-legend';
    legend.textContent = 'Зелёный = быстрый отрезок · Красный = медленный · Шкала индивидуальная';
    wrapper.appendChild(legend);

    return wrapper;
}
```

- [ ] **Step 2: Проверить в консоли**

```javascript
fetch('/api/result-segments?result_id=1').then(r=>r.json()).then(segs => {
    const cons = filterConsecutiveSegments(segs);
    const km = buildKmMap(segs);
    const chart = renderPaceChart(cons, km);
    console.log('chart element:', chart);
    console.log('bars count:', chart ? chart.querySelectorAll('.pace-bar-col').length : 0);
});
```

Должен вернуть элемент с числом баров = числу последовательных отрезков с данными.

- [ ] **Step 3: Commit**

```bash
git add static/js/analytics-results.js
git commit -m "feat: add renderPaceChart with relative per-participant color scale"
```

---

### Task 5: Заменить createSegmentsTable на createSegmentsPanel

**Files:**
- Modify: `static/js/analytics-results.js` — заменить `createSegmentsTable()` (~строка 866), обновить вызов в `loadSegmentsIntoPanel()` (~строка 824)

- [ ] **Step 1: Заменить тело `createSegmentsTable` на `createSegmentsPanel`**

Найти `function createSegmentsTable(segments)` (строки 866–929) и **заменить всю функцию целиком** на:

```javascript
function createSegmentsPanel(segments) {
    const useGun = timeMode === 'gun';
    const modeLabel = useGun ? 'офиц.' : 'чист.';

    const consecutive = filterConsecutiveSegments(segments);
    const splits      = filterSplitSegments(segments);
    const kmMap       = buildKmMap(segments);

    const panel = document.createElement('div');

    // 1. Бар-чарт (только если есть последовательные отрезки)
    const chart = renderPaceChart(consecutive, kmMap);
    if (chart) panel.appendChild(chart);

    // Хелпер: рендер одной секции таблицы
    function renderSection(title, color, rows) {
        if (!rows.length) return;

        const header = document.createElement('div');
        header.className = 'segment-section-header';
        header.style.color = color;
        header.textContent = title;
        panel.appendChild(header);

        const table = document.createElement('table');
        table.classList.add('segments-table');
        table.innerHTML = `
            <colgroup>
                <col width="30%"/><col width="18%"/><col width="24%"/>
                <col width="9%"/><col width="9%"/><col width="9%"/>
            </colgroup>
            <thead>
                <tr>
                    <th>Участок</th>
                    <th>Время <span class="seg-mode-label">${modeLabel}</span></th>
                    <th>Темп</th>
                    <th title="Место абсолют">Абс.</th>
                    <th title="Место по полу">Пол</th>
                    <th title="Место в категории">Кат.</th>
                </tr>
            </thead>
        `;

        const tbody = document.createElement('tbody');
        rows.forEach((segment, i) => {
            const prevSegment = i > 0 ? rows[i - 1] : null;
            const code = segment.segment_code || '-';
            const time = formatTime(useGun ? (segment.sg_time_gun || segment.sg_time_clear) : segment.sg_time_clear) || '-';
            const pace = formatSegmentPace(useGun ? (segment.sg_pace_avg_gun || segment.sg_pace_avg) : segment.sg_pace_avg);
            const rankAbsolute = useGun ? (segment.sg_rank_absolute_gun || segment.sg_rank_absolute || '-') : (segment.sg_rank_absolute || '-');
            const rankSex      = useGun ? (segment.sg_rank_sex_gun      || segment.sg_rank_sex      || '-') : (segment.sg_rank_sex      || '-');
            const rankCategory = useGun ? (segment.sg_rank_category_gun || segment.sg_rank_category || '-') : (segment.sg_rank_category || '-');

            let paceHtml = pace;
            if (prevSegment) {
                const prevPace = formatSegmentPace(useGun ? (prevSegment.sg_pace_avg_gun || prevSegment.sg_pace_avg) : prevSegment.sg_pace_avg);
                const cmp = compareSegments(pace, prevPace);
                if (cmp) {
                    const clr = cmp.improved ? '#27ae60' : '#e74c3c';
                    paceHtml += ` <span style="color:${clr};font-size:0.85em">${cmp.direction}${cmp.percent}%</span>`;
                }
            }

            const rankBadge = (rank) => {
                const clr = getRankColor(rank);
                return `<span class="seg-rank-badge" style="background:${clr}">${rank}</span>`;
            };

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="seg-name">${formatSegmentName(code)}</td>
                <td class="seg-time">${time}</td>
                <td class="seg-pace">${paceHtml}</td>
                <td class="seg-rank">${rankBadge(rankAbsolute)}</td>
                <td class="seg-rank">${rankBadge(rankSex)}</td>
                <td class="seg-rank">${rankBadge(rankCategory)}</td>
            `;
            tbody.appendChild(tr);
        });

        table.appendChild(tbody);
        panel.appendChild(table);
    }

    renderSection('Отрезки', '#e63946', consecutive);
    renderSection('Сплиты от старта', '#4a9eff', splits);

    // Если нет ни отрезков, ни сплитов — показать весь список как раньше
    if (!consecutive.length && !splits.length) {
        const fallback = document.createElement('div');
        fallback.style.cssText = 'color:#aaa;font-size:13px;padding:8px 0';
        fallback.textContent = 'Данные КТ не найдены';
        panel.appendChild(fallback);
    }

    return panel;
}
```

- [ ] **Step 2: Обновить вызов в `loadSegmentsIntoPanel`**

Найти строку (~824):
```javascript
cell.appendChild(createSegmentsTable(segments));
```
Заменить на:
```javascript
cell.appendChild(createSegmentsPanel(segments));
```

- [ ] **Step 3: Commit**

```bash
git add static/js/analytics-results.js
git commit -m "feat: replace createSegmentsTable with createSegmentsPanel + pace chart"
```

---

### Task 6: Ручная верификация

- [ ] **Step 1: Запустить сервер**

```bash
cd c:\Users\podbo\Работа\КРАСМАРАФОН\KM_track
python -m uvicorn src.main:app --reload --port 8000
```

- [ ] **Step 2: Проверить полумарафон (много КТ)**

1. Открыть `http://localhost:8000/results`
2. Выбрать Первомайский 2026, 21.1 км
3. Кликнуть на участника с данными КТ (не DNS/DNF)
4. В детальной панели убедиться:
   - Бар-чарт отображается: 8 баров (start→kt1 ... kt7→finish)
   - Над каждым баром: время прохождения + дистанция участка
   - Под каждым баром: темп с "мин/км" + км-диапазон ("0–3 км" и т.п.)
   - Самый медленный бар — красный, самый быстрый — зелёный
   - Заголовок "ОТРЕЗКИ" красным, 8 строк в таблице
   - Заголовок "СПЛИТЫ ОТ СТАРТА" синим, 8 строк

- [ ] **Step 3: Проверить Весну (1 КТ)**

1. Переключить на Весна 2026, 5 км
2. Кликнуть участника с данными
3. Убедиться: бар-чарт из 2 баров (start→kt1, kt1→finish), обе таблицы корректны

- [ ] **Step 4: Проверить граничный случай — нет данных КТ**

1. Кликнуть участника со статусом DNS или без КТ-данных
2. Детальная панель должна показать "Данные КТ не найдены" без ошибок в консоли

- [ ] **Step 5: Проверить DevTools Console**

F12 → Console: **0 ошибок**. Предупреждения допустимы.

- [ ] **Step 6: Финальный commit если нужны мелкие фиксы**

```bash
git add static/js/analytics-results.js static/css/analytics.css
git commit -m "fix: segment panel visual adjustments after manual review"
```
