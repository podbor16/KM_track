# Mobile Results Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the detail panel's fixed-width stat tablets + monolithic chart section with a tab interface (Результат / Темп / Отрезки) so no content overflows the viewport on mobile.

**Architecture:** Two files only. `buildDetailPanelHTML` generates a universal tab structure; CSS hides tab buttons on desktop and shows all panes, while on mobile only the active pane is visible. `loadSegmentsIntoPanel` is rewritten to fill the `pace` and `segments` panes separately. `createSegmentsPanel` is deleted; its inner `renderSection` is extracted as a module-level `renderSegmentSection` function.

**Tech Stack:** Vanilla JS, CSS, existing FastAPI backend (untouched).

---

## File Map

| File | Lines | Change |
|------|-------|--------|
| `static/css/analytics.css` | 339–358 | Remove dead tablet styles; add tab + result styles |
| `static/css/analytics.css` | 1253–1256 | Remove `html, body { overflow-x: hidden }` |
| `static/css/analytics.css` | 1475–1498 | Remove tablet compact rules; replace chart rules |
| `static/js/analytics-results.js` | 779–803 | Replace `buildDetailPanelHTML` return with tab HTML |
| `static/js/analytics-results.js` | 67 | Add tab-switching listener after DOMContentLoaded |
| `static/js/analytics-results.js` | 809–824 | Rewrite `loadSegmentsIntoPanel` |
| `static/js/analytics-results.js` | 1079–1175 | Delete `createSegmentsPanel`; extract `renderSegmentSection` |

---

### Task 1: CSS — replace dead tablet styles, add tabs, fix mobile chart

**Files:**
- Modify: `static/css/analytics.css`

**Context:** Lines 339–358 contain the `detail-stats-grid` + `detail-stat-tablet*` + `detail-segments-title` + `detail-segments-loading` rules added in the previous sprint — these are now dead code. The `row-active` rule at line 359 must be kept. The detail panel background is `#f5f5f5` (light), so text colours must be dark.

- [ ] **Step 1: Replace lines 339–358 with tab + result styles**

In `static/css/analytics.css`, find this block (lines 339–358):

```css
.detail-stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }

.detail-stat-tablet { background: white; border-radius: 8px; padding: 10px 12px; text-align: center; }
.detail-stat-tablet--gun { border-top: 3px solid var(--primary-color); }
.detail-stat-tablet--net { border-top: 3px solid #4a9eff; }

.detail-stat-tablet__label { font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.detail-stat-tablet--gun .detail-stat-tablet__label { color: var(--primary-color); }
.detail-stat-tablet--net .detail-stat-tablet__label { color: #4a9eff; }

.detail-stat-tablet__time { font-size: 20px; font-weight: 700; color: #222; line-height: 1.1; }
.detail-stat-tablet--net .detail-stat-tablet__time { color: #4a9eff; }

.detail-stat-tablet__pace { font-size: 11px; color: #888; margin-top: 2px; }

.detail-stat-tablet__ranks { font-size: 10px; color: #aaa; margin-top: 4px; line-height: 1.4; }
.detail-stat-tablet__ranks strong { color: #444; }

.detail-segments-title { font-size: 12px; font-weight: 700; text-transform: uppercase; color: #666; margin-bottom: 12px; letter-spacing: 0.6px; }
.detail-segments-loading { color: #aaa; font-size: 13px; padding: 12px 0; }
```

Replace with:

```css
/* ── Detail panel tabs ── */
.detail-tabs { display: flex; border-bottom: 1px solid #ddd; margin-bottom: 12px; }
.detail-tab { flex: 1; background: none; border: none; border-bottom: 2px solid transparent; padding: 8px 4px; font-size: 13px; color: #888; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
.detail-tab.active { color: var(--primary-color); border-bottom-color: var(--primary-color); font-weight: 600; }
.detail-tab-pane { display: none; }
.detail-tab-pane.active { display: block; }

/* ── Detail panel: Result tab (light bg #f5f5f5) ── */
.detail-result-block { padding: 0 4px; }
.detail-result-divider { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: #999; padding: 8px 0 4px; border-bottom: 1px solid #ddd; margin-bottom: 4px; }
.detail-result-divider:first-child { padding-top: 0; }
.detail-result-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #e9ecef; font-size: 13px; }
.detail-result-row:last-child { border-bottom: none; }
.detail-result-label { color: #888; }
.detail-result-value { font-weight: 600; color: #222; }
.detail-result-value--gun { color: var(--primary-color); }
.detail-result-value--net { color: #1a73e8; }

/* Desktop: show all panes inline, hide tab buttons */
@media (min-width: 641px) {
  .detail-tabs { display: none; }
  .detail-tab-pane { display: block; }
}
```

- [ ] **Step 2: Remove `html, body { overflow-x: hidden }` from `@media (max-width: 640px)`**

Find (around line 1253):

```css
  html, body {
    overflow-x: hidden;
    max-width: 100%;
  }

  .table-wrapper {
```

Replace with:

```css
  .table-wrapper {
```

- [ ] **Step 3: Remove tablet compact rules and fix mobile chart rules**

Find (around lines 1475–1498):

```css
  /* ── Stat tablets compact on mobile ── */
  .detail-stat-tablet { padding: 8px 8px; }
  .detail-stat-tablet__time { font-size: 16px; }
  .detail-stat-tablet__pace { font-size: 9px; }
  .detail-stat-tablet__ranks { font-size: 9px; }

  /* ── Bar chart: horizontal scroll ── */
  .pace-chart-wrapper {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .pace-chart {
    min-width: max-content;
    justify-content: flex-start;
  }
  .pace-bar-col {
    flex: 0 0 52px;
    min-width: 52px;
  }
```

Replace with:

```css
  /* ── Bar chart: fluid width in pane ── */
  .pace-chart-wrapper { overflow-x: visible; }
  .pace-chart { min-width: 0; }
  .pace-bar-col { flex: 1; min-width: 0; }
```

- [ ] **Step 4: Commit**

```bash
git add static/css/analytics.css
git commit -m "refactor: detail panel tabs CSS — remove tablets, add tab/result styles, fix mobile chart"
```

---

### Task 2: JS — `buildDetailPanelHTML` tab structure

**Files:**
- Modify: `static/js/analytics-results.js:779–803`

**Context:** The function currently returns a template string with `detail-stats-grid` containing two `detail-stat-tablet` divs, followed by `detail-segments-title` and a single `segments-placeholder`. Replace the entire return string with a tab structure: header unchanged, then `detail-tabs` bar, then three `detail-tab-pane` divs. The variable declarations above line 779 are unchanged.

- [ ] **Step 1: Replace the return template in `buildDetailPanelHTML`**

Find (lines 779–803):

```javascript
    return `
    <div class="detail-panel-header">
        <div>
            <div class="detail-panel-name">${fullName}</div>
            <div class="detail-panel-meta">${metaParts.join(' · ')} · ${status}</div>
        </div>
        <button class="detail-panel-close" title="Закрыть">&times;</button>
    </div>
    <div class="detail-stats-grid">
        <div class="detail-stat-tablet detail-stat-tablet--gun">
            <div class="detail-stat-tablet__label">Официальное</div>
            <div class="detail-stat-tablet__time">${timeGun}</div>
            <div class="detail-stat-tablet__pace">${paceGun}</div>
            <div class="detail-stat-tablet__ranks">Место <strong>${rankAbs}</strong> · Пол <strong>${rankSex}</strong> · Кат <strong>${rankCat}</strong></div>
        </div>
        <div class="detail-stat-tablet detail-stat-tablet--net">
            <div class="detail-stat-tablet__label">Чистое</div>
            <div class="detail-stat-tablet__time">${timeNet}</div>
            <div class="detail-stat-tablet__pace">${paceNet}</div>
            <div class="detail-stat-tablet__ranks">Место <strong>${rankAbsClean}</strong> · Пол <strong>${rankSexClean}</strong> · Кат <strong>${rankCatClean}</strong></div>
        </div>
    </div>
    <div class="detail-segments-title">Время по контрольным точкам</div>
    <div class="detail-segments-loading segments-placeholder">Загрузка...</div>
    `;
```

Replace with:

```javascript
    return `
    <div class="detail-panel-header">
        <div>
            <div class="detail-panel-name">${fullName}</div>
            <div class="detail-panel-meta">${metaParts.join(' · ')} · ${status}</div>
        </div>
        <button class="detail-panel-close" title="Закрыть">&times;</button>
    </div>
    <div class="detail-tabs">
        <button class="detail-tab active" data-tab="result">Результат</button>
        <button class="detail-tab" data-tab="pace">Темп</button>
        <button class="detail-tab" data-tab="segments">Отрезки</button>
    </div>
    <div class="detail-tab-pane active" data-pane="result">
        <div class="detail-result-block">
            <div class="detail-result-divider">Официальное</div>
            <div class="detail-result-row"><span class="detail-result-label">Время</span><span class="detail-result-value detail-result-value--gun">${timeGun}</span></div>
            <div class="detail-result-row"><span class="detail-result-label">Темп</span><span class="detail-result-value detail-result-value--gun">${paceGun}</span></div>
            <div class="detail-result-row"><span class="detail-result-label">Место</span><span class="detail-result-value">${rankAbs}</span></div>
            <div class="detail-result-row"><span class="detail-result-label">Пол</span><span class="detail-result-value">${rankSex}</span></div>
            <div class="detail-result-row"><span class="detail-result-label">Кат.</span><span class="detail-result-value">${rankCat}</span></div>
            <div class="detail-result-divider">Чистое</div>
            <div class="detail-result-row"><span class="detail-result-label">Время</span><span class="detail-result-value detail-result-value--net">${timeNet}</span></div>
            <div class="detail-result-row"><span class="detail-result-label">Темп</span><span class="detail-result-value detail-result-value--net">${paceNet}</span></div>
            <div class="detail-result-row"><span class="detail-result-label">Место</span><span class="detail-result-value">${rankAbsClean}</span></div>
            <div class="detail-result-row"><span class="detail-result-label">Пол</span><span class="detail-result-value">${rankSexClean}</span></div>
            <div class="detail-result-row"><span class="detail-result-label">Кат.</span><span class="detail-result-value">${rankCatClean}</span></div>
        </div>
    </div>
    <div class="detail-tab-pane" data-pane="pace">
        <div class="segments-placeholder pace-placeholder">Загрузка...</div>
    </div>
    <div class="detail-tab-pane" data-pane="segments">
        <div class="segments-placeholder segs-placeholder">Загрузка...</div>
    </div>
    `;
```

- [ ] **Step 2: Commit**

```bash
git add static/js/analytics-results.js
git commit -m "feat: buildDetailPanelHTML — tab structure (Результат/Темп/Отрезки)"
```

---

### Task 3: JS — tab listener + loadSegmentsIntoPanel + renderSegmentSection

**Files:**
- Modify: `static/js/analytics-results.js`

**Context:** Three changes in one commit:
1. Add a delegated `click` listener for `.detail-tab` buttons (after line 67).
2. Rewrite `loadSegmentsIntoPanel` (lines 809–824) to fill the `pace` and `segments` panes separately instead of appending `createSegmentsPanel` output to `cell`.
3. Extract `renderSegmentSection` as a new module-level function (replaces inner `renderSection`), then delete `createSegmentsPanel` entirely.

- [ ] **Step 1: Add tab-switching listener after the DOMContentLoaded block**

After line 67 (`});`), insert:

```javascript
document.addEventListener('click', e => {
    const tab = e.target.closest('.detail-tab');
    if (!tab) return;
    const panel = tab.closest('td');
    panel.querySelectorAll('.detail-tab').forEach(t => t.classList.toggle('active', t === tab));
    panel.querySelectorAll('.detail-tab-pane').forEach(p =>
        p.classList.toggle('active', p.dataset.pane === tab.dataset.tab)
    );
});
```

- [ ] **Step 2: Rewrite `loadSegmentsIntoPanel`**

Find (lines 809–824):

```javascript
async function loadSegmentsIntoPanel(cell, resultId) {
    const placeholder = cell.querySelector('.segments-placeholder');
    try {
        const resp = await fetch(`/api/result-segments?result_id=${resultId}`);
        if (!resp.ok) throw new Error(`Ошибка сервера: ${resp.status}`);
        const segments = await resp.json();
        if (placeholder) placeholder.remove();
        if (!segments.length) {
            cell.insertAdjacentHTML('beforeend', '<div style="color:#aaa;font-size:13px;padding:8px 0">Данные КТ не найдены</div>');
            return;
        }
        cell.appendChild(createSegmentsPanel(segments));
    } catch (e) {
        if (placeholder) placeholder.textContent = `Ошибка загрузки КТ: ${e.message}`;
    }
}
```

Replace with:

```javascript
async function loadSegmentsIntoPanel(cell, resultId) {
    const pacePlaceholder = cell.querySelector('.pace-placeholder');
    const segPlaceholder  = cell.querySelector('.segs-placeholder');
    try {
        const resp = await fetch(`/api/result-segments?result_id=${resultId}`);
        if (!resp.ok) throw new Error(`Ошибка сервера: ${resp.status}`);
        const segments = await resp.json();

        if (!segments.length) {
            if (pacePlaceholder) pacePlaceholder.textContent = 'Данные КТ не найдены';
            if (segPlaceholder)  segPlaceholder.textContent  = 'Данные КТ не найдены';
            return;
        }

        const consecutive = filterConsecutiveSegments(segments);
        const splits       = filterSplitSegments(segments);
        const kmMap        = buildKmMap(segments);

        const pacePane = cell.querySelector('[data-pane="pace"]');
        if (pacePlaceholder) pacePlaceholder.remove();
        const chart = renderPaceChart(consecutive, kmMap);
        if (chart && pacePane) pacePane.appendChild(chart);

        const segsPane = cell.querySelector('[data-pane="segments"]');
        if (segPlaceholder) segPlaceholder.remove();
        if (segsPane) {
            renderSegmentSection(segsPane, 'Отрезки', '#e63946', consecutive);
            renderSegmentSection(segsPane, 'Сплиты от старта', '#4a9eff', splits);
            if (!consecutive.length && !splits.length) {
                segsPane.insertAdjacentHTML('beforeend',
                    '<div style="color:#aaa;font-size:13px;padding:8px 0">Данные КТ не найдены</div>');
            }
        }
    } catch (e) {
        if (pacePlaceholder) pacePlaceholder.textContent = `Ошибка загрузки КТ: ${e.message}`;
        if (segPlaceholder)  segPlaceholder.textContent  = `Ошибка загрузки КТ: ${e.message}`;
    }
}
```

- [ ] **Step 3: Replace `createSegmentsPanel` with `renderSegmentSection`**

Find the entire `createSegmentsPanel` function (lines 1079–1175):

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

Replace with:

```javascript
function renderSegmentSection(container, title, color, rows) {
    if (!rows.length) return;
    const useGun = timeMode === 'gun';
    const modeLabel = useGun ? 'офиц.' : 'чист.';

    const header = document.createElement('div');
    header.className = 'segment-section-header';
    header.style.color = color;
    header.textContent = title;
    container.appendChild(header);

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
    container.appendChild(table);
}
```

- [ ] **Step 4: Commit**

```bash
git add static/js/analytics-results.js
git commit -m "feat: tab switching + rewrite loadSegmentsIntoPanel + extract renderSegmentSection"
```

---

## Verification

Open browser DevTools → set viewport to 390px → navigate to `/results` → select any event with results → click any runner row.

**Mobile (390px):**
- [ ] No horizontal page scroll
- [ ] Panel opens below the row
- [ ] «Результат» tab is active by default — shows label:value list (gun values red, net values blue)
- [ ] Tap «Темп» — bar chart fills full panel width, no horizontal scroll, bars share width equally
- [ ] Tap «Отрезки» — segment cards and split cards render correctly
- [ ] Tap «Результат» again — switches back

**Desktop (>640px, resize DevTools):**
- [ ] Tab buttons are NOT visible
- [ ] All three panes visible sequentially (result list → chart → segments)
- [ ] Bar chart bars have `flex:1`, not fixed px
- [ ] Segment tables render as normal table (not card layout)
