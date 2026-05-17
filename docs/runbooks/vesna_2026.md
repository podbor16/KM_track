# Runbook: Весна 2026 — 17 мая 2026

**Дистанция:** 5 км  
**Событие:** `db_event_id=106`  
**Конфиг:** `config/events/vesna.yaml`  
**Preset:** `config/copernico/km_vesna_5km_2026.yaml`  
**Маршрут:** Старт → Разворот 2.5 км → Финиш

---

## ЗА НЕСКОЛЬКО ДНЕЙ ДО СТАРТА

### 1. Получить `race_id` и создать пресет в Copernico

Когда Copernico выдаст ID забега:
1. Вписать в `config/events/vesna.yaml`:
   ```yaml
   copernico:
     race_id: <ID_ИЗ_COPERNICO>
   ```
2. В интерфейсе Copernico создать пресет `km_vesna_5km_2026` с нужными полями (старт, финиш, chip-старт, chip-финиш, КТ разворота)

### 2. Инспектировать поля пресета из Copernico

```bash
cd c:\Users\podbo\Работа\КРАСМАРАФОН\KM_track
python scripts/prerace_check.py --config config/events/vesna.yaml --distance "5 км" --inspect
```

Пример вывода:
```
--- Временные поля (times.*) ---
  'times.official_:::finish:::': 1600496  <-- ЕСТЬ ДАННЫЕ
  'times.official_:::start:::': 12459     <-- ЕСТЬ ДАННЫЕ
  'times.real_:::finish:::': 1588037      <-- ЕСТЬ ДАННЫЕ
  'times.real_:::start:::': 0             <-- ЕСТЬ ДАННЫЕ
  'times.official_:::razvorot:::': 750000 <-- ЕСТЬ ДАННЫЕ
  ...
```

По выводу заполнить `config/copernico/km_vesna_5km_2026.yaml`:
```yaml
time_fields:
  gun_start:   "times.official_:::start:::"
  gun_finish:  "times.official_:::finish:::"
  chip_start:  "times.real_:::start:::"     # реальное имя из вывода inspect
  chip_finish: "times.real_:::finish:::"    # реальное имя из вывода inspect

checkpoint_fields:
  kt1: "times.official_:::razvorot:::"     # реальное имя из вывода inspect
```

---

## НАКАНУНЕ (16 мая вечером)

### 3. Запустить предстартовую проверку

```bash
python scripts/prerace_check.py --config config/events/vesna.yaml --distance "5 км"
```

Ожидаемый результат до `--init`:
```
[A] Конфиг    OK   OK
[B] Файлы     OK   GPX валиден (vesna.gpx)
[C] БД        OK   id=106, КТ 0/2.5/5.0 совпадают
[D] Участники WARN 0 записей — запустите --init
[E] API       SKIP --server не указан
[F] Copernico OK   race_id=..., HTTP 200
[G] Пресет    OK   km_vesna_5km_2026.yaml найден
[G] Поля API  OK   Все ожидаемые поля присутствуют
```

Если `[A]`, `[B]`, `[G]` FAIL — разобраться до следующего шага.

### 4. Загрузить стартовый список (`--init`)

```bash
python load_race_results.py --config config/events/vesna.yaml --distance "5 км" --init
```

Ожидаемый вывод: `Загружено NNN участников (event_id=106)`

### 5. Повторная проверка (блок D должен стать OK)

```bash
python scripts/prerace_check.py --config config/events/vesna.yaml --distance "5 км"
```

### 6. Визуальная проверка браузера

Запустить сервер: `python -m uvicorn src.main:app --reload --port 8000`

| Страница | Что проверить |
|----------|--------------|
| `/tracker` | Название "Весна 2026", маршрут на карте, список участников |
| `/results` | Таблица с участниками, статус "Not started" |
| `/start-list` | Стартовый список загружен, имена не пустые |
| `/analytics` | Открывается без ошибок |
| `/business-analytics` | Редирект на логин |

DevTools Console (F12): **0 ошибок**, допустимы только info-логи.

### 7. Серверные логи (uvicorn)

**Должно быть:**
```
Application startup complete.
[OK] Подключено к БД
КТ-маппинг из preset: [(1, 'times.official_:::razvorot:::')]
```

**Не должно быть:** `❌`, `Error`, `Traceback`, `WARNING`

---

## УТРО 17 МАЯ — ЗАПУСК

### 8. Запустить loader на VPS (рекомендуется)

Loader работает на VPS — стабильно, не зависит от wifi ноутбука.

```bash
# Первый раз на этом VPS (устанавливает systemd-сервис):
python deploy/ssh_loader.py setup

# Инициализация + старт для vesna 5 км:
python deploy/ssh_loader.py init vesna_5km

# Проверить статус:
python deploy/ssh_loader.py status

# Просмотр логов:
python deploy/ssh_loader.py logs vesna_5km
```

**Альтернатива: локальный запуск (запасной вариант)**

Если VPS недоступен — запустить локально в двух терминалах:

*Терминал 1 — FastAPI (уже запущен на VPS, этот вариант только для локальной разработки):*
```bash
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2
```

*Терминал 2 — Loader:*
```bash
python load_race_results.py --config config/events/vesna.yaml --distance "5 км" --interval 5 --debug
```

Если нужен VPN-обход (БД на удалённом хосте) — запустить от Администратора:
```bash
python load_race_results.py --config config/events/vesna.yaml --distance "5 км" --interval 5 --debug --fix-routing
```

### 9. До старта — норма в логах

```
Цикл #1: fetch=1.5s calc=0.2s ranks=0.1s total=1.8s | updated=0r/0s kt_reads=0
```
Нули — нормально: никто ещё не стартовал.

---

## В МОМЕНТ ВЫСТРЕЛА

В течение 1–2 минут в логах loader должно появиться:
```
gun_time_utc сохранён: 2026-05-17T...Z
```
Именно с этого момента маркеры начнут двигаться.

Если через 5 минут нет — Copernico ещё не зафиксировал gunTime. Ждать.

---

## ВО ВРЕМЯ ГОНКИ

**Логи Loader (каждые 5 сек):**
```
Цикл #47: fetch=1.2s calc=0.8s ranks=1.5s total=3.5s | updated=34r/10s kt_reads=28
```
- `kt_reads=N` — N человек прошли Разворот 2.5 км
- `total < 5s` — нормально

**Трекер `/tracker`:**
- Маркер движется к развороту, потом обратно к финишу
- Попап: «КТ: Разворот 2.5 км», темп участка, прогноз финиша

---

## ТРЕВОЖНЫЕ СИГНАЛЫ

| Что в логах | Диагноз | Действие |
|-------------|---------|---------|
| `❌ Ошибка Copernico: 429` | Rate limit | Ctrl+C, перезапустить с `--interval 10` |
| `❌ Ошибка Copernico: 503` | Перегруз Copernico | Ждать 30 сек, повторить |
| `Traceback` | Падение loader | Перезапустить; если повторяется — чинить |
| Маркеры не двигаются 10+ мин | gun_time не пришёл или нет считывателей | Проверить логи |
| `WARN` о БД соединении | Пул исчерпан | Перезапустить uvicorn |

---

## ПОСЛЕ ФИНИША

Когда все финишировали (~1 час после старта):

1. В `/results` — все финишировавшие имеют `time_gun_finish` и `time_clear_finish` (не прочерки)
2. Ранги заполнены
3. В `/tracker` — все маркеры на финише (зелёный кружок)

Если `time_clear_finish` NULL у финишировавших:
```bash
# Адаптировать EVENT_IDS = {106: 5.0} в начале скрипта
python scripts/fix_post_race.py
```

---

## ПОСТГОНОЧНЫЕ ЗАДАЧИ

- [ ] Проверить `/results` — нет NULL в `time_gun_finish`, `time_clear_finish`
- [ ] Проверить сегменты — ранги не прочерки
- [ ] Обновить `is_active: false` в `config/events/vesna.yaml`
- [ ] Сохранить сессию в Obsidian: `sessions/YYYY-MM-DD-vesna-postrace.md`
