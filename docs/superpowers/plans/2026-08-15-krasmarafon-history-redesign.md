# Редизайн history.html — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Привести `history.html` к единому `km-*` дизайн-языку (тот же, что уже задеплоен на `results.html`/`start_list.html`/`race-analysis.html`/`athlete-profile.html`) — нейтральная рамка карточек-выбора вместо всегда включённой розовой, плоская CTA-кнопка вместо градиента.

**Architecture:** Пятый под-проект программы редизайна Красмарафона. Чисто CSS-задача — `templates/krasmarafon/history.html` и `static/js/history.js` не меняются, только `static/css/history.css`. Никакой новой JS-логики нет, поэтому TDD-цикла с тестами не требуется (в отличие от предыдущих 4 страниц, где были pill-переключатели) — задача сводится к двум точным CSS-правкам и визуальной проверке.

**Tech Stack:** CSS. Верификация — pytest для бэкенда (не меняется в этой задаче, но полный прогон обязателен для проверки регрессии по общим CSS-файлам) + визуальная проверка в браузере (agent-browser).

**Полная спека:** `docs/superpowers/specs/2026-08-15-krasmarafon-history-redesign-design.md`

---

## Task 1: CSS — нейтральная рамка карточек, плоская CTA-кнопка

**Files:**
- Modify: `static/css/history.css`

### Правка 1: Карточки-выбора (`.search-option`)

Найти:

```css
.search-option {
  background: #fff;
  border: 2px solid var(--km-primary, #EE2D62);
  border-radius: 12px;
  padding: 32px 28px;
  box-shadow: var(--km-shadow, 0 2px 8px rgba(0,0,0,0.1));
  display: flex;
  flex-direction: column;
  min-height: 220px;
  transition: all 0.3s ease;
}

.search-option:hover {
  transform: translateY(-4px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.15);
  border-color: #d41f52;
}
```

Заменить на:

```css
.search-option {
  background: #fff;
  border: 1px solid var(--km-border-light, #e0e0e0);
  border-radius: 12px;
  padding: 32px 28px;
  box-shadow: var(--km-shadow, 0 2px 8px rgba(0,0,0,0.1));
  display: flex;
  flex-direction: column;
  min-height: 220px;
  transition: box-shadow 0.2s ease;
}

.search-option:hover {
  box-shadow: var(--km-shadow-hover, 0 4px 12px rgba(0,0,0,0.15));
}
```

### Правка 2: CTA-кнопка (`.race-analysis-btn`)

Найти:

```css
.race-analysis-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 13px 36px;
  background: linear-gradient(135deg, var(--km-primary, #EE2D62), #d41f52);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: var(--km-font-ui, Arial, sans-serif);
  box-shadow: 0 4px 12px rgba(238,45,98,.3);
  text-transform: uppercase;
  text-decoration: none;
  letter-spacing: .5px;
  transition: all .3s;
}

.race-analysis-btn:hover {
  background: linear-gradient(135deg, #d41f52, #b81a45);
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(238,45,98,.4);
}

.race-analysis-btn:active {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(238,45,98,.3);
}
```

Заменить на:

```css
.race-analysis-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 13px 36px;
  background: var(--km-primary, #EE2D62);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: var(--km-font-ui, Arial, sans-serif);
  box-shadow: 0 4px 12px rgba(238,45,98,.3);
  text-transform: uppercase;
  text-decoration: none;
  letter-spacing: .5px;
  transition: background .15s, transform .1s, box-shadow .15s;
}

.race-analysis-btn:hover {
  background: #d4254f;
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(238,45,98,.4);
}

.race-analysis-btn:active {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(238,45,98,.3);
}
```

(Плоская заливка + hover-затемнение + лёгкий `translateY(-1px)` — тот же
паттерн, что `.km-btn-export:hover` в `static/css/analytics.css:121-125`.
`:active` возвращён к `translateY(0)`, как у `.km-btn-export:active` —
раньше `-1px` было промежуточным между rest (`0`) и hover (`-2px`),
теперь hover сам стал `-1px`, так что `:active` логично вернуть на `0`
для эффекта нажатия.)

- [ ] **Step 3: Проверить, что CSS валиден (нет незакрытых скобок)**

Открыть `static/css/history.css` и убедиться, что число `{` равно числу
`}`. Быстрая команда:

```bash
grep -o '{' static/css/history.css | wc -l
grep -o '}' static/css/history.css | wc -l
```

Expected: оба числа равны.

- [ ] **Step 4: Убедиться, что старые значения (градиент, translateY(-4px)/(-2px)) больше не встречаются**

```bash
grep -n "linear-gradient" static/css/history.css
grep -n "translateY(-4px)\|translateY(-2px)" static/css/history.css
```

Expected: `linear-gradient` — 0 совпадений. `translateY(-4px)`/`translateY(-2px)` — 0 совпадений.

- [ ] **Step 5: Commit**

```bash
git add static/css/history.css
git commit -m "chore(krasmarafon): history.css — нейтральная рамка карточек-выбора, плоская CTA-кнопка"
```

---

## Task 2: Полный прогон тестов + визуальная проверка

**Files:** нет изменений кода — только верификация.

- [ ] **Step 1: Запустить полный Python test suite**

Run: `conda run -n base python -m pytest tests/unit/ -q`
Expected: все тесты passed (страница не завязана на backend-логику, но
общие CSS/шаблонные файлы могли задеть другие роуты — полный прогон
исключает регресс)

- [ ] **Step 2: Визуальная проверка в браузере (agent-browser)**

Запустить dev-сервер:
```bash
conda run -n base python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Открыть через `agent-browser open http://127.0.0.1:8000/history`.
Страница не требует авторизации и не зависит от `history_enabled`
(в отличие от `/athlete-profile`/`/race-analysis` — `/history` сама
управляет флагом видимости навигации, но сам роут по прямому URL
доступен всегда, см. `src/krasmarafon/routers/pages.py`). Никаких
фикстур данных подставлять не нужно — страница статична, JS только
обслуживает поле поиска (не задействовано в проверке вёрстки).

Проверить на скриншоте (десктоп `1280x800` и мобильная ширина `390x700`,
через `agent-browser set viewport <w> <h>`):
- Карточки «Поиск спортсмена» / «Анализ по забегам» — тонкая
  нейтральная рамка (не розовая), при наведении курсора нет сдвига
  карточки вверх, только тень становится заметнее
- Кнопка «Перейти к анализу забегов» — сплошная розовая заливка без
  диагонального градиента, при наведении курсора — лёгкий подъём (~1px)
  и более тёмный оттенок розового
- Мобильная ширина — 2 карточки складываются в 1 колонку (уже
  реализовано, не должно было сломаться), ничего не переполняет экран
  горизонтально

Если найдены визуальные баги — исправить и повторить проверку.

- [ ] **Step 3: Закрыть браузер и остановить dev-сервер**

```bash
agent-browser close
```
Остановить процесс uvicorn (найти PID по занятому порту 8000, завершить).

- [ ] **Step 4: Финальный коммит (если были правки по итогам визуальной проверки)**

Если Step 2 потребовал исправлений — закоммитить их отдельным коммитом
(`fix(krasmarafon): history.css — <что именно поправлено по итогам
визуальной проверки>`). Если правок не было — этот шаг пропускается,
Task 1 уже финальный коммит.

---

## Self-Review (для исполнителя плана)

- **Покрытие спеки:** п.1 (карточки-выбора) — Task 1 правка 1; п.2
  (CTA-кнопка) — Task 1 правка 2; п.3 («не в объёме») — ни один task не
  трогает `.container`/`h1`/`.intro-section`/`.athlete-search-input`/
  `.autocomplete-results`/`static/js/history.js`.
- **Плейсхолдеров нет** — оба find/replace блока содержат точный код.
- **Тестов не требуется** — спека явно оговаривает отсутствие
  собственной JS-логики у страницы, Task 2 ограничивается прогоном
  существующего test suite + визуальной проверкой, без нового
  постоянного теста.
