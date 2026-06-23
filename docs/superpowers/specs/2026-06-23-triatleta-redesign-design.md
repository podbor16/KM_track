# Triatleta Redesign — Design Spec

**Date:** 2026-06-23  
**Scope:** `tri_results.html`, `tri_admin.html`, `tri_results.css`  
**Goal:** Убрать эмодзи из пользовательского интерфейса, сменить тему на светлую с брендовой тёмной шапкой по образцу race.triatleta.ru/24h

---

## Палитра

Источник: извлечена с race.triatleta.ru через `getComputedStyle` в DevTools.

| Переменная | Старое значение | Новое значение | Назначение |
|---|---|---|---|
| `--tri-bg` | `#0d1117` | `#f5f5f5` | Фон страницы |
| `--tri-surface` | `#161b22` | `#ffffff` | Фон карточек, таблиц |
| `--tri-border` | `#30363d` | `#e8e8e8` | Разделители |
| `--tri-accent` | `#f0883e` | `#FF8562` | Акцент (лосось с сайта гонки) |
| `--tri-text` | `#e6edf3` | `#050505` | Основной текст |
| `--tri-muted` | `#8b949e` | `#888888` | Вторичный текст |
| `--tri-navy` | *(нет)* | `#263146` | Заголовки таблиц, навигация |
| `--tri-green` | `#3fb950` | `#18A558` | Лидер / позитив |
| `--tri-red` | `#f85149` | `#DE0000` | Отставание / негатив |
| `--tri-header-bg` | *(нет)* | `linear-gradient(135deg, #050505 0%, #263146 100%)` | Фон шапки |

---

## Шрифт

**Onest** — тот же шрифт, что используется на race.triatleta.ru.  
Подключается через Google Fonts:

```html
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;600;700;800;900&display=swap" rel="stylesheet">
```

Добавляется в `<head>` обоих шаблонов. CSS: `font-family: 'Onest', Arial, sans-serif`.

---

## Компонент: Шапка (обе страницы)

Одинаковая структура в `tri_results.html` и `tri_admin.html`.

**Визуал:**
- Фон: `linear-gradient(135deg, #050505, #263146)`
- Нижняя граница: `3px solid #FF8562`
- Eyebrow-строка: `TRIATLETA · 24 ЧАСА` — `font-size: 11px`, `color: #FF8562`, `font-weight: 700`, `letter-spacing: 1.5px`, `text-transform: uppercase`
- Заголовок: `font-size: 22px`, `font-weight: 900`, `color: #fff`
- Метаданные (дата, место, круг): `color: rgba(255,255,255,0.45)`
- Таймер справа: `font-size: 32px`, `font-weight: 900`, `color: #FF8562`, `font-variant-numeric: tabular-nums`

**Удаление эмодзи:**
- `tri_results.html`: удалить `🚴` из заголовка
- `tri_admin.html`: удалить `🔧` из заголовка

---

## Компонент: Toolbar (только tri_results.html)

Белая полоса между шапкой и таблицей:
- `background: #fff`, `border-bottom: 1px solid #e8e8e8`
- `select` и `input`: `background: #f5f5f5`, `border: 1px solid #e0e0e0`, `border-radius: 6px`
- При фокусе: `border-color: #FF8562`

---

## Компонент: Таблица результатов

**Обёртка:** `background: #fff`, `border-radius: 10px`, `box-shadow: 0 1px 4px rgba(0,0,0,0.06)`

**Заголовок таблицы:** `color: #263146`, `font-weight: 700`, `border-bottom: 2px solid #e8e8e8`

**Строки:** `border-bottom: 1px solid #f0f0f0`, hover: `background: #fafafa`

**Бейджи зачётов:**
- Личный: `background: #f0f0f0`, `color: #555`
- Эстафета: `background: #fff0ec`, `color: #FF8562`

**Специальные ячейки:**
- Лидер: `color: #18A558`, `font-weight: 700`
- Отставание: `color: #DE0000`
- Имя: `font-weight: 600`
- Номер места: `font-weight: 800`

---

## Компонент: Admin-панель (tri_admin.html)

Та же тёмная шапка (Triatleta — Управление, без 🔧). Всё внутри — светлая тема:

- Вкладки: активная — `background: #FF8562`, `color: #000`; неактивная — белая, `border: 1px solid #e8e8e8`
- Карточки: `background: #fff`, `border: 1px solid #e8e8e8`, `border-radius: 8px`
- Заголовок карточки: `color: #FF8562`
- Бейджи статуса: active — зелёный фон `#18A558`, inactive — красный `#DE0000`
- Кнопки: Start `#18A558`, Stop `border: 1px solid #e0e0e0`, Init — border-style, Save `#FF8562`
- Таблица загрузчика: те же правила что основная таблица
- Textarea редактора: `background: #f5f5f5`, `border: 1px solid #e0e0e0`, `color: #050505`

---

## Что НЕ меняется

- Логика JS в шаблонах (polling, фильтры, сплиты, AJAX) — без изменений
- Бэкенд (`router.py`, `load_tri_results.py`) — без изменений
- Логи в Python — эмодзи в логах остаются
- `✓` / `✗` в JS-сообщениях admin — это Unicode-символы, не эмодзи, остаются

---

## Файлы изменений

| Файл | Тип изменений |
|---|---|
| `static/css/tri_results.css` | Полный переписать: новые переменные, Onest, светлая тема, компоненты |
| `templates/tri_results.html` | Новая структура шапки, toolbar, link на Onest, убрать `🚴` |
| `templates/tri_admin.html` | Новая структура шапки, светлая тема вкладок/карточек, убрать `🔧` |
