# Mobile Results Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the /results page detail panel and page layout for mobile (≤640px) — compact stat tablets, scrollable bar chart, segment card rows.

**Architecture:** Two files only. CSS changes go into the existing `@media (max-width: 640px)` block in `analytics.css` plus new base styles for `.detail-stat-tablet`. JS change replaces the `detail-stat-block` HTML template in `buildDetailPanelHTML` with the new `detail-stat-tablet` structure. No backend changes.

**Tech Stack:** Vanilla JS, CSS Grid, existing FastAPI/Pydantic backend (untouched)

---

## File Map

| File | Lines | Change |
|------|-------|--------|
| `static/css/analytics.css` | 339–351 | Replace old `.detail-stat-block` rules with new `.detail-stat-tablet` rules |
| `static/css/analytics.css` | 340 | Remove the `@media (max-width:600px)` that collapses `.detail-stats-grid` to 1 col |
| `static/css/analytics.css` | 1449 (end) | Extend existing `@media (max-width: 640px)` with page tweaks + bar chart scroll + segments card layout |
| `static/js/analytics-results.js` | 787–804 | Replace `detail-stat-block` HTML in `buildDetailPanelHTML` with `detail-stat-tablet` |

---

### Task 1: New `.detail-stat-tablet` CSS (base styles, all viewports)

**Files:**
- Modify: `static/css/analytics.css:339-351`

**Context:** Lines 339–351 contain the old `.detail-stat-block`, `.detail-stat-row`, `.detail-stat-label`, `.detail-stat-value` rules and a `@media (max-width:600px)` that collapses the grid to 1 column. We replace all of this with new tablet-style rules that work at every viewport. The `detail-stats-grid` stays 2-column always.

- [ ] **Step 1: Replace the old detail-panel stat block styles**

In `static/css/analytics.css`, find and replace this block (lines 339–351):

```css
.detail-stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
@media (max-width: 600px) { .detail-stats-grid { grid-template-columns: 1fr; } }
.detail-stat-block { background: white; border-radius: 8px; padding: 16px 20px; border-left: 4px solid var(--primary-color); }
.detail-stat-block h4 { font-size: 11px; color: #999; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 0.6px; font-weight: 600; }
.detail-stat-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #f0f0f0; font-size: 14px; }
.detail-stat-row:last-child { border-bottom: none; }
.detail-stat-label { color: #888; }
.detail-stat-value { font-weight: 600; color: #222; }
.detail-stat-value-big { font-size: 26px; font-weight: 700; color: #222; }
.detail-stat-value-big + .detail-stat-label { font-size: 12px; }
.detail-segments-title { font-size: 12px; font-weight: 700; text-transform: uppercase; color: #666; margin-bottom: 12px; letter-spacing: 0.6px; }
.detail-segments-loading { color: #aaa; font-size: 13px; padding: 12px 0; }
.row-active td { background: #e8f4fd !important; }
```

Replace with:

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
.row-active td { background: #e8f4fd !important; }
```

- [ ] **Step 2: Commit**

```bash
git add static/css/analytics.css
git commit -m "refactor: detail-stat-block → detail-stat-tablet CSS (base styles)"
```

---

### Task 2: Update `buildDetailPanelHTML` JS to use new tablet structure

**Files:**
- Modify: `static/js/analytics-results.js:787-807`

**Context:** The function builds the HTML string for the detail panel. Lines 787–807 contain the old `detail-stat-block` divs with `detail-stat-row` rows. We replace the `detail-stats-grid` section only — header, variables, and segments placeholder stay unchanged.

- [ ] **Step 1: Replace the `detail-stats-grid` section in `buildDetailPanelHTML`**

In `static/js/analytics-results.js`, find this section inside `buildDetailPanelHTML` (lines 787–804):

```javascript
    <div class="detail-stats-grid">
        <div class="detail-stat-block">
            <h4>Официальные результаты</h4>
            <div class="detail-stat-row"><span class="detail-stat-label">Место</span><span class="detail-stat-value">${rankAbs}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Место по полу</span><span class="detail-stat-value">${rankSex}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Место в категории</span><span class="detail-stat-value">${rankCat} ${category}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Время</span><span class="detail-stat-value">${timeGun}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Темп</span><span class="detail-stat-value">${paceGun}</span></div>
        </div>
        <div class="detail-stat-block">
            <h4>Чистые результаты</h4>
            <div class="detail-stat-row"><span class="detail-stat-label">Место</span><span class="detail-stat-value">${rankAbsClean}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Место по полу</span><span class="detail-stat-value">${rankSexClean}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Место в категории</span><span class="detail-stat-value">${rankCatClean} ${category}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Время</span><span class="detail-stat-value">${timeNet}</span></div>
            <div class="detail-stat-row"><span class="detail-stat-label">Темп</span><span class="detail-stat-value">${paceNet}</span></div>
        </div>
    </div>
```

Replace with:

```javascript
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
```

- [ ] **Step 2: Commit**

```bash
git add static/js/analytics-results.js
git commit -m "feat: detail panel stat blocks → compact tablets (gun/net)"
```

---

### Task 3: Mobile CSS — page tweaks + bar chart scroll + segments card layout

**Files:**
- Modify: `static/css/analytics.css:1449` (end of existing `@media (max-width: 640px)` block)

**Context:** The existing `@media (max-width: 640px)` block ends at line 1449 with `} /* end @media 640px */`. We add new rules inside it (before the closing brace) for: container/event-card page-level tweaks, tablet stat block compact sizing, bar chart scrollability, and segments table card layout.

- [ ] **Step 1: Add mobile rules inside the existing `@media (max-width: 640px)` block**

In `static/css/analytics.css`, find the closing comment of the media block:

```css
} /* end @media 640px */
```

Replace with:

```css
  /* ── Page-level tweaks ── */
  .container {
    border-radius: 0;
    box-shadow: none;
    margin: 0;
    padding: 8px 0;
  }

  .event-card {
    height: 160px;
    margin-bottom: 16px;
    border-radius: 0;
  }

  .detail-panel-row > td {
    padding: 10px 12px !important;
  }

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

  /* ── Segments table: card layout ── */
  .segments-table thead { display: none; }

  .segments-table tbody tr {
    display: grid;
    grid-template-columns: 1fr auto auto;
    grid-template-rows: auto auto;
    row-gap: 3px;
    background: #162030;
    border-radius: 6px;
    margin-bottom: 4px;
    padding: 7px 10px;
    border: none;
  }

  .segments-table tbody td {
    display: block;
    padding: 0;
    border: none;
    text-align: left;
  }

  /* Row 1: segment name | time | pace */
  .segments-table tbody td:nth-child(1) {
    grid-column: 1; grid-row: 1;
    font-size: 10px; color: #bbb;
    align-self: center;
  }
  .segments-table tbody td:nth-child(2) {
    grid-column: 2; grid-row: 1;
    font-size: 10px; font-weight: 600;
    text-align: right; padding-right: 10px;
    align-self: center;
  }
  .segments-table tbody td:nth-child(3) {
    grid-column: 3; grid-row: 1;
    font-size: 10px; font-weight: 700;
    text-align: right;
    align-self: center;
  }

  /* Row 2: ranks */
  .segments-table tbody td:nth-child(4) {
    grid-column: 1; grid-row: 2;
    font-size: 8px; color: #555;
  }
  .segments-table tbody td:nth-child(5) {
    grid-column: 2; grid-row: 2;
    font-size: 8px; color: #555;
    text-align: right; padding-right: 10px;
  }
  .segments-table tbody td:nth-child(6) {
    grid-column: 3; grid-row: 2;
    font-size: 8px; color: #555;
    text-align: right;
  }

  .segments-table tbody td:nth-child(4)::before { content: "Абс "; }
  .segments-table tbody td:nth-child(5)::before { content: "Пол "; }
  .segments-table tbody td:nth-child(6)::before { content: "Кат "; }

  /* Strip rank badge background on mobile */
  .segments-table tbody .seg-rank-badge {
    background: transparent !important;
    padding: 0;
    font-size: 8px;
    font-weight: 600;
  }

} /* end @media 640px */
```

- [ ] **Step 2: Commit**

```bash
git add static/css/analytics.css
git commit -m "feat: mobile layout — page tweaks, bar chart scroll, segment cards ≤640px"
```

---

## Verification

Open browser DevTools → set viewport to 390px → navigate to `/results`, select any event with results.

**Page level:**
- [ ] No horizontal page scroll
- [ ] Container takes full width, no card shadow/radius
- [ ] Event card is ~160px tall (not 280px)

**Detail panel (click any runner row):**
- [ ] Panel opens full width, padding is compact (~10px sides)
- [ ] Two stat tablets side by side: red top border (Официальное) | blue top border (Чистое)
- [ ] Each tablet shows: label · big time · pace · "Место N · Пол M#N · Кат #N"

**Bar chart:**
- [ ] Each bar is at least 52px wide
- [ ] Chart scrolls horizontally (swipe/drag) when 4+ bars
- [ ] Pace label shows "3:05 мин/км" under each bar

**Segment tables (Отрезки / Сплиты от старта):**
- [ ] No table header row
- [ ] Each segment row is a dark card (background `#162030`)
- [ ] Row 1: segment name (left) · time (right-center) · pace мин/км (right)
- [ ] Row 2: "Абс N" · "Пол M#N" · "Кат #N" in grey

**Desktop (>640px, resize DevTools back):**
- [ ] Stat tablets still show in 2-column grid, look correct
- [ ] Bar chart not scrolling (bars fit naturally)
- [ ] Segment tables show as normal table with header
