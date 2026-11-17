# Архитектура платформы KM_track

Обзор по коду и конфигурации репозитория на 17.11.2026. Фактическое состояние сервисов на сервере отдельно не проверялось.

```mermaid
flowchart TD
    User["Зрители и участники<br/>карта, результаты, карточки"]
    Admin["Организаторы<br/>админка, импорт, управление"]
    Tilda["Tilda<br/>регистрации и сайты"]
    Cop["Copernico API<br/>хронометраж"]
    Sheets["Google Sheets / Excel<br/>результаты Siberman"]
    DL["Yandex DataLens<br/>аналитика"]
    GH["GitHub Actions<br/>тесты и деплой main"]

    subgraph Server["Сервер: конфигурация проекта"]
        Nginx["Nginx<br/>HTTPS, домены, статика, проксирование"]
        App["Gunicorn / Uvicorn<br/>FastAPI, 3 воркера"]
        Loaders["Загрузчики результатов<br/>отдельные процессы systemd"]
        Redis[("Redis<br/>лидер и pub/sub")]
        MySQL[("MySQL<br/>krasmarafon · siberman<br/>triatleta_24h · duathlon_222")]
        Metrics[("SQLite<br/>метрики сервера")]
        Files["Файлы проекта<br/>статика, конфигурация, live JSON"]
    end

    User -->|"HTTPS: страницы, API, SSE"| Nginx
    Admin -->|"HTTPS"| Nginx
    Tilda -->|"вебхуки заявок"| Nginx
    Nginx -->|"прокси"| App
    Nginx -->|"отдача"| Files
    Cop -->|"опрос результатов"| Loaders
    Loaders -->|"запись"| MySQL
    Loaders -->|"выгрузка, где настроена"| Files
    Cop -->|"бег Siberman: опрос"| App
    Sheets -->|"синхронизация или импорт"| App
    App <-->|"чтение и запись"| MySQL
    App <-->|"координация и события"| Redis
    App -->|"сбор"| Metrics
    MySQL -->|"данные для аналитики"| DL
    DL -->|"встроенный дашборд"| User
    GH -->|"SSH, после успешных тестов"| App
```

## Что происходит

- Nginx направляет домены Красмарафона, Siberman и Triatleta к общему приложению; часть статических файлов отдаёт сам. В FastAPI направления разделены роутерами и сервисами.
- Загрузчики читают Copernico и сохраняют результаты. Для Siberman приложение также умеет опрашивать Copernico и Google Sheets; источники включаются настройками. Организаторы могут загружать файлы вручную.
- Воркеры используют Redis для выбора лидера и распространения обновлений; приложение передаёт живые обновления клиентам через SSE. Метрики сохраняются отдельно в SQLite.
- Регистрации могут приходить из Tilda через вебхуки. DataLens использует данные для аналитики и встраивается в интерфейс. Межтабличные связи описаны в [ER-диаграммах](database-er.md).
- При push в `main` GitHub Actions запускает тесты и затем деплой на VPS. Диаграмма описывает настроенный процесс; текущий статус сборки или серверных служб здесь не подтверждён.

Источники: `app.py`, `src/krasmarafon/router.py`, `src/siberman/google_sheet_sync.py`, `deploy/nginx.conf`, `deploy/km_track.service`, `deploy/run_loader.sh`, `.github/workflows/deploy.yml` и [ER-диаграммы](database-er.md).
