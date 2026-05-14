# Дизайн: Мобильное отображение страницы /results

> **Дата:** 2026-05-14  
> **Статус:** Approved (вариант Б — карточки отрезков)

---

## Контекст

Страница `/results` на мобильном (~390px) выглядела неудовлетворительно: контейнер с горизонтальным скроллом, бар-чарт сжат до нечитаемых размеров, таблица сегментов (6 колонок) выходила за экран, блоки статистики не влезали. Выбран дизайн «Вариант Б — карточки отрезков» для детальной панели.

---

## Затронутые файлы

| Файл | Изменение |
|------|-----------|
| `static/css/analytics.css` | Добавить мобильные стили в уже существующий `@media (max-width: 640px)` блок |
| `static/js/analytics-results.js` | Изменить `buildDetailPanelHTML` (новая структура стат-блоков) |

---

## Что меняется

### 1. Страница в целом (`≤640px`)

- `.container`: `border-radius: 0`, `box-shadow: none`, `margin: 0`, `padding: 8px 0`
- `.event-card`: высота `160px` вместо `280px`
- `.detail-panel-row > td`: padding `10px 12px` вместо `20px 24px`

### 2. Стат-блоки детальной панели (JS + CSS)

**Текущая структура** — строки `detail-stat-row` с label/value.  
**Новая структура** — два компактных блока `.detail-stat-tablet`:

```html
<div class="detail-stats-grid">
  <div class="detail-stat-tablet detail-stat-tablet--gun">
    <div class="detail-stat-tablet__label">Официальное</div>
    <div class="detail-stat-tablet__time">{timeGun}</div>
    <div class="detail-stat-tablet__pace">{paceGun}</div>
    <div class="detail-stat-tablet__ranks">
      Место {rankAbs} · Пол {rankSex} · Кат {rankCat}
    </div>
  </div>
  <div class="detail-stat-tablet detail-stat-tablet--net">
    <div class="detail-stat-tablet__label">Чистое</div>
    <div class="detail-stat-tablet__time">{timeNet}</div>
    <div class="detail-stat-tablet__pace">{paceNet}</div>
    <div class="detail-stat-tablet__ranks">
      Место {rankAbsClean} · Пол {rankSexClean} · Кат {rankCatClean}
    </div>
  </div>
</div>
```

**CSS для новых классов** (работают на всех размерах):

```css
.detail-stats-grid { grid-template-columns: 1fr 1fr; } /* всегда 2 колонки */

.detail-stat-tablet {
    background: white;
    border-radius: 8px;
    padding: 10px 12px;
    text-align: center;
}
.detail-stat-tablet--gun { border-top: 3px solid var(--primary-color); }
.detail-stat-tablet--net { border-top: 3px solid #4a9eff; }

.detail-stat-tablet__label {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}
.detail-stat-tablet--gun .detail-stat-tablet__label { color: var(--primary-color); }
.detail-stat-tablet--net .detail-stat-tablet__label { color: #4a9eff; }

.detail-stat-tablet__time {
    font-size: 20px;
    font-weight: 700;
    color: #222;
    line-height: 1.1;
}
.detail-stat-tablet--net .detail-stat-tablet__time { color: #4a9eff; }

.detail-stat-tablet__pace {
    font-size: 11px;
    color: #888;
    margin-top: 2px;
}
.detail-stat-tablet__ranks {
    font-size: 10px;
    color: #aaa;
    margin-top: 4px;
    line-height: 1.4;
}
.detail-stat-tablet__ranks strong { color: #444; }

@media (max-width: 640px) {
    .detail-stat-tablet { padding: 8px 8px; }
    .detail-stat-tablet__time { font-size: 16px; }
    .detail-stat-tablet__pace { font-size: 9px; }
    .detail-stat-tablet__ranks { font-size: 9px; }
}
```

> **Важно:** убрать старые стили `.detail-stat-block`, `.detail-stat-row`, `.detail-stat-label`, `.detail-stat-value` — они больше не используются.

### 3. Бар-чарт: горизонтальный скролл на мобильном

```css
@media (max-width: 640px) {
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
}
```

Бары больше не сжимаются — каждый минимум 52px, чарт листается свайпом.

### 4. Таблицы сегментов: card layout на мобильном (CSS-only)

Каждая строка `<tr>` → двухстрочная карточка:
- Строка 1: название отрезка | время | темп мин/км  
- Строка 2 (мелкий серый): Абс N · Пол М#N · Кат #N

```css
@media (max-width: 640px) {
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

    /* Строка 1 */
    .segments-table tbody td:nth-child(1) { /* название */
        grid-column: 1; grid-row: 1;
        font-size: 10px; color: #bbb;
        align-self: center;
    }
    .segments-table tbody td:nth-child(2) { /* время */
        grid-column: 2; grid-row: 1;
        font-size: 10px; font-weight: 600;
        text-align: right; padding-right: 10px;
        align-self: center;
    }
    .segments-table tbody td:nth-child(3) { /* темп */
        grid-column: 3; grid-row: 1;
        font-size: 10px; font-weight: 700;
        text-align: right;
        align-self: center;
    }

    /* Строка 2: ранги */
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

    /* Бейджи рангов: убрать фон, оставить цифру */
    .segments-table tbody .seg-rank-badge {
        background: transparent !important;
        padding: 0;
        font-size: 8px;
        font-weight: 600;
    }
}
```

---

## Граничные случаи

| Ситуация | Поведение |
|----------|-----------|
| `timeGun` / `timeNet` отсутствует | Показывается `—` |
| `rankCat` пустой | `Кат —` |
| 1 КТ (Весна 5 км) | 2 бара в чарте, скролл не нужен но работает корректно |
| 7 КТ (Первомайский) | 7 баров, ~364px min-width → скролл |
| Десктоп >640px | Новые стат-блоки работают в 2 колонки без изменений |

---

## Верификация

1. **DevTools → viewport 390px → /results**:
   - Нет горизонтального скролла у страницы
   - Список участников: карточки (Место + Имя + Оф/Чист время)
   - Клик на карточку → детальная панель открывается полной шириной
   - Стат-блоки: 2 таблетки рядом (Официальное | Чистое)
   - Бар-чарт: листается горизонтально, каждый бар ≥52px
   - Каждый отрезок в таблице: 2 строки (название+время+темп | ранги)

2. **Десктоп >640px**: стат-блоки выглядят корректно (2 таблетки в сетке)
