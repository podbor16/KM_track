# Дизайн: Адаптация KM_track под суточную велогонку Triatleta

**Дата:** 2026-06-23  
**Гонка:** Triatleta — Суточная велогонка 24 часа 2026  
**Старт:** 2026-06-25 20:00 Красноярск (13:00 UTC)  
**Статус:** Утверждён

---

## Контекст

Суточная многокруговая велогонка. Круг: 4.04 км. До 150 кругов на участника.
- 6 участников в личном зачёте
- 3 команды в эстафетном зачёте (2 участника в команде, детали уточняются)
- Данные из Copernico API, race_id: `triatleta-sutochnaya-velogonka-24-chasa-2026`
- КТ в Copernico: `1kr`, `2kr`, ..., `150kr` (один КТ = один круг)

---

## Архитектура

**Вариант А: новый модуль в существующем FastAPI-приложении**

```
live-race.triatleta.ru
    ↓ nginx (новый server block, тот же порт 8000)
    ↓ FastAPI (Host-header routing)
    ↓
DB: triatleta_24h (отдельная БД, тот же MySQL VPS)
    ↓
Copernico API (race_id: triatleta-sutochnaya-velogonka-24-chasa-2026)
    ↓
load_tri_results.py (новый загрузчик, интервал 30 сек)
```

FastAPI определяет Host-заголовок: если `live-race.triatleta.ru` → отдаёт Tri-страницы.

---

## База данных `triatleta_24h`

### events
```sql
CREATE TABLE events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) UNIQUE,
    name VARCHAR(255),
    gun_datetime DATETIME,        -- UTC: 2026-06-25 13:00:00
    lap_distance_km DECIMAL(5,3), -- 4.040
    duration_hours INT            -- 24
);
```

### participants
```sql
CREATE TABLE participants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_id INT,
    start_number INT,
    surname VARCHAR(255),
    name VARCHAR(255),
    birthdate DATE,
    gender VARCHAR(10),
    status VARCHAR(50),
    category VARCHAR(100),
    team_name VARCHAR(255)        -- NULL для личного зачёта
);
```

### laps
```sql
CREATE TABLE laps (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    participant_id INT,
    event_id INT,
    lap_number INT,
    cumulative_ms BIGINT,         -- мс от gun_start до финиша круга
    lap_ms BIGINT,                -- мс на этот конкретный круг
    INDEX idx_participant_lap (participant_id, lap_number)
);
```

**Почему `laps`, а не `results`:** каждая строка — событие в реальном времени (факт завершения круга), а не итоговый финиш. Для 150 кругов на участника это до 150 строк, что принципиально отличается от марафонской модели "одна строка = один финиш".

---

## Copernico пресет

**Файл:** `config/copernico/tri_24h_2026.yaml`

```yaml
description: "Triatleta 24h 2026. 150 кругов по 4.04 км. КТ: 1kr..150kr."

fields:
  start_number: bib
  surname: surname
  name: name
  birthdate: birthdate
  gender: gender
  status: status
  category: category

lap_fields:
  count: 150
  pattern: "times.official_{n}kr"
```

---

## Загрузчик

**Файл:** `load_tri_results.py` (новый, не модифицирует существующий `load_race_results.py`)

**Конфиг:** `config/loader/tri_24h.env`
```
LOADER_CONFIG=config/events/tri_24h.yaml
LOADER_INTERVAL=30
```

**Логика:**
1. Каждые 30 сек запрашивает Copernico API
2. При первом запуске (`--init`): создаёт записи в `participants`
3. Для каждого участника итерирует `times.official_1kr` → `times.official_150kr`
4. Вычисляет `lap_ms = cumulative_ms[N] - cumulative_ms[N-1]`
5. INSERT IGNORE по `(participant_id, lap_number)` — только новые круги

**Event YAML:** `config/events/tri_24h.yaml`
```yaml
name: "Triatleta 24h"
code: "tri_24h_2026"
year: 2026
gun_time: "13:00:00"  # UTC
distances:
  - distance: "24h"
    db_event_id: null   # заполнить после создания записи в events
    copernico:
      race_id: "triatleta-sutochnaya-velogonka-24-chasa-2026"
      login: "podbor250718@gmail.com"
      preset: "tri_24h_2026"
      event: "24h"     # уточнить название ивента в Copernico
```

---

## Frontend — `live-race.triatleta.ru`

### Live Results (главная страница)

- Счётчик прошедшего времени гонки
- Таблица личного зачёта:
  `Место | Участник | Кругов | Км | Время | Скорость км/ч | Отставание от лидера`
- Отставание: лидер показывает `—`, остальные:
  - Если разница в кругах: `−N кругов`
  - Если одинаковые круги: `+чч:мм:сс`
- Вкладки: **Личный зачёт** / **Командный зачёт**
- Polling каждые 30 сек (не SSE — достаточно для суточной гонки)

### Сплиты по часам

- Двойной слайдер: выбор диапазона часов (1–24)
- Таблица: `Участник | Кругов за период | Км за период`
- Данные считаются на клиенте из уже загруженных `laps` по `cumulative_ms`

---

## Инфраструктура

### DNS
- Добавлена A-запись `live-race` → `89.108.88.104` (сделано 2026-06-23)
- TTL: 3600 сек

### SSL
- Let's Encrypt через `certbot --nginx -d live-race.triatleta.ru` после распространения DNS

### nginx
Новый `server` блок в `deploy/nginx.conf`:
```nginx
server {
    listen 443 ssl;
    server_name live-race.triatleta.ru;
    ssl_certificate     /etc/letsencrypt/live/live-race.triatleta.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/live-race.triatleta.ru/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
server {
    listen 80;
    server_name live-race.triatleta.ru;
    return 301 https://$host$request_uri;
}
```

### Systemd
Новый сервис `km_race_loader_tri@tri_24h.service` по аналогии с `km_race_loader@*`.

---

## Переключение между проектами

- В хедере `krasmarafon.ru`: ссылка «Tri.Race ↗» → `live-race.triatleta.ru`
- В хедере `live-race.triatleta.ru`: ссылка «КМ.Аналитика ↗» → `krasmarafon.ru`
- Реализуется после гонки (не критично для MVP)

---

## Открытые вопросы

1. **Эстафета в Copernico**: как представлены команды — каждый гонщик отдельно или команда как одна запись? Уточнить перед разработкой командного зачёта.
2. **Название ивента в Copernico**: точное значение поля `event` в API (аналог `5km` у марафона). Уточнить в Copernico.
3. **`db_event_id`**: заполнить после `INSERT INTO triatleta_24h.events`.

---

## Порядок реализации (приоритет — к старту 25.06)

1. Настройка DNS + SSL (`live-race.triatleta.ru`)
2. Создание БД `triatleta_24h` + таблицы
3. Copernico пресет + event YAML + loader config
4. Новый загрузчик `load_tri_results.py`
5. nginx конфиг для нового домена
6. FastAPI роуты + Host-routing
7. HTML-страница live results
8. Сплиты со слайдером
