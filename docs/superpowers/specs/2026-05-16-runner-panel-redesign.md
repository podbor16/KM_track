# Спека: редизайн панели участника (Runner Panel)

## Контекст

Текущая панель участника (`#runner-panel`) использует inline-стили и устаревшую верстку. Задача — заменить `buildPopupContent()` на современную карточку «Clean Minimal» (вариант C), адаптивную для мобильного и десктопного вида.

---

## Дизайн

### Токены
- Акцент: `#EE2D62`
- Фон карточки: `#fff`
- Шрифт: `'HouschkaRoundedAlt', 'Inter', Arial, sans-serif`

### Анатомия карточки

```
┌─────────────────────────────────────────┐
│ [●9910]  Иванов Михаил        [Бежит]   │  ← TOP ROW
│          М35–39 · Старт 10:02:15        │
├──────────────────────────────────────┤
│   5:12     14.5/21.1    47/312          │  ← STATS (3 col mobile / 4 col desktop)
│   Темп       км          Место          │
├──────────────────────────────────────┤
│  Последняя КТ · КТ3 · 14.5 км  1:15:34 │  ← KT BLOCK
│                               5:12 м/км │
│ [47/312] [38/248] [12/67]               │  ← RANKS ROW
│  Абсолют   Пол    Катег.                │
├──────────────────────────────────────┤
│  Прогноз финиша        1:39:45          │  ← ETA (розовый фон)
│                    финиш в 11:42:00     │
└─────────────────────────────────────────┘
```

**Десктоп** (viewport ≥ 640px): тело карточки — 2 колонки (KT block слева, Ranks справа, ETA на всю ширину); 4-я стат-ячейка «Время КТ».

**Мобильный** (< 640px): 3-col stats, KT/ranks/ETA в одну колонку.

---

## Состояния карточки

### `running` / `started`
- TOP: имя, номер, категория, время старта, пилюля «Бежит»
- STATS: темп | пройдено/дистанция | место в абсолюте [| время КТ на десктопе]
- KT BLOCK: последняя КТ (имя, дистанция, время, темп). Если КТ нет — скрыт
- RANKS: абсолют / пол / категория на последней КТ. Если нет данных — скрыт
- ETA: результат крупно + астрономическое время мелко. Если нет прогноза — скрыт

### `finished`
- TOP: пилюля «Финишировал»
- STATS: темп (финишный avg) | дистанция | место абсолют [| чистое время на десктопе]
- KT BLOCK: скрыт
- RANKS: абсолют / пол / категория (финишные)
- ETA: заменён блоком RESULT — «Результат» + `time_gun_finish` крупно + `time_clear_finish` мелко

### `not_started`
- TOP: пилюля «Не стартовал»
- STATS: пусто
- KT/RANKS/ETA: скрыты
- Только статусная строка

---

## Файлы

| Файл | Изменение |
|------|-----------|
| `static/css/tracker.css` | Добавить блок `.card-c` (новые стили) после существующих панельных стилей |
| `static/js/tracker-map.js` | Заменить `buildPopupContent()` целиком; добавить `card-c--desktop` логику в `showRunnerPanel()` |
| `templates/tracker.html` | Не меняется (структура `#runner-panel` остаётся) |

---

## CSS-классы (новые)

```
.card-c                   — корень карточки
.card-c--desktop          — модификатор десктопа (JS-класс, window.innerWidth >= 640)
.card-c__top              — строка с кружком, именем, пилюлей
.card-c__circle           — кружок-бейдж (номер участника, цвет по статусу)
.card-c__name             — имя
.card-c__sub              — подстрока (категория · старт)
.card-c__pill             — статусная пилюля
.card-c__stats-grid       — сетка статистики (3-col / 4-col desktop)
.card-c__stat             — ячейка статистики
.card-c__stat-val         — значение
.card-c__stat-lbl         — подпись
.card-c__body             — тело (flex-col / grid desktop)
.card-c__kt-block         — блок последней КТ
.card-c__kt-label         — «Последняя КТ»
.card-c__kt-name          — имя КТ + дистанция
.card-c__kt-time          — время на КТ
.card-c__kt-pace          — темп до КТ
.card-c__ranks-row        — строка с тремя ячейками мест
.card-c__rank             — ячейка места
.card-c__rank-val         — значение места
.card-c__rank-lbl         — подпись места
.card-c__eta              — ETA-полоса (розовый фон)
.card-c__eta-lbl          — «Прогноз финиша» (жирный)
.card-c__eta-vals         — обёртка правой части ETA
.card-c__eta-val          — результат крупно
.card-c__eta-time         — астрономическое время мелко
```

---

## Логика `showRunnerPanel()`

```javascript
function showRunnerPanel(runner) {
    const panel = document.getElementById('runner-panel');
    const content = document.getElementById('runner-panel-content');
    content.innerHTML = buildPopupContent(runner);
    // десктопный модификатор
    const card = content.querySelector('.card-c');
    if (card) {
        card.classList.toggle('card-c--desktop', window.innerWidth >= 640);
    }
    panel.classList.remove('runner-panel--hidden');
    // z-index маркера (существующая логика) — не меняется
}
```

---

## Данные из `runner`

| Поле | Используется |
|------|-------------|
| `runner.start_number` | кружок-бейдж, подстрока |
| `runner.full_name` | имя |
| `runner.category` | `KMUtils.normalizeCategory(runner.category)` |
| `runner.status` | статус пилюли, ветвление |
| `runner.time_clear_start_s` | время старта (через `raceGunUnixMs`) |
| `runner.current_pace` | темп |
| `runner.current_distance` | пройдено км |
| `runner.rank_absolute` | место абсолют |
| `runner.rank_sex` | место пол |
| `runner.rank_category` | место категория |
| `getLastCheckpoint(runner)` | КТ-блок |
| `getKtRanks(runner, cp.code)` | ранги на КТ |
| `runner.last_kt_unix_ms` | для расчёта ETA |
| `runner.speed` | для расчёта ETA |
| `runner.time_gun_finish` | финишное время |
| `runner.time_clear_finish` | чистое время финиша |

---

## Цвет кружка-бейджа

Использовать существующую функцию `getStatusColor(runner.status, runner.lap ?? 0)` — та же логика что у маркеров на карте.

---

## Верификация

1. Запустить сервер: `conda run -n base python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000`
2. Открыть `http://localhost:8000/tracker?event_id=<id>`
3. Кликнуть маркер бегущего участника → должна появиться карточка card-c со всеми блоками
4. Проверить на мобильной ширине (DevTools, 375px) — 3-col stats, одна колонка тела
5. Проверить на десктопной ширине (1280px) — 4-col stats, 2-col тело
6. Кликнуть финишировавшего участника — RANKS с финишными местами, блок RESULT вместо ETA
7. Кликнуть не стартовавшего — только пилюля, нет КТ/RANKS/ETA
