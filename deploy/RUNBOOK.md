# Runbook: Деплой KM Track на Timeweb Cloud

Цель: запустить `https://analytics.krasmarafon.ru` на бесплатном VPS Timeweb Cloud.

---

## Шаг 1 — Регистрация и создание VPS

1. Перейди на https://timeweb.cloud — зарегистрируйся (нужен только номер телефона)
2. После входа: **Облачные серверы → Создать сервер**
3. Выбери конфигурацию:
   - ОС: **Ubuntu 22.04**
   - Тариф: минимальный (1 vCPU / 1 GB RAM / 15 GB SSD)
   - Регион: **Москва**
4. Создай SSH-ключ или запомни root-пароль
5. Запусти сервер → скопируй **IP-адрес** (например `185.x.x.x`)

---

## Шаг 2 — DNS в nic.ru

1. Войди в панель управления nic.ru → **Управление доменом** → `krasmarafon.ru`
2. DNS-записи → Добавить запись:
   - Тип: **A**
   - Имя (поддомен): `analytics`
   - Значение: IP-адрес сервера из шага 1
   - TTL: 300
3. Сохрани. DNS распространяется обычно за 5–30 минут.
4. Проверка: `nslookup analytics.krasmarafon.ru` должен вернуть твой IP.

---

## Шаг 3 — Подключение к серверу

```bash
ssh root@<IP_АДРЕС>
```

---

## Шаг 4 — Клонирование репозитория и первоначальная настройка

```bash
# Скачать setup.sh прямо с GitHub
curl -o setup.sh https://raw.githubusercontent.com/podbor16/KM_track/Map/deploy/setup.sh
bash setup.sh https://github.com/podbor16/KM_track.git
```

Скрипт сделает:
- Установит Python 3.11, nginx, certbot, git
- Создаст пользователя `km`
- Склонирует репозиторий в `/opt/km_track`
- Создаст virtualenv и установит зависимости
- Добавит 1 GB swap (важно для 1 GB RAM)
- Настроит nginx и получит SSL-сертификат
- Зарегистрирует systemd-сервис

> Когда скрипт спросит `DNS настроен? (y/n)` — убедись что `nslookup analytics.krasmarafon.ru` уже отвечает твоим IP.

---

## Шаг 5 — Скопировать .env на сервер

На своей локальной машине (в директории проекта):

```bash
scp .env root@<IP_АДРЕС>:/opt/km_track/.env
```

Проверь что в `.env` заполнены все обязательные поля:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- `SECRET_KEY` — любая длинная случайная строка
- `DEBUG=False`
- `CORS_ORIGINS=https://analytics.krasmarafon.ru,https://krasmarafon.ru`

---

## Шаг 6 — Запуск приложения

```bash
# На сервере:
systemctl start km_track
systemctl status km_track
```

Должно показать `active (running)`.

---

## Шаг 7 — Проверка

```bash
# На сервере — локальный health check:
curl http://127.0.0.1:8000/health

# Через браузер:
https://analytics.krasmarafon.ru/health        # → {"status":"ok"}
https://analytics.krasmarafon.ru/tracker       # карта
https://analytics.krasmarafon.ru/results       # таблица результатов
```

В браузере: DevTools → Network → выбери любой SSE-запрос (`/api/sse/...`) → убедись что `EventStream` получает события.

---

## Деплой обновлений (после первого запуска)

```bash
ssh root@<IP_АДРЕС>
bash /opt/km_track/deploy/update.sh
```

---

## Полезные команды

```bash
systemctl status km_track          # статус сервиса
journalctl -u km_track -n 50 -f    # логи приложения в реальном времени
systemctl restart km_track         # перезапуск
nginx -t && systemctl reload nginx # проверить и перезагрузить nginx
certbot renew --dry-run            # проверка автообновления SSL
free -h                            # оперативная память
df -h                              # место на диске
```

---

## Если что-то пошло не так

**Сервис не запускается:**
```bash
journalctl -u km_track -n 100
```
Чаще всего причина: `.env` не скопирован или неверный путь к venv.

**502 Bad Gateway в nginx:**
```bash
systemctl status km_track   # приложение не запущено?
curl http://127.0.0.1:8000  # работает локально?
```

**Сертификат не выдаётся:**
```bash
# DNS ещё не распространился — подожди и повтори:
certbot --nginx -d analytics.krasmarafon.ru
```
