# Runbook: Деплой KM Track на nic.ru VDS

Цель: запустить `https://analytics.krasmarafon.ru` на VDS nic.ru.

**Условия nic.ru:** 30 дней бесплатно при оплате от 3 месяцев.
Минимальный тариф 490 ₽/мес × 3 = **1 470 ₽** → первый месяц бесплатно.

---

## Шаг 1 — Заказать VDS

1. Перейди на https://www.nic.ru/catalog/vps/
2. Выбери тариф **VDS KVM SSD-1** (минимальный):
   - 1 vCPU / 1 GB RAM / 20 GB SSD
   - ~490 ₽/мес
3. При оформлении:
   - ОС: **Ubuntu 22.04 LTS**
   - Период: **3 месяца** (чтобы получить первый месяц бесплатно)
   - Запомни или смени **root-пароль**
4. После оплаты сервер создаётся за 5–10 минут
5. В личном кабинете → **Мои услуги → VDS** → скопируй **IP-адрес**

---

## Шаг 2 — DNS для analytics.krasmarafon.ru

DNS домена уже на nic.ru — всё в одном месте.

1. Личный кабинет nic.ru → **Домены** → `krasmarafon.ru` → **Управление DNS**
2. Добавить запись:
   - Тип: **A**
   - Имя: `analytics`
   - Значение: IP-адрес VDS из шага 1
   - TTL: 300
3. Сохранить
4. Проверить через 5–15 минут:
   ```
   nslookup analytics.krasmarafon.ru
   ```
   Должен вернуть твой IP.

---

## Шаг 3 — Подключиться к серверу

```bash
ssh root@<IP_АДРЕС>
```

Если на Windows — используй **PuTTY** или встроенный терминал (Win+R → `cmd` → `ssh root@IP`).

---

## Шаг 4 — Запустить setup.sh

```bash
curl -o setup.sh https://raw.githubusercontent.com/podbor16/KM_track/Map/deploy/setup.sh
bash setup.sh https://github.com/podbor16/KM_track.git
```

Скрипт автоматически:
- Установит Python 3.11, nginx, certbot, git
- Создаст пользователя `km` и virtualenv
- Склонирует репозиторий в `/opt/km_track`
- Установит зависимости (`requirements.txt`)
- Добавит 1 GB swap
- Настроит nginx и получит SSL-сертификат Let's Encrypt
- Зарегистрирует systemd-сервис с автозапуском

> Когда скрипт спросит `DNS настроен? (y/n)` — убедись что `nslookup` уже отвечает нужным IP, затем вводи `y`.

---

## Шаг 5 — Скопировать .env

На локальной машине (в директории проекта):

```bash
scp .env root@<IP_АДРЕС>:/opt/km_track/.env
```

Убедись что в `.env` заполнены:
```
DB_HOST=79.174.89.159
DB_PORT=16171
DB_NAME=krasmarafon
DB_USER=km_analytic
DB_PASSWORD=<пароль>
ADMIN_USERNAME=<логин>
ADMIN_PASSWORD=<пароль>
SECRET_KEY=<длинная случайная строка>
DEBUG=False
CORS_ORIGINS=https://analytics.krasmarafon.ru,https://krasmarafon.ru
```

---

## Шаг 6 — Запустить приложение

```bash
# На сервере:
systemctl start km_track
systemctl status km_track
```

Должно показать `active (running)`.

---

## Шаг 7 — Проверка

```bash
# На сервере:
curl http://127.0.0.1:8000/health
```

В браузере:
- `https://analytics.krasmarafon.ru/health` → `{"status":"ok"}`
- `https://analytics.krasmarafon.ru/tracker`
- `https://analytics.krasmarafon.ru/results`

---

## Деплой обновлений

```bash
ssh root@<IP_АДРЕС>
bash /opt/km_track/deploy/update.sh
```

---

## Полезные команды

```bash
systemctl status km_track            # статус приложения
journalctl -u km_track -n 50 -f      # логи в реальном времени
systemctl restart km_track           # перезапуск
nginx -t && systemctl reload nginx   # проверить конфиг nginx
free -h                              # оперативная память
df -h                                # место на диске
```

---

## Устранение проблем

**Сервис не запускается:**
```bash
journalctl -u km_track -n 100
```
Чаще всего: `.env` не скопирован или неверный `DB_PASSWORD`.

**502 Bad Gateway:**
```bash
systemctl status km_track    # приложение упало?
curl http://127.0.0.1:8000   # работает локально?
```

**SSL не получается:**
```bash
# DNS ещё не распространился — подожди и повтори:
certbot --nginx -d analytics.krasmarafon.ru
```
