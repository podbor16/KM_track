# Triatleta Mobile Layout Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Исправить мобильный layout страницы `/tri/results` — табы и сабтабы графика должны скроллиться горизонтально, графики не обрезаться.

**Architecture:** Только CSS и одна строка JS на файл. `body { overflow-x: hidden }` заменяется на `overflow-x: clip` (не блокирует child scroll-контейнеры). Таб-бары получают `overflow-x: auto` в `@media (max-width: 640px)`. Canvas-чарты получают `padding.right: 0` на мобилке.

**Tech Stack:** CSS media queries, Chart.js options, vanilla JS.

---

## Файлы

- Modify: `static/css/tri_results.css` — body overflow, page tabs mobile, chart subtabs mobile
- Modify: `templates/race_triatleta/tri_results.html` — `layout.padding.right` в `renderChart` (строка ~978) и `renderPositionChart` (строка ~1305)

---

### Task 1: CSS — body overflow-x и page tabs

**Files:**
- Modify: `static/css/tri_results.css`

- [ ] **Шаг 1: Открыть файл и найти `body` блок (строка ~14–22)**

  ```css
  /* Было: */
  body {
      ...
      overflow-x: hidden;
  }

  /* Станет: */
  body {
      ...
      overflow-x: clip;
  }
  ```

  > Почему `clip`, а не убрать совсем: `clip` так же скрывает overflow страницы, но не создаёт новый scroll-контейнер — дочерние `overflow-x: auto` работают корректно.

- [ ] **Шаг 2: Найти `@media (max-width: 640px)` (строка ~196) и добавить мобильные стили page tabs**

  В конец существующего `@media (max-width: 640px)` блока добавить:

  ```css
  /* Mobile page tabs */
  .tri-page-tabs {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      padding: 0 12px;
  }
  .tri-page-tabs::-webkit-scrollbar { display: none; }
  .tri-page-tab {
      padding: 9px 14px;
      font-size: 13px;
      flex-shrink: 0;
  }
  ```

- [ ] **Шаг 3: Проверить в браузере на 375px — все 4 таба должны быть доступны**

  Открыть DevTools → Dimensions: iPhone SE (375×667). Убедиться что табы «Расстояние», «Отрезки», «График», «Круги» либо влезают, либо скроллятся.

- [ ] **Шаг 4: Commit**

  ```bash
  git add static/css/tri_results.css
  git commit -m "fix(tri): mobile page tabs — overflow-x scroll, reduced padding"
  ```

---

### Task 2: CSS — chart subtabs мобилка

**Files:**
- Modify: `static/css/tri_results.css`

- [ ] **Шаг 1: Найти стили `.tri-chart-subtabs` (поиск по `tri-chart-subtabs`)**

  Добавить в тот же `@media (max-width: 640px)` блок (или создать новый):

  ```css
  /* Mobile chart subtabs */
  .tri-chart-subtabs {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      flex-wrap: nowrap;
      padding: 8px 12px;
  }
  .tri-chart-subtabs::-webkit-scrollbar { display: none; }
  .tri-chart-subtab {
      flex-shrink: 0;
  }
  ```

- [ ] **Шаг 2: Проверить в DevTools 375px на вкладке «График»**

  Сабтабы «Скорость», «Дистанция», «Позиция» должны быть доступны (влезать или скроллиться).

- [ ] **Шаг 3: Commit**

  ```bash
  git add static/css/tri_results.css
  git commit -m "fix(tri): mobile chart subtabs — overflow-x scroll"
  ```

---

### Task 3: JS — убрать правый padding canvas на мобилке

**Files:**
- Modify: `templates/race_triatleta/tri_results.html`

- [ ] **Шаг 1: Найти `renderChart` (~строка 849) — опцию `layout`**

  ```js
  // Было (~строка 978):
  layout: { padding: { right: 160 } },

  // Станет:
  layout: { padding: { right: isMobile() ? 0 : 160 } },
  ```

- [ ] **Шаг 2: Найти `renderPositionChart` (~строка 1160) — опцию `layout`**

  ```js
  // Было (~строка 1305):
  layout: { padding: { right: 160 } },

  // Станет:
  layout: { padding: { right: isMobile() ? 0 : 160 } },
  ```

  > `renderDistanceChart` не имеет `padding.right` — не трогаем.

- [ ] **Шаг 3: Проверить в DevTools 375px — переключиться на «График»**

  График «Дистанция» и «Позиция» должны занимать полную ширину без обрезки справа. Плашки с именами участников (десктопная фича) на мобилке скрыты через `if (isMobile()) return;` — так и должно быть.

- [ ] **Шаг 4: Проверить что десктоп не сломан**

  На полной ширине (>640px) плашки с именами по-прежнему отображаются справа от графика.

- [ ] **Шаг 5: Commit**

  ```bash
  git add templates/race_triatleta/tri_results.html
  git commit -m "fix(tri): remove chart right padding on mobile"
  ```

---

### Task 4: Финальная проверка

- [ ] **Проверить все 4 таба на мобилке**

  DevTools 375px. Пройтись по всем 4 вкладкам: Расстояние → Отрезки → График → Круги. Все должны переключаться без обрезки.

- [ ] **Проверить 3 сабтаба графика**

  На вкладке «График»: Скорость / Дистанция / Позиция — все доступны.

- [ ] **Проверить десктоп (1280px)**

  Табы, графики, плашки с именами — без регрессий.

- [ ] **Проверить тёмную тему** (если есть `prefers-color-scheme: dark`)

  Скроллбары скрыты в обоих режимах.
