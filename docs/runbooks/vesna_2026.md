# Runbook: Весна 2026 — 17 мая 2026

**Дистанция:** 5 км  
**Событие:** `db_event_id=106`  
**Конфиг:** `config/events/vesna.yaml`  
**Маршрут:** Старт → Разворот 2.5 км → Финиш (1 КТ между стартом и финишем)

---

## Накануне (16 мая вечером)

### 1. Получить `race_id` из Copernico и заполнить конфиг

Когда Copernico выдаст ID забега — вписать в `config/events/vesna.yaml`:
```yaml
copernico:
  race_id: <ID_ИЗ_COPERNICO>
```

### 2. Запустить предстартовую проверку

```bash
cd c:\Users\podbo\Работа\КРАСМАРАФОН\KM_track
python scripts/prerace_check.py --config config/events/vesna.yaml --distance "5 км"
```

Ожидаемый результат до `--init`:
```
[A] Конфиг.............. OK   OK
[B] Файлы............... OK   GPX валиден (vesna.gpx)
[C] БД.................. OK   id=106, КТ 0/2.5/5.0 совпадают
[D] Участники........... WARN 0 записей — запустите --init
[E] API................. SKIP --server не указан
[F] Copernico........... OK   race_id=..., HTTP 200
```

Если `[A]` или `[B]` FAIL — разобраться до следующего шага.

### 3. Загрузить стартовый список (`--init`)

```bash
python load_race_results.py --config config/events/vesna.yaml --distance "5 км" --init
```

Ожидаемый вывод:
```
Загрузка данных из Copernico...
Загружено NNN участников (event_id=106)
```

### 4. Повторная проверка после `--init`

```bash
python scripts/prerace_check.py --config config/events/vesna.yaml --distance "5 км"
```

Блок `[D]` теперь должен показать `NNN участников`, не WARN.

### 5. Визуальная проверка браузера

Запустить сервер:
```bash
python -m uvicorn src.main:app --reload --port 8000
```

Открыть и проверить:

| Страница | Что проверить |
|----------|--------------|
| `http://localhost:8000/tracker` | Название "Весна", маршрут на карте, список участников |
| `http://localhost:8000/results` | Таблица участников, статус "Not started" |
| `http://localhost:8000/start-list` | Стартовый список загружен |
| `http://localhost:8000/analytics` | Открывается без ошибок |
| `http://localhost:8000/business-analytics` | Редиректит на логин |

DevTools Console (F12): **0 ошибок**, допустимы только info-логи.

### 6. Чеклист серверных логов

**Должно быть:**
```
Application startup complete.
[OK] Подключено к БД
```

**Не должно быть:**
```
❌  Error  Traceback  WARNING (кроме ожидаемых)
```

---

## Утро 17 мая — запуск

### 1. Открыть 2 терминала

**Терминал 1 — FastAPI сервер:**
```bash
cd c:\Users\podbo\Работа\КРАСМАРАФОН\KM_track
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2
```
Ждать: `Application startup complete.`

**Терминал 2 — Loader 5 км:**
```bash
python load_race_results.py --config config/events/vesna.yaml --distance "5 км" --interval 5 --debug
```

Если нужен VPN-обход (БД на удалённом хосте):
```bash
python load_race_results.py --config config/events/vesna.yaml --distance "5 км" --interval 5 --debug --fix-routing
```
(запустить от Администратора)

### 2. До старта — норма в логах

```
Цикл #1: fetch=1.5s calc=0.2s ranks=0.1s total=1.8s | updated=0r/0s kt_reads=0
```
Нули — нормально: никто ещё не стартовал.

---

## В момент выстрела

В течение 1–2 минут в логах loader должно появиться:
```
gun_time_utc сохранён: 2026-05-17T...Z
```
Именно с этого момента маркеры начнут двигаться по карте.

Если через 5 минут после старта строки нет — Copernico ещё не зафиксировал gunTime.  
Маркеры на старте — это нормально, движение начнётся когда появятся считывания КТ.

---

## Во время гонки

**Логи Loader (каждые 5 сек):**
```
Цикл #47: fetch=1.2s calc=0.8s ranks=1.5s total=3.5s | updated=34r/10s kt_reads=28
```
- `kt_reads=N` — N человек прошли КТ "Разворот 2.5 км"
- `total < 5s` — нормально

**Трекер `http://localhost:8000/tracker`:**
- Маркер выбранного участника движется к развороту, потом обратно к финишу
- Попап: «КТ: Разворот 2.5 км», темп участка, прогноз финиша

---

## Тревожные сигналы

| Что в логах | Диагноз | Действие |
|-------------|---------|---------|
| `❌ Ошибка Copernico: 429` | Rate limit | Ctrl+C, перезапустить с `--interval 10` |
| `❌ Ошибка Copernico: 503` | Перегруз Copernico | Ждать 30 сек, повторить |
| `Traceback` | Падение loader | Перезапустить; если повторяется — чинить |
| Маркеры не двигаются 10+ мин | gun_time не пришёл или нет читалок | Проверить логи, убедиться что Copernico работает |
| `WARN` о БД соединении | Пул исчерпан | Перезапустить uvicorn |

---

## После финиша

Когда все финишировали (~1 час после старта), проверить:
1. В `/results` — все финишировавшие имеют `time_gun_finish` и `time_clear_finish`
2. Ранги заполнены (не прочерки)
3. В `/tracker` — все маркеры на финише (зелёный кружок)

Если `time_clear_finish` NULL:
```bash
python scripts/fix_post_race.py  # адаптировать EVENT_IDS для id=106
```

---

## Постгоночные задачи

- [ ] Проверить результаты на `/results` — нет NULL в основных полях
- [ ] Проверить сегменты — ранги заполнены
- [ ] Обновить `is_active: false` в `config/events/vesna.yaml`
- [ ] Сохранить логи сессии в `sessions/`
