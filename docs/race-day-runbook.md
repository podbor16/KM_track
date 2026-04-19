# Документация: Подготовка и запуск трекера на забеге

---

## Быстрый старт (день забега)

```bash
# Терминал 1 — загрузчик данных из Copernico (запустить за 5 мин до старта)
python load_race_results.py --config config/events/night_run.yaml --distance "5 км" --interval 2

# Терминал 2 — веб-приложение трекера
python app.py
```

**Трекер:** http://localhost:8000/tracker?event_id=104  
**API docs:** http://localhost:8000/docs

---

## Что нужно обновить перед каждым забегом

### 1. Открыть YAML-файл события в `config/events/`

```yaml
# config/events/night_run.yaml
year: 2026                    # ← обновить год
event_date: "2026-03-29"      # ← обновить дату
db_event_id: 104              # ← обновить ID из таблицы events
copernico:
  race_id: "--2026-67178"     # ← обновить ID из Copernico
```

**Файлы событий:**
| Файл | Событие | Отслеживаемая дистанция |
|------|---------|------------------------|
| `config/events/night_run.yaml` | Ночной забег | 5 км |
| `config/events/vesna.yaml` | Весна | 5 км |
| `config/events/colorful_run.yaml` | Красочный забег | 5 км |
| `config/events/women7.yaml` | Женская семерка | 7 км |
| `config/events/zhara.yaml` | Жара | 5 км, 21.1 км |
| `config/events/kids.yaml` | Детский забег | 1 км |
| `config/events/x_trail.yaml` | Х Трейл (показ: Забег Икс) | 10 км |
| `config/events/snow7.yaml` | Снежная семерка | 7 км |

### 2. В таблице `events` — убедиться что запись для нового события существует

```sql
SELECT id, event_name, event_distance, event_date, checkpoint_distances
FROM events WHERE event_year = 2026 AND event_name = 'Ночной забег';
```

ID из этой записи → `db_event_id` в YAML.

---

## Режимы запуска `load_race_results.py`

### Новый способ (через конфиг)

```bash
# Инициализация (загрузить стартовый список один раз)
python load_race_results.py --config config/events/night_run.yaml --distance "5 км" --init

# Непрерывное обновление во время забега
python load_race_results.py --config config/events/night_run.yaml --distance "5 км" --interval 2

# Жара — две дистанции, два терминала
python load_race_results.py --config config/events/zhara.yaml --distance "21.1 км" --interval 2
python load_race_results.py --config config/events/zhara.yaml --distance "5 км" --interval 2
```

### Старый способ (обратная совместимость)

```bash
python load_race_results.py --event-id 104 --interval 2
```

### Все аргументы

| Аргумент | Назначение | Когда |
|----------|-----------|-------|
| `--config path` | Путь к YAML события | рекомендуется |
| `--distance "5 км"` | Дистанция из YAML | обязателен с --config |
| `--event-id 104` | ID события в БД (legacy) | без --config |
| `--init` | Загрузить всех один раз | за день до забега |
| `--interval 2` | Обновление каждые N сек | во время забега |
| `--reset-cache 300` | Перезагрузка кэша БД (сек) | по умолчанию 300 |
| `--debug` | Подробные DEBUG-логи | при отладке |

---

## Поток данных: Copernico → БД → Трекер

```
Copernico API
    ↓
GET /api/races/{race_id}/preset/{login}:::{preset}/{event}
    ↓
load_race_results.py (каждые 2 сек)
    ├── Конвертация полей (ms → HH:MM:SS, gender → Мужчина/Женщина)
    ├── Вычисление темпов (finish_pace, pace_avg_kt1...kt5)
    └── Вычисление мест/рангов (_recalculate_ranks)
    ↓
MySQL: таблица `results` + `result_segments`
    ↓
FastAPI: GET /api/event-results?event_id=104
    ↓
tracker.js: анимация маркеров на карте Leaflet
```

---

## Поля из Copernico API (сырые данные)

| Поле Copernico | Тип | Описание |
|----------------|-----|----------|
| `dorsal` | string | Стартовый номер |
| `surname` / `name` | string | Фамилия / Имя |
| `gender` | 'male'/'female' | Пол |
| `birthdate` | 'YYYY-MM-DD' | Дата рождения |
| `category` | string | Категория от Copernico (игнорируется — пересчитывается) |
| `status` | string | 'finished', 'running', 'dnf', 'dsq', 'notstarted' |
| `times.official_:::start:::` | int (ms) | Gun time старта |
| `times.real_:::start:::` | int (ms) | Chip time старта |
| `times.official_:::finish:::` | int (ms) | Gun time финиша |
| `times.real_:::finish:::` | int (ms) | Chip time финиша |
| `times.real_kt1` ... `times.real_kt5` | int (ms) | Chip времена КТ |

---

## Что вычисляется программно

| Поле в БД | Как вычисляется |
|-----------|----------------|
| `category` | `calculate_age_group(birthdate, sex)` |
| `race_status` | `convert_status(copernico_status)` |
| `sex` | `convert_gender(gender)` — 'Мужчина'/'Женщина' |
| `time_gun_start/finish` | `milliseconds_to_time(ms)` |
| `time_clear_start/finish` | `milliseconds_to_time(ms)` |
| `finish_pace_avg_gun/clean` | `time_sec / distance_km` → мин:сек/км |
| `time_clear_kt1...kt5` | `milliseconds_to_time(ms)` |
| `pace_avg_kt1...kt5` | `kt_time_sec / checkpoint_dist[i]` |
| `rank_*` (gun + clean + kt) | ранжирование среди финишировавших |
| `result_segments.*` | все пары точек, ранги отдельно на каждый segment_code |

---

## Таблицы БД

### `results` — основная таблица

```
id, event_id, start_number, surname, name, birthday, sex, category, race_status
time_gun_start, time_clear_start, time_gun_finish, time_clear_finish
finish_pace_avg_gun, finish_pace_avg_clean
time_clear_kt1...kt5, pace_avg_kt1...kt5
rank_absolute, rank_sex, rank_category  (gun time)
rank_absolute_clean, rank_sex_clean, rank_category_clean  (chip time)
rank_absolute_kt1...kt5, rank_sex_kt1...kt5, rank_category_kt1...kt5
```

### `result_segments` — сегменты между КТ

```
id, result_id, segment_code, sg_time_clear, sg_pace_avg
sg_rank_absolute, sg_rank_sex, sg_rank_category
```

Все возможные segment_code (до 21 на участника):
```
start-kt1  start-kt2  start-kt3  start-kt4  start-kt5
kt1-kt2    kt1-kt3    kt1-kt4    kt1-kt5    kt1-finish
kt2-kt3    kt2-kt4    kt2-kt5    kt2-finish
kt3-kt4    kt3-kt5    kt3-finish
kt4-kt5    kt4-finish
kt5-finish
```

Ранги считаются **отдельно для каждого segment_code**.

---

## Временная шкала дня забега

| Время | Действие |
|-------|---------|
| День до забега | `--init` — инициализировать стартовый список |
| −30 мин | Запустить `python app.py`, открыть трекер |
| −5 мин | `--interval 2` — запустить непрерывное обновление |
| Старт | Маркеры начинают движение, данные обновляются каждые 2 сек |
| После последнего финиша | Ctrl+C на `load_race_results.py` |

---

## Чек-лист перед запуском

- [ ] Запись в `events` для нового события (`id`, `checkpoint_distances` в JSON)
- [ ] YAML-файл обновлён: `year`, `event_date`, `copernico.race_id`, `db_event_id`
- [ ] GPX-файл маршрута лежит по пути из `gpx_file` в YAML
- [ ] Соединение с MySQL работает:
  ```bash
  python -c "from src.analytics.db_connection_optimized import get_pooled_connection; print(get_pooled_connection())"
  ```
- [ ] `--init` прошёл успешно (появились записи в `results`)
- [ ] Трекер открывается: http://localhost:8000/tracker?event_id=104

---

## Что менять каждый год

Только YAML-файлы в `config/events/` — для каждого прошедшего события:
- `year` → новый год
- `event_date` → новая дата
- `copernico.race_id` → новый ID из Copernico
- `db_event_id` → ID новой записи в таблице `events`

Код, шаблоны, `settings.py` — **не трогать** (только если изменился маршрут или дистанция).
