# Логотип в навбаре + favicon для Красмарафона — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить логотип в навбаре/логин-топбаре Красмарафона на графический знак (без текста), сгенерировать и подключить полноценный набор favicon-файлов на всех публичных страницах.

**Architecture:** Два независимых, но связанных изменения: (1) генерация 5 новых файлов-ассетов из уже имеющихся исходников (`КМ.png`, `KM_pink.jpg`) через одноразовый Python/PIL-скрипт — сам скрипт НЕ коммитится (тот же подход, что уже применён для favicon-набора Siberman — готовые файлы в `static/images/siberman/`, генератора в репозитории нет); (2) точечные правки шаблонов — 1 правка логотипа навбара (покрывает 7 страниц через общий инклюд `header.html`), 1 правка логотипа `login.html`, и по 3 строки favicon-тегов на 9 страницах (7 новых + 2 замены существующих).

**Tech Stack:** Python/Pillow (генерация PNG/ICO), Jinja2 HTML-шаблоны. Тесты — pytest для бэкенда (полный прогон, чтобы исключить регресс по общим шаблонам).

**Полная спека:** `docs/superpowers/specs/2026-08-15-krasmarafon-logo-favicon-design.md`

---

## Task 1: Генерация ассетов

**Files:**
- Create (временно, не коммитится): `_gen_krasmarafon_assets.py` в корне репозитория
- Create (коммитятся): `static/images/krasmarafon/logo-mark.png`, `static/images/krasmarafon/favicon-32.png`, `static/images/krasmarafon/favicon-512.png`, `static/images/krasmarafon/apple-touch-icon.png`, `static/images/krasmarafon/favicon.ico`

- [ ] **Step 1: Написать генерирующий скрипт**

Создать файл `_gen_krasmarafon_assets.py` в корне репозитория с ровно этим содержимым:

```python
from PIL import Image

# 1. Знак без текста — кроп верхней части полного локапа КМ.png
#    (строки 0-453 — знак, 454-551 — пустой прозрачный зазор, 552-633 — текст "КРАСМАРАФОН", исключаем)
src = Image.open("static/images/krasmarafon/КМ.png").convert("RGBA")
mark = src.crop((0, 0, 1549, 454))
mark.save("static/images/krasmarafon/logo-mark.png")
print("logo-mark.png:", mark.size, mark.mode)

# 2. Favicon-набор — из готовой квадратной иконки KM_pink.jpg (без кропа/паддинга)
pink = Image.open("static/images/krasmarafon/KM_pink.jpg").convert("RGBA")

favicon_32 = pink.resize((32, 32), Image.LANCZOS)
favicon_32.save("static/images/krasmarafon/favicon-32.png")
print("favicon-32.png:", favicon_32.size, favicon_32.mode)

favicon_512 = pink.resize((512, 512), Image.LANCZOS)
favicon_512.save("static/images/krasmarafon/favicon-512.png")
print("favicon-512.png:", favicon_512.size, favicon_512.mode)

apple_touch = pink.resize((180, 180), Image.LANCZOS)
apple_touch.save("static/images/krasmarafon/apple-touch-icon.png")
print("apple-touch-icon.png:", apple_touch.size, apple_touch.mode)

pink.save(
    "static/images/krasmarafon/favicon.ico",
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48)],
)
print("favicon.ico saved")
```

- [ ] **Step 2: Запустить скрипт**

Run: `conda run -n base python _gen_krasmarafon_assets.py`
Expected: 5 строк вывода, без ошибок:
```
logo-mark.png: (1549, 454) RGBA
favicon-32.png: (32, 32) RGBA
favicon-512.png: (512, 512) RGBA
apple-touch-icon.png: (180, 180) RGBA
favicon.ico saved
```

- [ ] **Step 3: Проверить результат вручную**

Открыть `static/images/krasmarafon/logo-mark.png` — должен быть виден только графический знак «KM» (тройной штрих + волна), без текста «КРАСМАРАФОН» снизу, фон прозрачный (не белый/чёрный прямоугольник).

Открыть `static/images/krasmarafon/favicon-512.png` — должен быть виден белый знак на розовом фоне, без искажений пропорций (не растянут).

- [ ] **Step 4: Удалить генерирующий скрипт (не коммитится — как и у Siberman-favicon, готовых генераторов в репозитории нет)**

```bash
rm _gen_krasmarafon_assets.py
```

- [ ] **Step 5: Commit только сгенерированных файлов**

```bash
git add static/images/krasmarafon/logo-mark.png static/images/krasmarafon/favicon-32.png static/images/krasmarafon/favicon-512.png static/images/krasmarafon/apple-touch-icon.png static/images/krasmarafon/favicon.ico
git commit -m "chore(krasmarafon): сгенерировать знак без текста + favicon-набор из исходников"
```

---

## Task 2: Логотип в навбаре и на login.html

**Files:**
- Modify: `templates/krasmarafon/header.html`
- Modify: `templates/krasmarafon/login.html`

### Правка 1: Навбар (покрывает все 7 страниц через общий инклюд)

Найти в `templates/krasmarafon/header.html`:

```html
            <img src="/static/images/krasmarafon-logo.png" alt="Красмарафон" class="navbar-logo-img">
```

Заменить на:

```html
            <img src="/static/images/krasmarafon/logo-mark.png" alt="Красмарафон" class="navbar-logo-img">
```

(CSS `.navbar-logo-img { height: 26px; width: auto }` в `static/css/navigation.css` НЕ меняется — при новом соотношении сторон 3.41:1 отрендерится ~89px шириной, укладывается и в мобильный `max-width: 140px`.)

### Правка 2: Топбар login.html — заменить текстовый мини-лого на знак

Найти в `templates/krasmarafon/login.html`:

```html
    <div class="km-topbar">
        <a href="/" class="logo-text">КМ<span>ТРЕК</span></a>
    </div>
```

Заменить на:

```html
    <div class="km-topbar">
        <a href="/" class="logo-text">
            <img src="/static/images/krasmarafon/logo-mark.png" alt="Красмарафон" style="height:26px;width:auto;display:block;">
        </a>
    </div>
```

### Правка 3: Убрать мёртвый CSS-селектор `.logo-text span` в login.html

Внутри `<span>` больше нет — `<span>`-дочернего элемента у `.logo-text` не осталось (был только для слова «ТРЕК» другим цветом). Найти в `templates/krasmarafon/login.html`:

```css
        .km-topbar .logo-text span {
            color: #e84c8c;
        }
```

Заменить на: (пусто — удалить блок целиком)

- [ ] **Step 4: Commit**

```bash
git add templates/krasmarafon/header.html templates/krasmarafon/login.html
git commit -m "feat(krasmarafon): логотип в навбаре и на login.html — знак вместо текста"
```

---

## Task 3: Favicon-теги на всех публичных страницах

**Files:**
- Modify: `templates/krasmarafon/athlete-profile.html`, `templates/krasmarafon/history.html`, `templates/krasmarafon/race-analysis.html`, `templates/krasmarafon/results.html`, `templates/krasmarafon/start_list.html`, `templates/krasmarafon/login.html`, `templates/krasmarafon/diploma.html`, `templates/krasmarafon/admin.html`, `templates/krasmarafon/tracker.html`

Один и тот же блок тегов добавляется/заменяется во всех 9 файлах (тот же паттерн, что уже в `templates/siberman/admin.html:7-9`):

```html
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">
```

### Правка 1: `templates/krasmarafon/athlete-profile.html` (favicon нет — добавить)

Найти:

```html
    <title>Профиль спортсмена - Анализ забегов</title>
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

Заменить на:

```html
    <title>Профиль спортсмена - Анализ забегов</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

### Правка 2: `templates/krasmarafon/history.html` (favicon нет — добавить)

Найти:

```html
    <title>История - Анализ забегов</title>
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

Заменить на:

```html
    <title>История - Анализ забегов</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

### Правка 3: `templates/krasmarafon/race-analysis.html` (favicon нет — добавить)

Найти:

```html
    <title>Анализ забегов - История событий</title>
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

Заменить на:

```html
    <title>Анализ забегов - История событий</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

### Правка 4: `templates/krasmarafon/results.html` (favicon нет — добавить)

Найти:

```html
    <title>Результаты забега</title>

    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

Заменить на:

```html
    <title>Результаты забега</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">

    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

### Правка 5: `templates/krasmarafon/start_list.html` (favicon нет — добавить)

Найти:

```html
    <title>Стартовый список</title>
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

Заменить на:

```html
    <title>Стартовый список</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

### Правка 6: `templates/krasmarafon/login.html` (favicon нет — добавить)

Найти:

```html
    <title>Вход — Бизнес-аналитика КМ</title>
    <link rel="stylesheet" href="/static/css/krasmarafon-header.css?v={{ v }}">
```

Заменить на:

```html
    <title>Вход — Бизнес-аналитика КМ</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/css/krasmarafon-header.css?v={{ v }}">
```

### Правка 7: `templates/krasmarafon/diploma.html` (favicon нет — добавить)

Найти:

```html
    <title>Диплом — {{ (diploma.surname or '') }} {{ (diploma.name or '') }}</title>
    <style>
```

Заменить на:

```html
    <title>Диплом — {{ (diploma.surname or '') }} {{ (diploma.name or '') }}</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">
    <style>
```

### Правка 8: `templates/krasmarafon/admin.html` (заменить старую строку на новый набор)

Найти:

```html
    <title>Панель управления — KM Track</title>
    <link rel="icon" type="image/png" href="/static/images/krasmarafon-logo.png">
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

Заменить на:

```html
    <title>Панель управления — KM Track</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
```

### Правка 9: `templates/krasmarafon/tracker.html` (заменить старую строку на новый набор)

Найти:

```html
    <title>{{ event_title }}</title>
    <link rel="icon" type="image/png" href="/static/images/krasmarafon-logo.png">
    <link rel="stylesheet" href="/static/lib/leaflet-1.9.4/leaflet.css"/>
```

Заменить на:

```html
    <title>{{ event_title }}</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" href="/static/images/krasmarafon/favicon-32.png" sizes="32x32">
    <link rel="apple-touch-icon" href="/static/images/krasmarafon/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/lib/leaflet-1.9.4/leaflet.css"/>
```

- [ ] **Step 10: Commit**

```bash
git add templates/krasmarafon/athlete-profile.html templates/krasmarafon/history.html templates/krasmarafon/race-analysis.html templates/krasmarafon/results.html templates/krasmarafon/start_list.html templates/krasmarafon/login.html templates/krasmarafon/diploma.html templates/krasmarafon/admin.html templates/krasmarafon/tracker.html
git commit -m "feat(krasmarafon): favicon на всех публичных страницах"
```

---

## Task 4: Полный прогон тестов + визуальная проверка

**Files:** нет изменений кода — только верификация.

- [ ] **Step 1: Запустить полный Python test suite**

Run: `conda run -n base python -m pytest tests/unit/ -q`
Expected: все тесты passed (изменения не затрагивают backend-логику, но регрессия по общим шаблонам должна быть исключена)

- [ ] **Step 2: Визуальная проверка в браузере (agent-browser)**

Запустить dev-сервер:
```bash
conda run -n base python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Проверить на скриншотах (десктоп `1280x800` и мобильная ширина `390x700`):
- `/results` или `/start_list` — в навбаре виден только графический знак «KM» (без текста «КРАСМАРАФОН» под ним), не искажён, помещается на мобильной ширине
- `/login` — в топбаре тот же знак вместо текста «КМ ТРЕК», кликабелен (ссылка на `/`)
- Вкладка браузера (`agent-browser get title` + проверка `<link rel="icon">` через `agent-browser eval "document.querySelector('link[rel=icon]').href"`) — указывает на новый `favicon.ico`, не на старый `krasmarafon-logo.png`

Если найдены визуальные баги — исправить и повторить проверку.

- [ ] **Step 3: Закрыть браузер и остановить dev-сервер**

```bash
agent-browser close
```
Остановить процесс uvicorn (найти PID по занятому порту 8000, завершить).

- [ ] **Step 4: Финальный коммит (если были правки по итогам визуальной проверки)**

Если Step 2 потребовал исправлений — закоммитить их отдельным коммитом (`fix(krasmarafon): <что именно поправлено>`). Если правок не было — этот шаг пропускается.

---

## Self-Review (для исполнителя плана)

- **Покрытие спеки:** п.1 (знак в навбаре) — Task 1 + Task 2 правка 1; п.2 (favicon-набор) — Task 1 + Task 3 (все 9 файлов); п.3 (login.html) — Task 2 правки 2-3; «не в объёме» (font-аудит, `krasmarafon_header.html`, `og:image`-тег, футер) — ни один task их не трогает; `static/images/krasmarafon-logo.png` — не удаляется и не изменяется ни в одном task.
- **Плейсхолдеров нет** — все 9 файлов Task 3 расписаны индивидуально с точным до/после текстом, не через «повторить как в файле N».
- **Согласованность путей:** `static/images/krasmarafon/logo-mark.png` — одно и то же имя файла используется в Task 1 (генерация), Task 2 правка 1 (навбар) и правка 2 (login.html). `favicon.ico`/`favicon-32.png`/`apple-touch-icon.png` — одинаковые пути во всех 9 правок Task 3.
