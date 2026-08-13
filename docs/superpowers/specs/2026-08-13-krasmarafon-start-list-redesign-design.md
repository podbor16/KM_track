# Редизайн start_list.html (вариант C: полировка бренда) — дизайн

## Контекст

Второй под-проект программы «Редизайн всего сайта Красмарафона, кроме
карточки над трекером и самого трекера» (см. `текущие приоритеты.md` →
КРАСМАРАФОН → Подготовка к Жаре, п.1). Первый под-проект (`results.html`)
уже задеплоен — см.
`docs/superpowers/specs/2026-08-13-krasmarafon-results-redesign-design.md`.
Эта спека закрывает `start_list.html`.

`start_list.html` делит `static/css/analytics.css` с `results.html` —
плоский хэдер таблицы, уплотнённые отступы `.km-th`/`.km-td` и классы
`.km-pills`/`.km-pill` уже существуют в этом файле (задеплоены в прошлом
цикле) и автоматически применились к `start_list.html`, ничего в CSS
менять не нужно. У таблицы нет колонки «Место»/медальных бейджей (это
список регистраций, не результаты) — `.km-rank-medal` здесь не участвует.

## Отличие от results.html

Фильтр «Пол» на `start_list.html` — статичные `<option value="Мужчина">
Мужчины</option>`/`<option value="Женщина">Женщины</option>` прямо в HTML
(не генерируются JS по факту данных, как было на `results.html`). Оба
варианта показаны всегда, независимо от того, есть ли участники этого
пола в текущей выборке. `applyFilters()` не перезаполняет опции пола на
каждый вызов (в отличие от `populateGenderFilter(allRunners)` на
`results.html`) — значит после конвертации в pill-кнопки не будет
естественного цикла перерисовки, который бы сам синхронизировал активный
класс. `setGenderFilter()` должен управлять активным классом сам.

Второе отличие: `switchEvent()` (`analytics-start-list.js:76`) сбрасывает
`document.getElementById('genderFilter').value = ''` при смене события —
обычное присваивание `select.value` НЕ вызывает `onchange`. Pill-версия
сброса должна вести себя так же (не запускать `onGenderChange()`/
`applyFilters()` — они и так вызовутся ниже по цепочке через
`loadRunnersData()`, вызывать их здесь тоже было бы преждевременно,
`allRunners` для нового события ещё не загружен).

## Изменения

### 1. Карточка события (`.km-event-card`)

Тот же паттерн, что и на `results.html`: убираем `.km-event-card`/
`__overlay`/`__controls` из разметки `start_list.html`, селекторы
Событие/Год переезжают в `.km-toolbar` (обычные `.km-select` в
`.km-filter-group`, без обёртки-панели, фонового изображения и без
`.km-select-group` — этот класс давал горизontальную раскладку
специально для панели над баннером, в общем тулбаре не нужен).

**Проверено по всему проекту** (`grep -r km-event-card`/`km-select-group`
по `templates/`) — `start_list.html` был ПОСЛЕДНИМ шаблоном, использующим
оба класса (`results.html` перестал в прошлом цикле). После этого
изменения `.km-event-card`, `.km-event-card__overlay`,
`.km-event-card__controls`, `.km-select-group` в `analytics.css`
(включая их overrides в `@media (max-width: 640px)`) становятся мёртвым
кодом во всём проекте — удаляются тем же коммитом, а не оставляются
«на всякий случай».

### 2. Фильтр «Пол» → pill-кнопки (статичная разметка)

Новая HTML-разметка (вместо `<select id="genderFilter">`):
```html
<div class="km-filter-group">
    <label class="km-label" id="genderFilterLabel">Пол:</label>
    <div class="km-pills" id="genderFilter" data-value="" role="group" aria-labelledby="genderFilterLabel">
        <button type="button" class="km-pill active" data-value="" onclick="setGenderFilter('')">Все</button>
        <button type="button" class="km-pill" data-value="Женщина" onclick="setGenderFilter('Женщина')">Женщины</button>
        <button type="button" class="km-pill" data-value="Мужчина" onclick="setGenderFilter('Мужчина')">Мужчины</button>
    </div>
</div>
```
Кнопки статичные (не генерируются JS) — тот же принцип, что и у исходного
`<select>` с захардкоженными `<option>`. `onclick` напрямую в разметке —
соответствует существующей конвенции файла (`onchange="switchEvent()"`,
`onclick="exportStartListPdf()"` и т.д.), в отличие от `results.html`, где
pill-кнопки генерируются JS и вешают слушателей программно (там иначе
нельзя — кнопок заранее не существует).

**Изменения в `analytics-start-list.js`**:
- `getGenderFilterValue()` — новая, читает `document.getElementById('genderFilter').dataset.value || ''`
- `_setGenderFilterActivePill(value)` — новая, внутренняя: устанавливает
  `container.dataset.value = value`, синхронизирует `.active` класс у
  дочерних `.km-pill` (сравнение `pill.dataset.value === value`). Без
  побочных вызовов — не дёргает `onGenderChange()`/`applyFilters()`
- `setGenderFilter(value)` — новая, публичная (вызывается из `onclick`
  кнопок): `_setGenderFilterActivePill(value)`, затем `onGenderChange()`
  (та же функция, что раньше вызывалась по `onchange` у `<select>`)
- `populateAgeGroups()` (строка ~147) и `applyFilters()` (строка ~293):
  `document.getElementById('genderFilter').value` → `getGenderFilterValue()`
- `updateEventCardBackground()` (строка ~48): гвард `if (!eventCard) return;`
  сразу после `getElementById('eventCard')` — после удаления баннера из
  разметки элемент перестаёт существовать, без гварда упадёт на первом же
  вызове (`DOMContentLoaded` и `switchEvent()`)
- `switchEvent()` (строка ~76): `document.getElementById('genderFilter').value = '';`
  → `_setGenderFilterActivePill('');` (без побочных эффектов — см. раздел
  «Отличие от results.html» выше)

### Не в объёме этой спеки

- Новых CSS-правил не добавляем — `.km-pills`/`.km-pill`, плоский хэдер
  таблицы, плотность уже унаследованы из прошлого цикла. Единственное
  CSS-изменение — удаление подтверждённо мёртвого кода (см. выше)
- Ширина/адаптивность 9-колоночной таблицы на мобильном — не запрошено,
  существующее поведение (`.km-table-wrap { overflow-x: auto }`) не
  трогаем
- Карточка над трекером и сам трекер — исключены с самого начала всей
  программы редизайна
- Остальные страницы (`history.html`, `athlete-profile.html` и т.д.) —
  отдельные будущие под-проекты

## Тестирование

- Unit-тесты на новую pill-логику (`node:vm`, тот же паттерн, что уже
  используется для `results.html`/Siberman JS в проекте) —
  `getGenderFilterValue()`/`setGenderFilter()`/`_setGenderFilterActivePill()`
  корректно переключают активную пилюлю и возвращают значение;
  `setGenderFilter()` вызывает `onGenderChange()`, `_setGenderFilterActivePill()`
  — нет; `applyFilters()`/`populateAgeGroups()` используют новое значение
  так же, как раньше использовали `select.value`
- Визуальная проверка в браузере (agent-browser) — десктоп и мобильная
  ширина, до отчёта о готовности: карточка события без фото рендерится
  чисто, pill-фильтр пола кликабелен и переключает список, смена события
  корректно сбрасывает пилюлю на «Все» без лишнего перерендера
