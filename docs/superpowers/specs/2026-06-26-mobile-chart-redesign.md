# Mobile Chart Redesign — Spec

**Дата:** 2026-06-26  
**Файлы:** `templates/tri_results.html`, `static/css/tri_results.css`

## Проблема

На мобильном вкладка «График» нечитаема: 10 одинаковых серых линий накладываются друг на друга на маленьком экране (260px высота). Десктоп не трогаем.

## Решение

Три взаимосвязанных изменения, только для `@media (max-width: 640px)`:

---

## 1. Авто-выбор топ-3 при открытии вкладки

**Когда:** переключение на вкладку «График» (`switchPageTab('chart', ...)`).  
**Логика:** если `selectedChartPids` пуст И ширина экрана ≤ 640px — выбрать топ-3 участника по `laps_completed` из `allStandings`.  
**Десктоп:** без изменений (если `selectedChartPids` непустой — ничего не делаем).

```
при switchPageTab('chart'):
  если isMobile() && selectedChartPids.size === 0:
    topPids = allStandings
      .slice()
      .sort by laps_completed DESC
      .slice(0, 3)
      .map(r => r.id)
    topPids.forEach(pid => selectedChartPids.add(pid))
```

`isMobile()` → `window.innerWidth <= 640`.

---

## 2. Контраст линий: выбранные — жирные, остальные — «призраки»

**Текущее поведение:** выбранные линии яркие, невыбранные серые (`opacity` ~0.3, `borderWidth` 1).  
**Новое на мобильном:** невыбранные линии `borderWidth: 1`, `borderColor: rgba(0,0,0,0.07)` — почти невидимые «призраки». Выбранные — `borderWidth: 3`, полный цвет.

Реализация: в `renderChart()` и `renderPositionChart()` при вычислении `borderWidth` и `borderColor` датасета — добавить ветку `isMobile()`:

```
если isMobile() && есть выбранные:
  выбранный: borderWidth=3, alpha=1.0
  невыбранный: borderWidth=1, color=rgba(0,0,0,0.07)
иначе (десктоп — как сейчас):
  выбранный: borderWidth=2, alpha=1.0
  невыбранный: borderWidth=1, alpha=0.15
```

---

## 3. Мобильный интерфейс выбора участников (шторка)

На мобильном **скрыть** десктопный `.tri-chart-sidebar` через CSS (`display:none`).  
Вместо него добавить новые элементы **только на мобильном** (CSS `display:none` по умолчанию, показываются в media query):

### 3a. Trigger-bar + active chips

```html
<div class="tri-chart-mobile-bar">
  <div class="tri-chart-mobile-trigger" onclick="openChartSheet()">
    <span class="tri-chart-mobile-label">Участники</span>
    <span class="tri-chart-mobile-badge" id="chart-mobile-badge">0</span>
    <span class="tri-chart-mobile-hint">нажмите для выбора ›</span>
  </div>
  <div class="tri-chart-mobile-chips" id="chart-mobile-chips"></div>
</div>
```

- **Badge** (`#chart-mobile-badge`): число выбранных, обновляется при каждом изменении `selectedChartPids`.
- **Chips** (`#chart-mobile-chips`): цветные таблетки выбранных участников (только имя + цветная точка), перерендериваются при изменении выборки.

### 3b. Bottom sheet

```html
<div class="tri-chart-sheet-overlay" id="chart-sheet-overlay" onclick="closeChartSheet()"></div>
<div class="tri-chart-sheet" id="chart-sheet">
  <div class="tri-chart-sheet-handle"></div>
  <div class="tri-chart-sheet-header">
    <span>Выбор участников</span>
    <div>
      <button onclick="selectAllChartPids()">Все</button>
      <button onclick="clearAllChartPids()">Сбросить</button>
    </div>
  </div>
  <div id="chart-sheet-list"></div>
</div>
```

**Список** (`#chart-sheet-list`): рендерится при `openChartSheet()` из `chartDatasetPids` + `allStandings`. Каждая строка:
- цветная точка, имя участника, расстояние (км), чекбокс-иконка
- `onclick` → `toggleChartPid(pid)` + обновить чекбокс + обновить chips/badge

**Открытие/закрытие:**
- `openChartSheet()` → добавить класс `open` к sheet + overlay
- `closeChartSheet()` → убрать класс `open`
- Тап по overlay → `closeChartSheet()`

Шторка не закрывается автоматически при выборе — пользователь сам закрывает (свайп/тап мимо). Это даёт возможность выбрать несколько подряд.

### 3c. Синхронизация

Функция `_syncMobileChart()` вызывается после каждого изменения `selectedChartPids`:
- Обновляет badge
- Перерендеривает chips
- Обновляет чекбоксы в шторке (если открыта)

`_syncMobileChart()` вызывается внутри `toggleChartPid()`, `selectAllChartPids()`, `clearAllChartPids()`.

---

## CSS

Только мобильный (`@media (max-width: 640px)`):

```css
/* Скрыть десктопный сайдбар */
.tri-chart-sidebar { display: none; }

/* Показать мобильные элементы */
.tri-chart-mobile-bar { display: block; }
.tri-chart-sheet-overlay { display: block; } /* когда .open */
.tri-chart-sheet { display: block; } /* трансформ снизу, анимация */

/* Chart wrap выше на мобильном */
.tri-chart-wrap { height: 320px; } /* было 260px */

/* Шторка: slide-up анимация */
.tri-chart-sheet { transform: translateY(100%); transition: transform 0.25s ease; }
.tri-chart-sheet.open { transform: translateY(0); }
.tri-chart-sheet-overlay { opacity: 0; pointer-events: none; transition: opacity 0.2s; }
.tri-chart-sheet-overlay.open { opacity: 1; pointer-events: auto; }
```

На десктопе (без media query):
```css
.tri-chart-mobile-bar { display: none; }
.tri-chart-sheet-overlay { display: none; }
.tri-chart-sheet { display: none; }
```

---

## Что НЕ меняем

- Десктопный сайдбар — без изменений
- Логика `toggleChartPid`, `selectAllChartPids`, `clearAllChartPids` — без изменений (только добавляем вызов `_syncMobileChart()`)
- API, backend, данные — не трогаем
- Вкладки «Расстояние» и «Отрезки» — не трогаем

---

## Порядок реализации

1. Добавить `isMobile()` хелпер
2. Добавить автовыбор топ-3 в `switchPageTab`
3. Добавить HTML шторки и mobile-bar в шаблон
4. Добавить `_syncMobileChart()`, `openChartSheet()`, `closeChartSheet()`
5. Обновить логику контраста линий в `renderChart()` и `renderPositionChart()`
6. Добавить CSS
7. Вызвать `_syncMobileChart()` в `toggleChartPid`, `selectAll`, `clearAll`
