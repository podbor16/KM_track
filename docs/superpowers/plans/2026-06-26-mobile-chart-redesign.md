# Mobile Chart Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать вкладку «График» читаемой на мобильном: авто-выбор топ-3 при открытии, резкий контраст линий, шторка снизу для выбора участников.

**Architecture:** Все изменения только в `tri_results.html` и `tri_results.css`. На десктопе поведение не меняется. На мобильном (`≤640px`) скрываем десктопный сайдбар, добавляем trigger-bar + bottom sheet для выбора участников, усиливаем контраст линий, при первом открытии вкладки автоматически выбираем топ-3 по кругам.

**Tech Stack:** Vanilla JS, Chart.js v4, CSS media queries (max-width: 640px)

---

## Файлы

- Modify: `templates/tri_results.html` — JS-логика и HTML-структура
- Modify: `static/css/tri_results.css` — мобильные стили

---

## Task 1: Хелпер `isMobile()` и функции шторки

**Files:**
- Modify: `templates/tri_results.html` — добавить после блока `let selectedChartPids = new Set();` (строка ~160)

- [ ] **Добавить `isMobile()`, `_syncMobileChart()`, `openChartSheet()`, `closeChartSheet()`**

Найти в `tri_results.html` строку:
```js
    function toggleChartPid(pid) {
```

Вставить ПЕРЕД ней:

```js
    function isMobile() { return window.innerWidth <= 640; }

    function _syncMobileChart() {
        if (!isMobile()) return;
        const badge = document.getElementById('chart-mobile-badge');
        if (badge) badge.textContent = selectedChartPids.size;

        const chipsEl = document.getElementById('chart-mobile-chips');
        if (chipsEl) {
            chipsEl.innerHTML = [...selectedChartPids].map(pid => {
                const idx = chartDatasetPids.indexOf(pid);
                const color = idx >= 0 ? CHART_COLORS[idx % CHART_COLORS.length] : '#888';
                const p = allStandings.find(r => r.id === pid);
                const name = p ? p.surname : pid;
                return `<div class="tri-chart-mobile-chip">
                    <span class="tri-chart-mobile-chip-dot" style="background:${color}"></span>${name}</div>`;
            }).join('');
        }

        document.querySelectorAll('.tri-chart-sheet-item').forEach(el => {
            const pid = parseInt(el.dataset.pid);
            el.querySelector('.tri-chart-sheet-check')?.classList.toggle('on', selectedChartPids.has(pid));
        });
    }

    function openChartSheet() {
        const list = document.getElementById('chart-sheet-list');
        if (!list) return;
        list.innerHTML = chartDatasetPids.map((pid, i) => {
            const color = CHART_COLORS[i % CHART_COLORS.length];
            const p = allStandings.find(r => r.id === pid);
            if (!p) return '';
            const isChecked = selectedChartPids.has(pid);
            return `<div class="tri-chart-sheet-item" data-pid="${pid}" onclick="toggleChartPid(${pid})">
                <span class="tri-chart-sheet-dot" style="background:${color}"></span>
                <span class="tri-chart-sheet-name">${p.surname} ${p.name}</span>
                <span class="tri-chart-sheet-km">${parseFloat(p.total_km).toFixed(1)} км</span>
                <span class="tri-chart-sheet-check${isChecked ? ' on' : ''}">✓</span>
            </div>`;
        }).join('');
        document.getElementById('chart-sheet')?.classList.add('open');
        document.getElementById('chart-sheet-overlay')?.classList.add('open');
    }

    function closeChartSheet() {
        document.getElementById('chart-sheet')?.classList.remove('open');
        document.getElementById('chart-sheet-overlay')?.classList.remove('open');
    }

```

- [ ] **Commit**

```bash
git add templates/tri_results.html
git commit -m "feat: add isMobile, _syncMobileChart, openChartSheet, closeChartSheet"
```

---

## Task 2: Добавить HTML — mobile-bar и bottom sheet

**Files:**
- Modify: `templates/tri_results.html` — изменить блок `#tab-chart` (строки ~128-152)

- [ ] **Заменить блок `#tab-chart`**

Найти в HTML:
```html
    <div id="tab-chart" style="display:none">
        <div class="tri-chart-subtabs">
            <button class="tri-chart-subtab active" onclick="switchChartType('speed', this)">Скорость</button>
            <button class="tri-chart-subtab" onclick="switchChartType('position', this)">Позиция</button>
        </div>
        <div class="tri-chart-layout">
```

Заменить на:
```html
    <div id="tab-chart" style="display:none">
        <div class="tri-chart-subtabs">
            <button class="tri-chart-subtab active" onclick="switchChartType('speed', this)">Скорость</button>
            <button class="tri-chart-subtab" onclick="switchChartType('position', this)">Позиция</button>
        </div>
        <div class="tri-chart-mobile-bar">
            <div class="tri-chart-mobile-trigger" onclick="openChartSheet()">
                <span class="tri-chart-mobile-label">Участники</span>
                <span class="tri-chart-mobile-badge" id="chart-mobile-badge">0</span>
                <span class="tri-chart-mobile-hint">нажмите для выбора ›</span>
            </div>
            <div class="tri-chart-mobile-chips" id="chart-mobile-chips"></div>
        </div>
        <div class="tri-chart-layout">
```

- [ ] **Добавить overlay и sheet перед закрывающим тегом `</div>` блока `#tab-chart`**

Найти в HTML:
```html
        <div class="tri-refresh" id="chart-refresh-label"></div>
    </div>
```
(конец блока `#tab-chart`)

Заменить на:
```html
        <div class="tri-refresh" id="chart-refresh-label"></div>
        <div class="tri-chart-sheet-overlay" id="chart-sheet-overlay" onclick="closeChartSheet()"></div>
        <div class="tri-chart-sheet" id="chart-sheet">
            <div class="tri-chart-sheet-handle"></div>
            <div class="tri-chart-sheet-header">
                <span>Выбор участников</span>
                <div class="tri-chart-sheet-header-actions">
                    <button class="tri-chart-sheet-header-btn" onclick="selectAllChartPids()">Все</button>
                    <button class="tri-chart-sheet-header-btn muted" onclick="clearAllChartPids()">Сбросить</button>
                </div>
            </div>
            <div id="chart-sheet-list"></div>
        </div>
    </div>
```

- [ ] **Commit**

```bash
git add templates/tri_results.html
git commit -m "feat: add mobile-bar and bottom sheet HTML for chart participant selection"
```

---

## Task 3: Авто-выбор топ-3 при открытии вкладки

**Files:**
- Modify: `templates/tri_results.html` — функция `switchPageTab` (строки ~405-421)

- [ ] **Обновить `switchPageTab`**

Найти:
```js
        if (name === 'chart') {
            requestAnimationFrame(() => {
                if (activeChartType === 'speed') renderChart();
                else renderPositionChart();
            });
        }
```

Заменить на:
```js
        if (name === 'chart') {
            if (isMobile() && selectedChartPids.size === 0 && allStandings.length > 0) {
                allStandings
                    .slice()
                    .sort((a, b) => b.laps_completed - a.laps_completed)
                    .slice(0, 3)
                    .forEach(r => selectedChartPids.add(r.id));
            }
            requestAnimationFrame(() => {
                if (activeChartType === 'speed') renderChart();
                else renderPositionChart();
            });
        }
```

- [ ] **Commit**

```bash
git add templates/tri_results.html
git commit -m "feat: auto-select top-3 participants on mobile when opening chart tab"
```

---

## Task 4: Усиленный контраст линий на мобильном

**Files:**
- Modify: `templates/tri_results.html` — функции `renderChart()` и `renderPositionChart()`

- [ ] **Обновить контраст в `renderChart()`**

Найти в `renderChart()` (строки ~492-500):
```js
            // По умолчанию: серый. Выбранный: цветной. Невыбранный при активной выборке: бледный серый
            let lineColor, lineWidth, endRadius;
            if (!hasSelection) {
                lineColor = '#c8c8c8'; endRadius = 3; lineWidth = 1.5;
            } else if (isSelected) {
                lineColor = color;    endRadius = 6; lineWidth = 2.5;
            } else {
                lineColor = '#e0e0e0'; endRadius = 0; lineWidth = 1;
            }
```

Заменить на:
```js
            // По умолчанию: серый. Выбранный: цветной. Невыбранный при активной выборке: бледный серый (ещё бледнее на мобильном)
            let lineColor, lineWidth, endRadius;
            if (!hasSelection) {
                lineColor = '#c8c8c8'; endRadius = 3; lineWidth = 1.5;
            } else if (isSelected) {
                lineColor = color; endRadius = 6; lineWidth = isMobile() ? 3 : 2.5;
            } else {
                lineColor = isMobile() ? 'rgba(0,0,0,0.07)' : '#e0e0e0';
                endRadius = 0; lineWidth = 1;
            }
```

- [ ] **Добавить вызов `_syncMobileChart()` в конце `renderChart()` — после `triChart.update('none')` и после создания нового `triChart`**

Найти в `renderChart()` блок обновления/создания чарта:
```js
        if (triChart) {
            triChart.data.datasets = datasets;
            triChart.update('none');
        } else {
            triChart = new Chart(ctx, {
```

После всего блока `if (triChart) { ... } else { ... }` (то есть после закрывающей `}` этого if/else) добавить:
```js
        _syncMobileChart();
```

- [ ] **Обновить контраст в `renderPositionChart()`**

Найти в `renderPositionChart()` (строки ~695-698):
```js
            let lineColor, lineWidth, endRadius;
            if (!hasSelection)     { lineColor = '#c8c8c8'; endRadius = 3; lineWidth = 1.5; }
            else if (isSelected)   { lineColor = color;     endRadius = 6; lineWidth = 2.5; }
            else                   { lineColor = '#e0e0e0'; endRadius = 0; lineWidth = 1; }
```

Заменить на:
```js
            let lineColor, lineWidth, endRadius;
            if (!hasSelection)   { lineColor = '#c8c8c8'; endRadius = 3; lineWidth = 1.5; }
            else if (isSelected) { lineColor = color; endRadius = 6; lineWidth = isMobile() ? 3 : 2.5; }
            else                 { lineColor = isMobile() ? 'rgba(0,0,0,0.07)' : '#e0e0e0'; endRadius = 0; lineWidth = 1; }
```

- [ ] **Добавить `_syncMobileChart()` в конце `renderPositionChart()` — аналогично `renderChart()`**

Найти в `renderPositionChart()` блок:
```js
        if (triChartPosition) {
            triChartPosition.data.datasets = datasets;
            triChartPosition.update('none');
        } else {
            triChartPosition = new Chart(ctx, {
```

После закрывающей `}` этого if/else добавить:
```js
        _syncMobileChart();
```

- [ ] **Commit**

```bash
git add templates/tri_results.html
git commit -m "feat: stronger line contrast on mobile in speed and position charts"
```

---

## Task 5: Подключить `_syncMobileChart()` к изменениям выборки

**Files:**
- Modify: `templates/tri_results.html` — функции `toggleChartPid`, `selectAllChartPids`, `clearAllChartPids`

- [ ] **Добавить `_syncMobileChart()` в `toggleChartPid`**

Найти:
```js
    function toggleChartPid(pid) {
        if (selectedChartPids.has(pid)) {
            selectedChartPids.delete(pid);
        } else {
            selectedChartPids.add(pid);
        }
        document.querySelectorAll('.tri-chart-legend-item').forEach(el => {
            el.classList.toggle('active', selectedChartPids.has(+el.dataset.pid));
        });
        if (activeChartType === 'position') _updatePositionSelection();
        else renderChart();
    }
```

Заменить на:
```js
    function toggleChartPid(pid) {
        if (selectedChartPids.has(pid)) {
            selectedChartPids.delete(pid);
        } else {
            selectedChartPids.add(pid);
        }
        document.querySelectorAll('.tri-chart-legend-item').forEach(el => {
            el.classList.toggle('active', selectedChartPids.has(+el.dataset.pid));
        });
        if (activeChartType === 'position') _updatePositionSelection();
        else renderChart();
        _syncMobileChart();
    }
```

- [ ] **Добавить `_syncMobileChart()` в `selectAllChartPids` и `clearAllChartPids`**

Найти:
```js
    function selectAllChartPids() {
        chartDatasetPids.forEach(pid => selectedChartPids.add(pid));
        document.querySelectorAll('.tri-chart-legend-item').forEach(el => el.classList.add('active'));
        if (activeChartType === 'position') _updatePositionSelection();
        else renderChart();
    }

    function clearAllChartPids() {
        selectedChartPids.clear();
        document.querySelectorAll('.tri-chart-legend-item').forEach(el => el.classList.remove('active'));
        if (activeChartType === 'position') _updatePositionSelection();
        else renderChart();
    }
```

Заменить на:
```js
    function selectAllChartPids() {
        chartDatasetPids.forEach(pid => selectedChartPids.add(pid));
        document.querySelectorAll('.tri-chart-legend-item').forEach(el => el.classList.add('active'));
        if (activeChartType === 'position') _updatePositionSelection();
        else renderChart();
        _syncMobileChart();
    }

    function clearAllChartPids() {
        selectedChartPids.clear();
        document.querySelectorAll('.tri-chart-legend-item').forEach(el => el.classList.remove('active'));
        if (activeChartType === 'position') _updatePositionSelection();
        else renderChart();
        _syncMobileChart();
    }
```

- [ ] **Commit**

```bash
git add templates/tri_results.html
git commit -m "feat: sync mobile chart UI on every selection change"
```

---

## Task 6: CSS — мобильные стили

**Files:**
- Modify: `static/css/tri_results.css`

- [ ] **Добавить desktop-hidden правила (перед `@media`) и мобильные стили (внутри существующего `@media (max-width: 640px)` блока)**

В CSS найти блок:
```css
@media (max-width: 640px) {
    .tri-chart-layout { flex-direction: column; }
    .tri-chart-sidebar {
        width: 100%; max-height: none;
        padding: 8px;
        border-radius: 0; box-shadow: none;
    }
    .tri-chart-sidebar__hint { display: none; }
    #chart-legend-list { display: flex; flex-wrap: wrap; gap: 4px; }
    .tri-chart-legend-item { padding: 4px 8px; border-radius: 20px; background: #f0f0f0; font-size: 11px; }
    .tri-chart-legend-item.active { background: var(--tri-navy); color: #fff; }
    .tri-chart-wrap { height: 260px; border-radius: 0; box-shadow: none; padding: 10px 6px 6px; }
}
```

Заменить на:
```css
/* Mobile chart elements — hidden on desktop */
.tri-chart-mobile-bar { display: none; }
.tri-chart-sheet-overlay { display: none; }
.tri-chart-sheet { display: none; }

@media (max-width: 640px) {
    /* Скрыть десктопный сайдбар */
    .tri-chart-layout { flex-direction: column; }
    .tri-chart-sidebar { display: none; }
    .tri-chart-wrap { height: 320px; border-radius: 0; box-shadow: none; padding: 10px 6px 6px; }

    /* Trigger-bar с чипами */
    .tri-chart-mobile-bar {
        display: block;
        background: #fafafa;
        border-bottom: 1px solid var(--tri-border);
    }
    .tri-chart-mobile-trigger {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 12px;
        cursor: pointer;
    }
    .tri-chart-mobile-label { font-size: 12px; font-weight: 700; color: var(--tri-navy); }
    .tri-chart-mobile-badge {
        background: var(--tri-accent);
        color: #fff;
        border-radius: 10px;
        padding: 1px 7px;
        font-size: 11px;
        font-weight: 700;
    }
    .tri-chart-mobile-hint { font-size: 11px; color: var(--tri-muted); margin-left: auto; }
    .tri-chart-mobile-chips { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 12px 8px; }
    .tri-chart-mobile-chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 3px 8px;
        border-radius: 12px;
        background: var(--tri-navy);
        color: #fff;
        font-size: 10px;
        font-weight: 700;
    }
    .tri-chart-mobile-chip-dot {
        width: 6px; height: 6px;
        border-radius: 50%;
        display: inline-block;
    }

    /* Bottom sheet overlay */
    .tri-chart-sheet-overlay {
        display: block;
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.35);
        z-index: 100;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.2s;
    }
    .tri-chart-sheet-overlay.open { opacity: 1; pointer-events: auto; }

    /* Bottom sheet */
    .tri-chart-sheet {
        display: block;
        position: fixed;
        left: 0; right: 0; bottom: 0;
        background: #fff;
        border-radius: 16px 16px 0 0;
        z-index: 101;
        max-height: 70vh;
        overflow-y: auto;
        transform: translateY(100%);
        transition: transform 0.25s ease;
        box-shadow: 0 -4px 24px rgba(0,0,0,0.15);
    }
    .tri-chart-sheet.open { transform: translateY(0); }
    .tri-chart-sheet-handle {
        width: 36px; height: 4px;
        background: #ddd;
        border-radius: 2px;
        margin: 10px auto 8px;
    }
    .tri-chart-sheet-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 16px 10px;
        border-bottom: 1px solid var(--tri-border);
        font-size: 14px;
        font-weight: 800;
        color: var(--tri-navy);
    }
    .tri-chart-sheet-header-actions { display: flex; gap: 12px; }
    .tri-chart-sheet-header-btn {
        font-size: 12px; font-weight: 700;
        color: var(--tri-accent);
        background: none; border: none;
        cursor: pointer;
        font-family: 'Onest', Arial, sans-serif;
        padding: 0;
    }
    .tri-chart-sheet-header-btn.muted { color: var(--tri-muted); }
    .tri-chart-sheet-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 12px 16px;
        border-bottom: 1px solid #f8f8f8;
        cursor: pointer;
    }
    .tri-chart-sheet-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
    .tri-chart-sheet-name { flex: 1; font-size: 13px; font-weight: 600; color: var(--tri-text); }
    .tri-chart-sheet-km { font-size: 11px; color: var(--tri-muted); }
    .tri-chart-sheet-check {
        width: 20px; height: 20px;
        border-radius: 6px;
        border: 2px solid var(--tri-border);
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        color: transparent;
    }
    .tri-chart-sheet-check.on {
        background: var(--tri-navy);
        border-color: var(--tri-navy);
        color: #fff;
    }
}
```

- [ ] **Commit**

```bash
git add static/css/tri_results.css
git commit -m "feat: mobile chart CSS — trigger bar, chips, bottom sheet, taller chart"
```

---

## Task 7: Deploy и проверка

- [ ] **Push и деплой**

```bash
git push origin main
```

Затем SSH на сервер:
```bash
cd /opt/km_track && git pull origin main && systemctl restart km_track
```

- [ ] **Проверить на мобильном (реальный телефон или DevTools → Toggle device toolbar → ширина ≤ 640px)**

1. Открыть `/24h` → вкладка «График»
2. Убедиться что топ-3 выбраны автоматически, три яркие линии видны, остальные почти невидимы
3. Нажать «Участники (3)» → шторка поднимается снизу
4. Убрать галочку → линия пропадает, чип убирается, badge обновляется
5. Нажать «Все» → все выбраны
6. Нажать «Сбросить» → чипов нет, badge = 0, все линии серые
7. Тап мимо шторки → шторка закрывается
8. Переключить «Позиция» → те же выбранные, тот же контраст
9. Проверить десктоп (ширина > 640px) — сайдбар работает как раньше, шторки нет

- [ ] **Commit если были мелкие правки по итогам проверки**
