# Редизайн race-analysis.html Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Привести `templates/krasmarafon/race-analysis.html` к тому же визуальному языку, что и `results.html`/`start_list.html` (плоские карточки, `--km-*` токены), заменив оверлей-текст на карточках забегов на компактную плашку-название и цветные градиентные блоки статистики в модалке на плоские белые карточки, попутно починив реальный баг (отсутствующие CSS-переменные) и удалив подтверждённо мёртвый CSS.

**Architecture:** Изменения только в `templates/krasmarafon/race-analysis.html` (markup карточек) и `static/css/race-analysis.css` (стили). `static/js/race-analysis.js` не редактируется — он уже читает `data-race-name`/генерирует `.stat-item`/`.best-result`/`.pace-item`/`.section-title` разметку, которая просто получает новые CSS-правила.

**Tech Stack:** Чистый CSS/HTML (без сборки), Jinja2-шаблон, agent-browser для визуальной верификации, pytest для регрессионного прогона существующего набора.

---

## Контекст для исполнителя

Спека: `docs/superpowers/specs/2026-08-14-krasmarafon-race-analysis-redesign-design.md` (прочитать перед началом — там объяснение архитектуры страницы и обоснование каждого решения).

Страница показывает сетку из 8 карточек-обложек забегов; клик открывает модалку с кросс-годовой статистикой (Chart.js график, лучший результат, средние темпы) через `/api/race-stats-db`. У страницы своя CSS (`race-analysis.css`), использующая несуществующие в проекте переменные (`--white`, `--shadow`, `--text-dark`, `--text-light`, `--background`) — реальный токенов-проекта набор находится в `static/css/km-design-tokens.css` (`--km-primary`, `--km-bg-card`, `--km-bg-page`, `--km-text-body`, `--km-text-secondary`, `--km-border-light`, `--km-shadow`, `--km-shadow-hover`, `--km-radius-card`, `--km-radius-btn`).

Тестов на JS не будет — `race-analysis.js` не редактируется, изменения чисто HTML/CSS. Основная верификация — визуальная (agent-browser) + регрессионный прогон существующего pytest-набора.

---

### Task 1: HTML — карточки забегов (плашка-название вместо оверлея) + id для заголовка

**Files:**
- Modify: `templates/krasmarafon/race-analysis.html:37-133` (блок `.race-cards-container`)
- Modify: `templates/krasmarafon/race-analysis.html:33` (`<h1>Анализ забегов</h1>`)

- [ ] **Step 1: Заменить весь блок `.race-cards-container` (8 карточек)**

Найти (текущий блок, строки 37-133):
```html
        <div class="race-cards-container">
            <!-- Карточка 1: Ночной забег -->
            <div class="race-card" data-race-id="night_run" data-race-name="Ночной забег">
                <div class="race-card-image"></div>
                <div class="race-card-overlay"></div>
                <div class="race-card-content">
                    <div class="race-card-title">Ночной забег</div>
                    <div class="race-card-description">
                        Забег под звёздами на набережной
                    </div>
                </div>
            </div>

            <!-- Карточка 2: Весна -->
            <div class="race-card" data-race-id="vesna" data-race-name="Весна">
                <div class="race-card-image"></div>
                <div class="race-card-overlay"></div>
                <div class="race-card-content">
                    <div class="race-card-title">Весна</div>
                    <div class="race-card-description">
                        Весенний полумарафон по живописным маршрутам
                    </div>
                </div>
            </div>

            <!-- Карточка 3: Красочный забег -->
            <div class="race-card" data-race-id="colorrun" data-race-name="Красочный забег">
                <div class="race-card-image"></div>
                <div class="race-card-overlay"></div>
                <div class="race-card-content">
                    <div class="race-card-title">Красочный забег</div>
                    <div class="race-card-description">
                        Яркий 5-километровый забег на острове Татышев
                    </div>
                </div>
            </div>

            <!-- Карточка 4: Женская Семерка -->
            <div class="race-card" data-race-id="girlseven" data-race-name="Женская Семерка">
                <div class="race-card-image"></div>
                <div class="race-card-overlay"></div>
                <div class="race-card-content">
                    <div class="race-card-title">Женская Семерка</div>
                    <div class="race-card-description">
                        7-км забег для женщин-спортсменов
                    </div>
                </div>
            </div>

            <!-- Карточка 5: Жара -->
            <div class="race-card" data-race-id="zhara" data-race-name="Жара">
                <div class="race-card-image"></div>
                <div class="race-card-overlay"></div>
                <div class="race-card-content">
                    <div class="race-card-title">Жара</div>
                    <div class="race-card-description">
                        Летний полумарафон на площади Мира в августе
                    </div>
                </div>
            </div>

            <!-- Карточка 6: Детский Забег -->
            <div class="race-card" data-race-id="kids" data-race-name="Детский Забег">
                <div class="race-card-image"></div>
                <div class="race-card-overlay"></div>
                <div class="race-card-content">
                    <div class="race-card-title">Детский Забег</div>
                    <div class="race-card-description">
                        1-км забег для самых маленьких спортсменов
                    </div>
                </div>
            </div>

            <!-- Карточка 7: Х Трейл -->
            <div class="race-card" data-race-id="xtrail" data-race-name="Х Трейл">
                <div class="race-card-image"></div>
                <div class="race-card-overlay"></div>
                <div class="race-card-content">
                    <div class="race-card-title">Х Трейл</div>
                    <div class="race-card-description">
                        Трейл-забег по пересечённой местности
                    </div>
                </div>
            </div>

            <!-- Карточка 8: Снежная семерка -->
            <div class="race-card" data-race-id="snow7" data-race-name="Снежная семерка">
                <div class="race-card-image"></div>
                <div class="race-card-overlay"></div>
                <div class="race-card-content">
                    <div class="race-card-title">Снежная семерка</div>
                    <div class="race-card-description">
                        7-км зимний забег на острове Татышев в декабре
                    </div>
                </div>
            </div>
        </div>
```

Заменить на:
```html
        <div class="race-cards-container">
            <!-- Карточка 1: Ночной забег -->
            <div class="race-card" data-race-id="night_run" data-race-name="Ночной забег">
                <div class="race-card-image"></div>
                <div class="race-card-badge">Ночной забег</div>
            </div>

            <!-- Карточка 2: Весна -->
            <div class="race-card" data-race-id="vesna" data-race-name="Весна">
                <div class="race-card-image"></div>
                <div class="race-card-badge">Весна</div>
            </div>

            <!-- Карточка 3: Красочный забег -->
            <div class="race-card" data-race-id="colorrun" data-race-name="Красочный забег">
                <div class="race-card-image"></div>
                <div class="race-card-badge">Красочный забег</div>
            </div>

            <!-- Карточка 4: Женская Семерка -->
            <div class="race-card" data-race-id="girlseven" data-race-name="Женская Семерка">
                <div class="race-card-image"></div>
                <div class="race-card-badge">Женская Семерка</div>
            </div>

            <!-- Карточка 5: Жара -->
            <div class="race-card" data-race-id="zhara" data-race-name="Жара">
                <div class="race-card-image"></div>
                <div class="race-card-badge">Жара</div>
            </div>

            <!-- Карточка 6: Детский Забег -->
            <div class="race-card" data-race-id="kids" data-race-name="Детский Забег">
                <div class="race-card-image"></div>
                <div class="race-card-badge">Детский Забег</div>
            </div>

            <!-- Карточка 7: Х Трейл -->
            <div class="race-card" data-race-id="xtrail" data-race-name="Х Трейл">
                <div class="race-card-image"></div>
                <div class="race-card-badge">Х Трейл</div>
            </div>

            <!-- Карточка 8: Снежная семерка -->
            <div class="race-card" data-race-id="snow7" data-race-name="Снежная семерка">
                <div class="race-card-image"></div>
                <div class="race-card-badge">Снежная семерка</div>
            </div>
        </div>
```

- [ ] **Step 2: Добавить `id="pageTitle"` на заголовок страницы**

Найти:
```html
            <h1>Анализ забегов</h1>
```
Заменить на:
```html
            <h1 id="pageTitle">Анализ забегов</h1>
```

- [ ] **Step 3: Проверить, что старые классы карточек не остались нигде в файле**

Run: `grep -n "race-card-overlay\|race-card-content\|race-card-title\|race-card-description" templates/krasmarafon/race-analysis.html`
Expected: пусто (нет вывода)

Run: `grep -c "race-card-badge" templates/krasmarafon/race-analysis.html`
Expected: `8`

- [ ] **Step 4: Commit**

```bash
git add templates/krasmarafon/race-analysis.html
git commit -m "feat(krasmarafon): race-analysis.html — плашка-название вместо оверлея на карточках"
```

---

### Task 2: CSS — удалить мёртвый код, добавить `.race-card-badge`

**Files:**
- Modify: `static/css/race-analysis.css`

- [ ] **Step 1: Удалить мёртвый класс `.race-analysis-container`**

Найти (строки 1-15):
```css
/* race-analysis.css - Стили для страницы Анализ забегов */

/* Основной контейнер */
.race-analysis-container {
    max-width: 1400px;
    margin: 0 auto;
    background-color: var(--background);
    padding: 40px 40px;
}

.race-analysis-header {
    text-align: center;
    margin-bottom: 50px;
}
```
Заменить на:
```css
/* race-analysis.css - Стили для страницы Анализ забегов */

.race-analysis-header {
    text-align: center;
    margin-bottom: 50px;
}
```

- [ ] **Step 2: Починить тень карточки (`--shadow` → `--km-shadow`)**

Найти:
```css
.race-card {
    position: relative;
    height: 300px;
    border-radius: 12px;
    overflow: hidden;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: var(--shadow);
    border: none;
}
```
Заменить на:
```css
.race-card {
    position: relative;
    height: 300px;
    border-radius: 12px;
    overflow: hidden;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: var(--km-shadow);
    border: none;
}
```

- [ ] **Step 3: Заменить `.race-card-overlay`/`.race-card-content`/`.race-card-title`/`.race-card-description` на `.race-card-badge`**

Найти:
```css
.race-card:hover .race-card-image {
    transform: scale(1.04);
}

.race-card-overlay {
    position: absolute;
    width: 100%;
    height: 100%;
    background: linear-gradient(to bottom, rgba(0, 0, 0, 0.05), rgba(0, 0, 0, 0.35));
    z-index: 1;
    transition: background 0.3s ease;
}

.race-card:hover .race-card-overlay {
    background: linear-gradient(to bottom, rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.65));
}

.race-card-content {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 28px 24px;
    color: var(--white);
    z-index: 2;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    height: 100%;
}

.race-card-title {
    font-size: 24px;
    font-weight: 600;
    margin-bottom: 10px;
    line-height: 1.2;
    letter-spacing: 0.3px;
}

.race-card-description {
    font-size: 13px;
    opacity: 0.95;
    line-height: 1.5;
    font-weight: 500;
}
```
Заменить на:
```css
.race-card:hover .race-card-image {
    transform: scale(1.04);
}

.race-card-badge {
    position: absolute;
    top: 12px;
    left: 12px;
    z-index: 2;
    background: var(--km-bg-card);
    color: var(--km-text-body);
    padding: 6px 14px;
    border-radius: var(--km-radius-btn);
    font-size: 13px;
    font-weight: 600;
    box-shadow: var(--km-shadow);
}
```

- [ ] **Step 4: Удалить мёртвый код `.race-info-section .info-row`/`.info-label`/`.info-value`**

Найти:
```css
.race-info,
.race-info-section {
    padding: 0;
}

.section-title {
```
Заменить на:
```css
.race-info {
    padding: 0;
}

.section-title {
```

Затем найти (следующий блок, идущий сразу после `.section-title { ... }`):
```css
/* Информация о забеге */
.race-info-section .info-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 10px 0;
    border-bottom: 1px solid #f5f5f5;
}

.race-info-section .info-row:last-child {
    border-bottom: none;
}

.race-info-section .info-label {
    font-weight: 600;
    color: var(--text-dark);
    flex: 0 0 auto;
    margin-right: 12px;
}

.race-info-section .info-value {
    color: var(--text-light);
    text-align: right;
    flex: 1;
}

/* Сетка статистики */
```
Заменить на:
```css
/* Сетка статистики */
```

- [ ] **Step 5: Очистить мобильный `@media` от правил для удалённых классов**

Найти (второй блок `@media (max-width: 768px)` в конце файла):
```css
@media (max-width: 768px) {
    .race-analysis-container {
        padding: 20px 20px;
    }

    .back-button {
        padding: 0 20px;
        margin-bottom: 25px;
    }

    .race-cards-container {
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 15px;
    }

    .race-card {
        height: 220px;
    }

    .race-card-title {
        font-size: 16px;
    }

    .race-card-content {
        padding: 18px 16px;
    }

    .race-analysis-header h1 {
        font-size: 28px;
    }

    .race-analysis-header p {
        font-size: 14px;
    }

    .back-button a {
        font-size: 14px;
        padding: 10px 20px;
    }

    .race-modal-container {
        padding: 30px 24px;
        width: 95%;
    }

    .race-modal-title {
        font-size: 24px;
    }

    .race-modal-close {
        width: 28px;
        height: 28px;
        font-size: 24px;
    }

    .race-card-content { display: none; }
}
```
Заменить на:
```css
@media (max-width: 768px) {
    .back-button {
        padding: 0 20px;
        margin-bottom: 25px;
    }

    .race-cards-container {
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 15px;
    }

    .race-card {
        height: 220px;
    }

    .race-analysis-header h1 {
        font-size: 28px;
    }

    .race-analysis-header p {
        font-size: 14px;
    }

    .back-button a {
        font-size: 14px;
        padding: 10px 20px;
    }

    .race-modal-container {
        padding: 30px 24px;
        width: 95%;
    }

    .race-modal-title {
        font-size: 24px;
    }

    .race-modal-close {
        width: 28px;
        height: 28px;
        font-size: 24px;
    }
}
```

- [ ] **Step 6: Проверить, что удалённые классы не остались нигде в CSS**

Run: `grep -n "race-analysis-container\|race-card-overlay\|race-card-content\|race-card-title\|race-card-description\|race-info-section" static/css/race-analysis.css`
Expected: пусто (нет вывода)

Run: `grep -c "race-card-badge" static/css/race-analysis.css`
Expected: `1`

- [ ] **Step 7: Commit**

```bash
git add static/css/race-analysis.css
git commit -m "fix(krasmarafon): race-analysis.css — удалить мёртвый CSS, добавить .race-card-badge"
```

---

### Task 3: CSS — токены (`--white`/`--shadow`/`--text-dark`/`--text-light` → `--km-*`)

**Files:**
- Modify: `static/css/race-analysis.css`

Это точечные замены отсутствующих переменных на существующие `--km-*` токены — без изменения структуры/значений, где переменная используется как цвет/фон/тень. Один случай (`.back-button a:hover`) — не токен, а литерал `#fff` (см. обоснование в спеке).

- [ ] **Step 1: Заголовок страницы (`.race-analysis-header h1`/`p`)**

Найти:
```css
.race-analysis-header h1 {
    font-size: 36px;
    color: var(--text-dark);
    margin: 20px 0 30px;
    font-weight: 600;
    text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.05);
}
```
Заменить на:
```css
.race-analysis-header h1 {
    font-size: 36px;
    color: var(--km-text-body);
    margin: 20px 0 30px;
    font-weight: 600;
    text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.05);
}
```

Найти:
```css
.race-analysis-header p {
    font-size: 16px;
    color: var(--text-light);
    line-height: 1.8;
    max-width: 600px;
    margin: 0 auto;
}
```
Заменить на:
```css
.race-analysis-header p {
    font-size: 16px;
    color: var(--km-text-secondary);
    line-height: 1.8;
    max-width: 600px;
    margin: 0 auto;
}
```

- [ ] **Step 2: Кнопка «Назад» (`.back-button a`, включая hover)**

Найти:
```css
.back-button a {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 24px;
    background-color: var(--white);
    color: var(--km-primary, #EE2D62);
    font-weight: 600;
    text-decoration: none;
    border: 2px solid var(--km-primary, #EE2D62);
    border-radius: 50px;
    transition: all 0.3s ease;
    font-size: 15px;
    box-shadow: var(--shadow);
}
```
Заменить на:
```css
.back-button a {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 24px;
    background-color: var(--km-bg-card);
    color: var(--km-primary, #EE2D62);
    font-weight: 600;
    text-decoration: none;
    border: 2px solid var(--km-primary, #EE2D62);
    border-radius: 50px;
    transition: all 0.3s ease;
    font-size: 15px;
    box-shadow: var(--km-shadow);
}
```

Найти:
```css
.back-button a:hover {
    background-color: var(--km-primary, #EE2D62);
    color: var(--white);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(238, 45, 98, 0.3);
}
```
Заменить на:
```css
.back-button a:hover {
    background-color: var(--km-primary, #EE2D62);
    color: #fff;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(238, 45, 98, 0.3);
}
```

- [ ] **Step 3: Модальное окно (контейнер, кнопка закрытия, заголовок, текст)**

Найти:
```css
.race-modal-container {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background-color: var(--white);
    border-radius: 12px;
```
Заменить на:
```css
.race-modal-container {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background-color: var(--km-bg-card);
    border-radius: 12px;
```

Найти:
```css
.race-modal-close {
    position: absolute;
    top: 20px;
    right: 20px;
    background: none;
    border: none;
    font-size: 28px;
    color: var(--text-dark);
    cursor: pointer;
```
Заменить на:
```css
.race-modal-close {
    position: absolute;
    top: 20px;
    right: 20px;
    background: none;
    border: none;
    font-size: 28px;
    color: var(--km-text-body);
    cursor: pointer;
```

Найти:
```css
.race-modal-title {
    font-size: 28px;
    font-weight: 600;
    color: var(--text-dark);
    margin: 0 0 20px 0;
}

.race-modal-body {
    font-size: 16px;
    color: var(--text-light);
    line-height: 1.6;
}
```
Заменить на:
```css
.race-modal-title {
    font-size: 28px;
    font-weight: 600;
    color: var(--km-text-body);
    margin: 0 0 20px 0;
}

.race-modal-body {
    font-size: 16px;
    color: var(--km-text-secondary);
    line-height: 1.6;
}
```

- [ ] **Step 4: Индикатор загрузки графика (`.chart-loader`)**

Найти:
```css
.chart-loader {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 300px;
    color: var(--text-light);
    font-size: 14px;
}
```
Заменить на:
```css
.chart-loader {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 300px;
    color: var(--km-text-secondary);
    font-size: 14px;
}
```

- [ ] **Step 5: Проверить, что `--white`/`--shadow` больше нигде не используются**

Run: `grep -n "var(--white)\|var(--shadow)" static/css/race-analysis.css`
Expected: пусто (нет вывода) — все 6 использований этих двух имён (2×`--shadow`, 4×`--white`) к этому моменту либо заменены на `--km-*`/`#fff` (в этой задаче и в Task 2 Step 2), либо удалены вместе с мёртвым кодом (Task 2 Step 3/4)

Не проверяем здесь `var(--text-dark)\|var(--text-light)` — 7 их вхождений (в `.stat-label`/`.stat-value`/`.best-runner-name`/`.best-year`/`.metric-label`/`.pace-label`/`.pace-value`) чинятся в Task 4, не в этой задаче. Полная проверка всех пяти переменных — в Task 4 Step 3.

- [ ] **Step 6: Commit**

```bash
git add static/css/race-analysis.css
git commit -m "fix(krasmarafon): race-analysis.css — токены --white/--shadow/--text-dark/--text-light на --km-*"
```

---

### Task 4: CSS — плоские карточки статистики в модалке (вместо цветных градиентов)

**Files:**
- Modify: `static/css/race-analysis.css`

- [ ] **Step 1: `.section-title` — убрать цветной акцент и подчёркивание**

Найти:
```css
.section-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--km-primary, #EE2D62);
    margin: 0 0 16px 0;
    padding-bottom: 10px;
    border-bottom: 2px solid #f0f0f0;
}
```
Заменить на:
```css
.section-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--km-text-body);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 16px 0;
}
```

- [ ] **Step 2: Блоки статистики/лучшего результата/темпа — плоский стиль**

Найти (весь блок от `/* Сетка статистики */` до конца `.pace-value`):
```css
/* Сетка статистики */
.race-stats-section {
    margin: 0;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
}

.stat-item {
    background-color: #f8f9fa;
    padding: 16px;
    border-radius: 8px;
    text-align: center;
    border-left: 4px solid var(--km-primary, #EE2D62);
}

.stat-item:nth-child(2) {
    border-left-color: #059C43;
}

.stat-item:nth-child(3) {
    border-left-color: #85c6e2;
}

.stat-item:nth-child(4) {
    border-left-color: #562872;
}

.stat-label {
    font-size: 13px;
    color: var(--text-light);
    margin-bottom: 8px;
    font-weight: 500;
}

.stat-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--text-dark);
}

/* Лучший результат */
.race-best-section {
    margin: 0;
}

.best-result {
    background: linear-gradient(135deg, #fff5f8 0%, #fffbfc 100%);
    padding: 20px;
    border-radius: 8px;
    border-left: 4px solid var(--km-primary, #EE2D62);
}

.best-runner-name {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-dark);
    margin-bottom: 4px;
}

.best-year {
    font-size: 12px;
    color: var(--text-light);
    font-weight: 500;
    margin-bottom: 12px;
}

.distance-block + .distance-block {
    border-top: 2px solid #f0f0f0;
    padding-top: 16px;
    margin-top: 8px;
}

.distance-block-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--km-primary, #EE2D62);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--km-primary, #EE2D62);
}

.best-result-metrics {
    display: flex;
    gap: 20px;
}

.best-result-metrics .metric {
    flex: 1;
}

.metric-label {
    display: block;
    font-size: 12px;
    color: var(--text-light);
    margin-bottom: 4px;
    font-weight: 500;
}

.metric-value {
    display: block;
    font-size: 16px;
    font-weight: 600;
    color: var(--km-primary, #EE2D62);
}

/* Средние темпы */
.race-pace-section {
    margin: 0;
}

.pace-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
}

.pace-item {
    background-color: #f0f8ff;
    padding: 16px;
    border-radius: 8px;
    text-align: center;
    border-top: 3px solid #00BFDF;
}

.pace-item:nth-child(2) {
    background-color: #f8f5ff;
    border-top-color: #562872;
}

.pace-item:nth-child(3) {
    background-color: #fff5f8;
    border-top-color: var(--km-primary, #EE2D62);
}

.pace-label {
    font-size: 12px;
    color: var(--text-light);
    margin-bottom: 8px;
    font-weight: 500;
}

.pace-value {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-dark);
    font-family: 'Courier New', monospace;
}
```
Заменить на:
```css
/* Сетка статистики */
.race-stats-section {
    margin: 0;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
}

.stat-item {
    background: var(--km-bg-card);
    border: 1px solid var(--km-border-light);
    padding: 16px;
    border-radius: var(--km-radius-card);
    text-align: center;
}

.stat-label {
    font-size: 13px;
    color: var(--km-text-secondary);
    margin-bottom: 8px;
    font-weight: 500;
}

.stat-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--km-text-body);
}

/* Лучший результат */
.race-best-section {
    margin: 0;
}

.best-result {
    background: var(--km-bg-card);
    border: 1px solid var(--km-border-light);
    padding: 20px;
    border-radius: var(--km-radius-card);
}

.best-runner-name {
    font-size: 18px;
    font-weight: 600;
    color: var(--km-text-body);
    margin-bottom: 4px;
}

.best-year {
    font-size: 12px;
    color: var(--km-text-secondary);
    font-weight: 500;
    margin-bottom: 12px;
}

.distance-block + .distance-block {
    border-top: 2px solid var(--km-border-light);
    padding-top: 16px;
    margin-top: 8px;
}

.distance-block-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--km-text-body);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 16px;
}

.best-result-metrics {
    display: flex;
    gap: 20px;
}

.best-result-metrics .metric {
    flex: 1;
}

.metric-label {
    display: block;
    font-size: 12px;
    color: var(--km-text-secondary);
    margin-bottom: 4px;
    font-weight: 500;
}

.metric-value {
    display: block;
    font-size: 16px;
    font-weight: 600;
    color: var(--km-primary, #EE2D62);
}

/* Средние темпы */
.race-pace-section {
    margin: 0;
}

.pace-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
}

.pace-item {
    background: var(--km-bg-card);
    border: 1px solid var(--km-border-light);
    padding: 16px;
    border-radius: var(--km-radius-card);
    text-align: center;
}

.pace-label {
    font-size: 12px;
    color: var(--km-text-secondary);
    margin-bottom: 8px;
    font-weight: 500;
}

.pace-value {
    font-size: 20px;
    font-weight: 700;
    color: var(--km-text-body);
    font-family: 'Courier New', monospace;
}
```

- [ ] **Step 3: Проверить, что цветные градиенты/border-left/border-top акценты убраны**

Run: `grep -n "linear-gradient\|border-left: 4px\|border-top: 3px\|#f8f9fa\|#f0f8ff\|#f8f5ff" static/css/race-analysis.css`
Expected: пусто (нет вывода)

Run: `grep -c "var(--km-border-light)" static/css/race-analysis.css`
Expected: `4` (stat-item, best-result, pace-item, distance-block-разделитель)

- [ ] **Step 3b: Финальная проверка — ни одной из пяти несуществующих переменных не осталось нигде в файле**

Run: `grep -n "var(--white)\|var(--shadow)\|var(--text-dark)\|var(--text-light)\|var(--background)" static/css/race-analysis.css`
Expected: пусто (нет вывода) — это финальная сводная проверка по всем пяти именам сразу (Task 2 удалила часть вхождений вместе с мёртвым кодом, Task 3 починила остальные кроме тех, что внутри блока статистики, Task 4 Step 2 только что починила последние 7)

- [ ] **Step 4: Commit**

```bash
git add static/css/race-analysis.css
git commit -m "feat(krasmarafon): race-analysis.css — плоские карточки статистики вместо градиентов"
```

---

### Task 5: Полная верификация — тесты + визуальная проверка в браузере

**Files:** нет изменений, только проверка

- [ ] **Step 1: Полный прогон существующего тестового набора**

Run: `conda run -n base python -m pytest tests/unit/ tests/integration/ -q --deselect tests/integration/test_api_runners.py`
Expected: все тесты проходят (без новых падений по сравнению с состоянием до этой ветки — `race-analysis.html`/`race-analysis.css`/`race-analysis.js` не покрыты собственными тестами ни до, ни после)

- [ ] **Step 2: Запустить dev-сервер**

Run (в фоне): `conda run -n base python -m uvicorn app:app --host 127.0.0.1 --port 8129`

Подождать готовности: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8129/race-analysis` (повторять с паузой ~2 сек, пока не вернётся `200` — старт может занимать 10+ сек)

- [ ] **Step 3: Визуальная проверка сетки карточек (десктоп)**

```bash
agent-browser open http://127.0.0.1:8129/race-analysis
agent-browser set viewport 1280 900
agent-browser screenshot ".superpowers/race-analysis-cards-desktop.png"
```

Проверить на скриншоте: у каждой из 8 карточек — компактная белая плашка с названием в левом верхнем углу, фото-лого показано полностью (без второго слоя текста снизу), карточки с тенью.

- [ ] **Step 4: Визуальная проверка модалки с реальными данными (обойти отсутствие БД в dev)**

Локальная БД скорее всего не содержит кросс-годовой статистики ни для одного события (API вернёт 404/пусто) — чтобы проверить именно "успешный" вид модалки (не fallback-текст), подменить `loadRaceStats` фикстурой прямо в браузере перед кликом:

```bash
agent-browser eval "loadRaceStats = async function() { return { distances: [{ distance: '5 км', years_data: [{ year: 2026, total_runners: 120, finished_runners: 115, male_count: 60, female_count: 60 }, { year: 2025, total_runners: 95, finished_runners: 90, male_count: 50, female_count: 45 }], best_result: { surname: 'Иванов', name: 'Иван', year: 2026, time: '00:16:42', pace: '3:20' }, average_paces: { all: '4:30', male: '4:10', female: '4:50' } }] }; };"
agent-browser find text "Весна" click
```

Подождать ~1 сек (рендер + отрисовка Chart.js), затем:

```bash
agent-browser screenshot ".superpowers/race-analysis-modal-desktop.png"
```

Проверить на скриншоте: модальное окно — непрозрачный белый фон с тенью (не просвечивает сквозь карточки за ним), карточки статистики (`Всего участников`/`Финишировали`/`Мужчин`/`Женщин`, лучший результат, средние темпы) — плоские, белые, с тонкой серой рамкой, без цветных градиентов; заголовки секций — некрупный uppercase-лейбл без цветного подчёркивания; цифры времени/темпа в лучшем результате — розовые (`--km-primary`); график по годам отрисован (2 точки, 4 цветные линии).

- [ ] **Step 5: Визуальная проверка на мобильной ширине**

```bash
agent-browser set viewport 390 800
agent-browser screenshot ".superpowers/race-analysis-mobile.png"
```

Закрыть модалку и проверить сетку карточек на мобильной ширине:

```bash
agent-browser eval "document.querySelector('.race-modal-close').click();"
agent-browser screenshot ".superpowers/race-analysis-cards-mobile.png"
```

Проверить: плашки-названия видны и не обрезаны на узких карточках (2 колонки на 390px), карточки не разъезжаются.

- [ ] **Step 6: Закрыть браузер и остановить dev-сервер**

```bash
agent-browser close
```

Остановить фоновый процесс uvicorn (`TaskStop` на task_id, полученный в Step 2).

- [ ] **Step 7: Итоговая проверка на отсутствие сломанных ссылок на удалённые классы**

Run: `grep -rn "race-card-overlay\|race-card-content\|race-card-title\|race-card-description\|race-analysis-container\|race-info-section" templates/krasmarafon/race-analysis.html static/css/race-analysis.css static/js/race-analysis.js`
Expected: пусто (нет вывода) во всех трёх файлах

Если все проверки прошли — задача полностью готова, отдельного коммита на этом шаге не требуется (Task 1-4 уже закоммичены).
