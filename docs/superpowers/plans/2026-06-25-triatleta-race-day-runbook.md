# Runbook: День старта суточной велогонки Triatleta 24h

**Дата:** 25 июня 2026  
**Старт гонки:** 20:00 Красноярск (13:00 UTC)  
**Сайт:** https://live-race.triatleta.ru/24h  
**VPS:** `ssh root@89.108.88.104`  
**Copernico:** https://copernico.cloud  

> Все команды `mysql` выполняются на VPS через SSH. Пароль берётся из `/opt/km_track/.env`.
> Алиас для удобства (вставить в ssh-сессию):
> ```bash
> alias mq='mysql -u km_analytic -p$(grep DB_PASSWORD /opt/km_track/.env | cut -d= -f2) triatleta_24h'
> ```

---

## За 2 часа до старта (18:00)

### Проверка инфраструктуры

- [ ] **Сайт открывается**
  ```bash
  curl -s -o /dev/null -w "%{http_code}" https://live-race.triatleta.ru/24h
  # Ожидать: 200
  ```

- [ ] **Загрузчик запущен и работает**
  ```bash
  ssh root@89.108.88.104 "systemctl status km_tri_loader@tri_24h --no-pager | head -5"
  # Ожидать: Active: active (running)
  ```

- [ ] **Последние логи загрузчика без ошибок**
  ```bash
  ssh root@89.108.88.104 "journalctl -u km_tri_loader@tri_24h -n 10 --no-pager"
  # Ожидать: "✅ Получено N участников" каждые 30 сек, без ❌
  ```

- [ ] **БД доступна и участники есть**
  ```bash
  ssh root@89.108.88.104 "mq -e 'SELECT COUNT(*) as participants FROM participants; SELECT COUNT(*) as laps FROM laps;'"
  # Ожидать: participants > 0, laps = 0 (до старта)
  ```

- [ ] **API отвечает корректно**
  ```bash
  curl -s https://live-race.triatleta.ru/api/tri/standings | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'standings: {len(d[\"standings\"])} участников')"
  # Ожидать: standings: N участников
  ```

### Инициализация участников (если ещё не сделано)

- [ ] **Через admin-панель** (рекомендуется):

  Открыть https://live-race.triatleta.ru/24h/admin → вкладка «Загрузчик» → кнопка «Инициализация»

- [ ] **Или через SSH:**
  ```bash
  ssh root@89.108.88.104 "cd /opt/km_track && /opt/km_track/venv/bin/python load_tri_results.py --config config/events/tri_24h.yaml --init 2>&1"
  # Ожидать: "Вставлено: N участников"
  ```

---

## Старт гонки (20:00)

- [ ] **Открыть сайт и проверить счётчик**

  https://live-race.triatleta.ru/24h — таймер «Прошло» начинает тикать

- [ ] **Открыть логи в live-режиме**
  ```bash
  ssh root@89.108.88.104 "journalctl -u km_tri_loader@tri_24h -f"
  # Как только появятся круги — увидишь: "💾 Добавлено новых кругов: N"
  ```

---

## Через ~15–20 минут после старта (первые круги)

### Критическая проверка — паттерн кругов

- [ ] **Проверить что Copernico возвращает поля кругов**
  ```bash
  curl -s "https://public-api.copernico.cloud/api/races/triatleta-sutochnaya-velogonka-24-chasa-2026/preset/podbor250718@gmail.com:::tri_24h_2026/24h%20race" \
    | python3 -c "
  import json,sys
  d=json.load(sys.stdin)
  if not d: print('Нет данных'); sys.exit()
  keys=[k for k in d[0] if 'kr' in k]
  print(f'Полей кругов: {len(keys)}')
  if keys: print(f'Первый: {keys[0]}, последний: {keys[-1]}')
  print(f'Значение 1kr: {d[0].get(\"times.official_1kr\")}')
  "
  # Ожидать: "times.official_1kr" и число (мс)
  ```

- [ ] **Если паттерн другой** — исправить `pattern` в `config/copernico/tri_24h_2026.yaml`, затем:
  ```bash
  git add config/copernico/tri_24h_2026.yaml && git commit -m "fix: tri lap pattern" && git push
  ssh root@89.108.88.104 "cd /opt/km_track && git pull && systemctl restart km_tri_loader@tri_24h"
  ```

- [ ] **Проверить что круги записались в БД**
  ```bash
  ssh root@89.108.88.104 "mq -e 'SELECT p.surname, p.name, COUNT(l.id) as laps, MAX(l.cumulative_ms) as elapsed_ms FROM participants p LEFT JOIN laps l ON l.participant_id=p.id GROUP BY p.id ORDER BY laps DESC LIMIT 5;'"
  # Ожидать: laps > 0 у лидеров
  ```

- [ ] **Таблица обновляется на сайте** — https://live-race.triatleta.ru/24h, ненулевые значения кругов

---

## Через ~2 часа после старта (проверка лимита кругов)

- [ ] **Проверить сколько кругов возвращает API**
  ```bash
  curl -s "https://public-api.copernico.cloud/api/races/triatleta-sutochnaya-velogonka-24-chasa-2026/preset/podbor250718@gmail.com:::tri_24h_2026/24h%20race" \
    | python3 -c "
  import json,sys
  d=json.load(sys.stdin)
  keys=sorted([k for k in (d[0] if d else {}) if 'kr' in k])
  print(f'Кругов в API: {len(keys)}, макс поле: {keys[-1] if keys else None}')
  "
  ```

  **Если API возвращает ровно 100 кругов** и лидер уже близко к 100 — действовать по плану:
  → Создать пресет `tri_24h_2026_b` (101–175) в Copernico UI и обновить загрузчик (см. Task 0 в плане).

---

## Мониторинг во время гонки

### Команды для периодической проверки (каждые 2–3 часа)

```bash
# Статус загрузчика
ssh root@89.108.88.104 "systemctl is-active km_tri_loader@tri_24h"

# Последние логи
ssh root@89.108.88.104 "journalctl -u km_tri_loader@tri_24h -n 5 --no-pager"

# Топ-3 по кругам в БД
ssh root@89.108.88.104 "mq -e 'SELECT p.surname, COUNT(l.id) as laps FROM participants p JOIN laps l ON l.participant_id=p.id GROUP BY p.id ORDER BY laps DESC LIMIT 3;'"
```

### Экстренные команды

```bash
# Перезапустить загрузчик
ssh root@89.108.88.104 "systemctl restart km_tri_loader@tri_24h"

# Перезапустить приложение
ssh root@89.108.88.104 "systemctl restart km_track"

# Только ошибки загрузчика
ssh root@89.108.88.104 "journalctl -u km_tri_loader@tri_24h -n 50 --no-pager | grep -E 'ERROR|Error|❌'"

# Проверить FastAPI напрямую (минуя nginx)
ssh root@89.108.88.104 "curl -s http://127.0.0.1:8000/api/tri/standings | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d[\"standings\"]), \"участников\")'"
```

---

## Возможные проблемы и решения

### Загрузчик упал (inactive / failed)

```bash
ssh root@89.108.88.104 "journalctl -u km_tri_loader@tri_24h -n 20 --no-pager"
# Найти причину, затем:
ssh root@89.108.88.104 "systemctl restart km_tri_loader@tri_24h"
```

### Copernico API не отвечает (timeout в логах)

Загрузчик повторит сам через 30 сек. Проверить вручную:
```bash
curl -v "https://public-api.copernico.cloud/api/races/triatleta-sutochnaya-velogonka-24-chasa-2026/preset/podbor250718@gmail.com:::tri_24h_2026/24h%20race" 2>&1 | head -15
```

### Паттерн кругов неверный (0 кругов в БД при наличии на Copernico)

1. Запросить API и найти реальный ключ: `... | python3 -c "import json,sys; d=json.load(sys.stdin); print([k for k in d[0] if 'official' in k])"`
2. Обновить `pattern` в `config/copernico/tri_24h_2026.yaml`
3. `git add . && git commit -m "fix: tri lap pattern" && git push`
4. `ssh root@89.108.88.104 "cd /opt/km_track && git pull && systemctl restart km_tri_loader@tri_24h"`

### Сайт недоступен (502 / 504)

```bash
ssh root@89.108.88.104 "systemctl status km_track --no-pager | head -10"
ssh root@89.108.88.104 "systemctl restart km_track"
ssh root@89.108.88.104 "systemctl status nginx --no-pager | head -5"
```

### Нет участников в API (пустой standings)

```bash
# Проверить БД
ssh root@89.108.88.104 "mq -e 'SELECT COUNT(*) FROM participants;'"
# Если 0 — переинициализировать:
ssh root@89.108.88.104 "cd /opt/km_track && /opt/km_track/venv/bin/python load_tri_results.py --config config/events/tri_24h.yaml --init 2>&1"
```

---

## Финиш гонки (20:00, 26.06.2026)

- [ ] Убедиться что финишные круги записаны (подождать 2–3 цикла загрузчика)
- [ ] Проверить финальную таблицу: https://live-race.triatleta.ru/24h
- [ ] Остановить загрузчик:
  ```bash
  ssh root@89.108.88.104 "systemctl stop km_tri_loader@tri_24h"
  ```
- [ ] Финальный снимок результатов:
  ```bash
  ssh root@89.108.88.104 "mq -e 'SELECT p.surname, p.name, p.gender, p.category, COUNT(l.id) as laps, ROUND(COUNT(l.id)*4.040,1) as km FROM participants p LEFT JOIN laps l ON l.participant_id=p.id GROUP BY p.id ORDER BY laps DESC;'"
  ```
