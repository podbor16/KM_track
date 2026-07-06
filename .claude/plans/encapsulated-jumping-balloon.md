# План: Трекер — фиксация анимации и отладка

## Статус задач

| Задача | Статус |
|--------|--------|
| MCP MySQL в `.mcp.json` | ✅ Выполнено |
| `get_checkpoint_distances()` и `get_category_avg_paces()` в db_connection_optimized.py | ✅ Выполнено |
| `calculate_live_position()` в runners_service.py | ✅ Выполнено (возвращает 3-tuple) |
| Подключить расчёт скорости в `/api/runners` | ✅ Выполнено |
| Unit-тесты (test_pace_calculator, test_routes_service, test_runners_service) | ✅ Выполнено |
| **Исправить анимацию в tracker.js** | ❌ Не выполнено — ROOT CAUSE |
| Добавить темп в popup | ❌ Не выполнено |
| Добавить отладку в консоль браузера | ❌ Не выполнено |

---

## Контекст — корневая причина визуальной проблемы

Фронтенд (`static/js/tracker.js`) использует `/api/event-results?event_id=104`, **не** `/api/runners`.
Анимация в `updateRunnerMarkerPosition()` (строки ~673–703) хардкодирует `currentProgress + 0.3` для ВСЕХ бегунов вне зависимости от скорости:

```javascript
// Обе ветки (hasKT1 и просто running) используют +0.3%:
targetProgressPercent = Math.min(100, currentProgress + 0.3);
targetProgressPercent = Math.min(maxTargetPercent, currentProgress + 0.3);
```

Значение 0.3% при маршруте 5 км соответствует ~27 км/ч — слишком быстро и одинаково для всех.

---

## Задача: исправление анимации и отладка

### Шаг 1: Добавить `speed` и `current_pace` в `/api/event-results` (router.py)

**Файл:** `src/tracker/router.py` — endpoint `/api/event-results` (строки ~1045–1137)

Перед циклом построения result_items добавить:
```python
# Один раз на запрос:
event_info = get_event_info(event_name or event_id, datetime.now().year)
race_date = event_info['event_date'] if event_info else date.today()
checkpoint_distances = get_checkpoint_distances(event_info['id']) if event_info else [0.0, 2.5, 5.0]
event_distance_km = event_info.get('event_distance', 5.0) if event_info else 5.0
category_speeds = get_category_avg_paces(
    event_info.get('event_name', ''), event_distance_km, datetime.now().year - 1
) if event_info else {}
```

Внутри цикла для каждого runner вызвать `calculate_live_position()`:
```python
from src.tracker.services.runners_service import calculate_live_position
speed_kmh, current_dist, pace_str = calculate_live_position(
    runner, checkpoint_distances, race_date, category_speeds
)
result_item['speed'] = round(speed_kmh, 2)
result_item['current_distance'] = round(current_dist, 3)
result_item['current_pace'] = pace_str
```

**Импорты** которые уже должны быть в router.py:
- `from src.analytics.db_connection_optimized import get_event_info, get_checkpoint_distances, get_category_avg_paces`
- `from src.tracker.services.runners_service import calculate_live_position`

### Шаг 2: Принять `speed` в маппинге данных в tracker.js

**Файл:** `static/js/tracker.js` — блок маппинга ответа API (~строки 430–472)

Добавить в объект runner:
```javascript
speed:            runner.speed || 10.0,        // км/ч от бэкенда
current_distance: runner.current_distance || 0, // км
current_pace:     runner.current_pace || '6:00', // строка "мм:сс"
```

### Шаг 3: Заменить `+0.3` на speed-based инкремент в `updateRunnerMarkerPosition()`

**Файл:** `static/js/tracker.js` — функция `updateRunnerMarkerPosition()` (~строки 643–740)

**Формула для инкремента прогресса:**
```javascript
const speedKmh = runner.speed || 10.0;
const totalDistKm = eventDistance || 5.0;
// UPDATE_INTERVAL = 2000 мс → часы: 2000 / 3_600_000
const progressPerTick = (speedKmh * CONFIG.UPDATE_INTERVAL / 3_600_000) / totalDistKm * 100;
```

Для участника 10 км/ч при 5 км маршруте: `10 * 2/3600 / 5 * 100 = 0.111%` — корректно (в ~2.7 раза медленнее текущего 0.3%).

**Замена в двух местах** (строки с `currentProgress + 0.3`):

```javascript
// БЫЛО:
targetProgressPercent = Math.min(100, currentProgress + 0.3);

// СТАЛО:
const progressPerTick = (runner.speed || 10.0) * CONFIG.UPDATE_INTERVAL / 3_600_000 / (eventDistance || 5.0) * 100;
targetProgressPercent = Math.min(100, currentProgress + progressPerTick);
```

```javascript
// БЫЛО:
targetProgressPercent = Math.min(maxTargetPercent, currentProgress + 0.3);

// СТАЛО:
const progressPerTick = (runner.speed || 10.0) * CONFIG.UPDATE_INTERVAL / 3_600_000 / (eventDistance || 5.0) * 100;
targetProgressPercent = Math.min(maxTargetPercent, currentProgress + progressPerTick);
```

### Шаг 4: Добавить темп в popup (buildPopupContent)

**Файл:** `static/js/tracker.js` — функция `buildPopupContent()` (~строки 534–622)

В ветке `running/started` после строки с последней КТ добавить:
```javascript
const currentPace = runner.current_pace
    ? `<div><strong>Текущий темп:</strong> ${runner.current_pace} мин/км</div>`
    : '';
```
И вставить `${currentPace}` в `contentHTML` после "Темп на КТ".

### Шаг 5: Добавить отладку в консоль браузера

**Файл:** `static/js/tracker.js` — в начале функции `updateRunnerMarkerPosition()` после вычисления `progressPerTick`:

```javascript
if (s.includes('running') || s.includes('started') || hasKT1) {
    console.log(
        `[Tracker] #${runner.start_number} ${runner.category}:`,
        `speed=${(runner.speed || 10).toFixed(1)} km/h`,
        `dist=${(runner.current_distance || 0).toFixed(2)} km`,
        `pace=${runner.current_pace || '?'}`,
        `progress=${targetProgressPercent.toFixed(2)}%`,
        `tick=${progressPerTick?.toFixed(3)}%`
    );
}
```

---

## Порядок выполнения

1. `src/tracker/router.py` — добавить `speed/current_distance/current_pace` в `/api/event-results`
2. `static/js/tracker.js` — принять новые поля в маппинге
3. `static/js/tracker.js` — заменить `+0.3` на формулу в двух местах
4. `static/js/tracker.js` — добавить темп в popup
5. `static/js/tracker.js` — добавить console.log отладку

---

## Верификация результата

1. Перезапустить сервер: `uvicorn app:app --reload`
2. `GET /api/event-results?event_id=104` → проверить что поле `speed` есть и различается для разных участников
3. Открыть `/tracker` → F12 → Console → видны строки `[Tracker] #... speed=X.X km/h`
4. Сравнить маркер категории "до 49 лет" и "75+": должны двигаться с визуально разной скоростью
5. Проверить popup работающего участника: должно показывать "Текущий темп: X:XX мин/км"
