# Дизайн: Вкладки детальной панели /results (мобильный редизайн v2)

> **Дата:** 2026-05-14
> **Статус:** Approved

---

## Контекст

Предыдущий редизайн (v1) добавил `overflow-x: hidden` на `body` и CSS card-layout, но не устранил причину переполнения: детальная панель содержит элементы с фиксированными горизонтальными размерами (таблет-сетка 2×1fr, бар-чарт с `flex: 0 0 52px`), которые выходят за 390px. Решение — переработать HTML-структуру панели на вкладки и убрать фиксированные px из чарта.

---

## Затронутые файлы

| Файл | Изменение |
|------|-----------|
| `static/js/analytics-results.js` | `buildDetailPanelHTML` — новая tab-структура |
| `static/js/analytics-results.js` | `createSegmentsPanel` — вставка чарта/таблиц в нужные pane |
| `static/js/analytics-results.js` | tab-switching JS (≤15 строк) |
| `static/css/analytics.css` | стили вкладок + mobile/desktop переключение |

---

## HTML-структура детальной панели

```html
<div class="detail-panel-header">
  <div>
    <div class="detail-panel-name">{fullName}</div>
    <div class="detail-panel-meta">{distance} · {gender} · {birthYear} · {status}</div>
  </div>
  <button class="detail-panel-close">&times;</button>
</div>

<div class="detail-tabs">
  <button class="detail-tab active" data-tab="result">Результат</button>
  <button class="detail-tab" data-tab="pace">Темп</button>
  <button class="detail-tab" data-tab="segments">Отрезки</button>
</div>

<div class="detail-tab-pane active" data-pane="result">
  <!-- Вкладка Результат — см. ниже -->
</div>
<div class="detail-tab-pane" data-pane="pace">
  <div class="segments-placeholder pace-placeholder">Загрузка...</div>
</div>
<div class="detail-tab-pane" data-pane="segments">
  <div class="segments-placeholder segs-placeholder">Загрузка...</div>
</div>
```

---

## Вкладка «Результат»

Структура внутри `detail-tab-pane[result]`:

```html
<div class="detail-result-block">
  <div class="detail-result-divider">Официальное</div>
  <div class="detail-result-row">
    <span class="detail-result-label">Время</span>
    <span class="detail-result-value detail-result-value--gun">{timeGun}</span>
  </div>
  <div class="detail-result-row">
    <span class="detail-result-label">Темп</span>
    <span class="detail-result-value detail-result-value--gun">{paceGun}</span>
  </div>
  <div class="detail-result-row">
    <span class="detail-result-label">Место</span>
    <span class="detail-result-value">{rankAbs}</span>
  </div>
  <div class="detail-result-row">
    <span class="detail-result-label">Пол</span>
    <span class="detail-result-value">{rankSex}</span>
  </div>
  <div class="detail-result-row">
    <span class="detail-result-label">Кат.</span>
    <span class="detail-result-value">{rankCat}</span>
  </div>

  <div class="detail-result-divider">Чистое</div>
  <div class="detail-result-row">
    <span class="detail-result-label">Время</span>
    <span class="detail-result-value detail-result-value--net">{timeNet}</span>
  </div>
  <div class="detail-result-row">
    <span class="detail-result-label">Темп</span>
    <span class="detail-result-value detail-result-value--net">{paceNet}</span>
  </div>
  <div class="detail-result-row">
    <span class="detail-result-label">Место</span>
    <span class="detail-result-value">{rankAbsClean}</span>
  </div>
  <div class="detail-result-row">
    <span class="detail-result-label">Пол</span>
    <span class="detail-result-value">{rankSexClean}</span>
  </div>
  <div class="detail-result-row">
    <span class="detail-result-label">Кат.</span>
    <span class="detail-result-value">{rankCatClean}</span>
  </div>
</div>
```

**Переменные** (те же что использует текущий `buildDetailPanelHTML`):
`timeGun`, `timeNet`, `paceGun`, `paceNet`, `rankAbs`, `rankSex`, `rankCat`, `rankAbsClean`, `rankSexClean`, `rankCatClean`

---

## Вкладка «Темп»

`createSegmentsPanel` находит `.pace-placeholder` внутри `detail-tab-pane[data-pane="pace"]` и заменяет его на `pace-chart-wrapper`.

**Изменение в бар-чарте:** `pace-bar-col` получает `flex: 1; min-width: 0` вместо `flex: 0 0 52px; min-width: 52px`. Бары делят доступную ширину поровну — нет горизонтального скролла.

На мобильном `pace-chart-wrapper` НЕ нужен `overflow-x: auto` (убираем для pane-контекста). Ширина чарта = ширина контейнера.

---

## Вкладка «Отрезки»

`createSegmentsPanel` находит `.segs-placeholder` внутри `detail-tab-pane[data-pane="segments"]` и заменяет его на существующий DOM-узел с таблицами (Отрезки + Сплиты от старта). HTML-структура таблиц и CSS card-layout не меняются.

---

## Tab-switching JS

Небольшой делегированный обработчик на `document`, слушает клики на `.detail-tab`:

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

---

## CSS

### Стили вкладок (все вьюпорты)

```css
.detail-tabs {
  display: flex;
  border-bottom: 1px solid #1e2535;
  margin-bottom: 12px;
}
.detail-tab {
  flex: 1;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 8px 4px;
  font-size: 13px;
  color: #888;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.detail-tab.active {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
  font-weight: 600;
}
.detail-tab-pane { display: none; }
.detail-tab-pane.active { display: block; }
```

### Стили вкладки «Результат»

```css
.detail-result-block { padding: 0 4px; }
.detail-result-divider {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #888;
  padding: 8px 0 4px;
  border-bottom: 1px solid #2a2a3e;
  margin-bottom: 4px;
}
.detail-result-divider:first-child { padding-top: 0; }
.detail-result-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
  border-bottom: 1px solid #1e2535;
  font-size: 13px;
}
.detail-result-row:last-child { border-bottom: none; }
.detail-result-label { color: #888; }
.detail-result-value { font-weight: 600; color: #fff; }
.detail-result-value--gun { color: var(--primary-color); }
.detail-result-value--net { color: #4a9eff; }
```

### Десктоп (>640px): показать всё без вкладок

```css
@media (min-width: 641px) {
  .detail-tabs { display: none; }
  .detail-tab-pane { display: block; }
}
```

### Мобильный (≤640px): убрать overflow у чарта (он теперь в pane)

```css
@media (max-width: 640px) {
  .pace-chart-wrapper { overflow-x: visible; }
  .pace-chart { min-width: 0; }
  .pace-bar-col { flex: 1; min-width: 0; }
}
```

---

## Удаляемые стили

После реализации стали неиспользуемыми — удалить из `analytics.css`:

- `.detail-stats-grid` (заменено вкладкой «Результат»)
- `.detail-stat-tablet` и все модификаторы/элементы (`--gun`, `--net`, `__label`, `__time`, `__pace`, `__ranks`)
- Мобильные правила `.detail-stat-tablet` из `@media (max-width: 640px)`
- `overflow-x: hidden` на `html, body` в `@media (max-width: 640px)` — причина устранена

---

## Поведение на десктопе (>640px)

Вкладки скрыты, все три pane видимы одновременно — поведение идентично текущему. Единственная видимая разница: `detail-stats-grid` с таблетами заменён на `detail-result-block` с label/value строками. Структура таблиц и чарта не меняется.

---

## Граничные случаи

| Ситуация | Поведение |
|----------|-----------|
| Нет сегментов | pane «Темп» и «Отрезки» показывают "Данные КТ не найдены" |
| `timeGun` / `timeNet` отсутствует | Показывается `—` |
| 1 отрезок | Один бар `flex: 1`, занимает всю ширину |
| 7 отрезков | 7 баров `flex: 1`, делят ширину поровну — нет скролла |

---

## Верификация

**DevTools → 390px → /results:**
1. Нет горизонтального скролла у страницы
2. Кликнуть на строку участника → панель открывается
3. Вкладка «Результат» активна по умолчанию — виден список label:value (gun красным, net синим)
4. Переключить на «Темп» → бар-чарт без скролла, бары занимают полную ширину
5. Переключить на «Отрезки» → карточки отрезков и сплитов

**Desktop >640px:**
1. Вкладки не видны
2. Все три pane отображаются последовательно (результат → чарт → отрезки)
3. Бар-чарт работает корректно (бары flex:1, нет фиксированных px)
