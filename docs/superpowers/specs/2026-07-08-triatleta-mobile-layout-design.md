# Дизайн: мобильный layout страницы triatleta /24h

**Дата:** 2026-07-08  
**Статус:** approved

## Проблема

На мобилке (≤640px) страница `/tri/results` имеет две категории проблем:

1. **Табы не влезают** — 4 таба («Расстояние», «Отрезки», «График», «Круги») + `padding: 0 24px` выходят за 375px. `body { overflow-x: hidden }` блокирует скролл → табы обрезаются, без возможности переключиться.
2. **Сабтабы графика** — `.tri-chart-subtabs` («Скорость», «Дистанция», «Позиция») та же проблема.
3. **Canvas графика** — `layout: { padding: { right: 160 } }` зарезервирован для десктопных плашек с именами; на мобилке лишний, сжимает рабочую область графика.

## Решение (вариант C)

Минимальный CSS-фикс + одна строка JS. HTML не трогаем.

### 1. `body` — заменить `overflow-x: hidden` → `overflow-x: clip`

`clip` так же предотвращает горизонтальный скролл страницы, но **не** создаёт новый scroll-контейнер, поэтому дочерние элементы с `overflow-x: auto` работают корректно.

```css
/* было */
body { overflow-x: hidden; }

/* станет */
body { overflow-x: clip; }
```

### 2. `.tri-page-tabs` — горизонтальный скролл на мобилке

В `@media (max-width: 640px)`:

```css
.tri-page-tabs {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    padding: 0 12px;       /* было 0 24px */
}
.tri-page-tabs::-webkit-scrollbar { display: none; }
.tri-page-tab {
    padding: 9px 14px;     /* было 12px 20px */
    font-size: 13px;       /* было 15px */
    flex-shrink: 0;
}
```

### 3. `.tri-chart-subtabs` — горизонтальный скролл на мобилке

В `@media (max-width: 640px)`:

```css
.tri-chart-subtabs {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    flex-wrap: nowrap;
}
.tri-chart-subtabs::-webkit-scrollbar { display: none; }
.tri-chart-subtab {
    flex-shrink: 0;
}
```

### 4. Chart.js — убрать правый padding на мобилке

В функции создания каждого из трёх чартов (`renderChart`, `renderDistanceChart`, `renderPositionChart`) добавить условие:

```js
layout: { padding: { right: isMobile() ? 0 : 160 } }
```

Это затрагивает только чарты «Скорость» (строка 978) и «Позиция» (строка 1305) — они используют `padding.right: 160`. «Дистанция» (`renderDistanceChart`) этого padding не имеет — её не трогаем.

## Затрагиваемые файлы

| Файл | Что меняем |
|------|-----------|
| `static/css/tri_results.css` | `body overflow-x`, мобильные стили табов и сабтабов |
| `templates/race_triatleta/tri_results.html` | `layout.padding.right` в `renderChart` и `renderPositionChart` |

## Не трогаем

- HTML-структуру табов
- Логику переключения табов в JS
- Десктопные стили (только `@media 640px` и `body`)
- Другие страницы (siberman, krasmarafon)

## Критерии готовности

- [ ] На 375px все 4 таба доступны (через скролл или влезают)
- [ ] Сабтабы графика доступны аналогично
- [ ] Графики не обрезаются по правому краю
- [ ] Десктоп не сломан
