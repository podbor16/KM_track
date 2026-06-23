# Triatleta Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать эмодзи из UI, переписать CSS/HTML под светлую тему с тёмной брендовой шапкой по палитре race.triatleta.ru.

**Architecture:** Полный переписать трёх файлов — `tri_results.css` (единый CSS для обеих страниц), `tri_results.html` (публичная страница), `tri_admin.html` (панель управления). JS-логика в шаблонах не трогается. Бэкенд не меняется.

**Tech Stack:** HTML, CSS (CSS custom properties), Google Fonts (Onest), Jinja2 шаблоны FastAPI.

---

## Task 1: Переписать tri_results.css

**Files:**
- Modify: `static/css/tri_results.css`

Единый CSS-файл теперь содержит стили для обеих страниц (results + admin). Инлайновые `<style>` блоки из обоих шаблонов переедут сюда.

- [ ] **Шаг 1: Заменить содержимое tri_results.css**

Полностью заменить файл `static/css/tri_results.css`:

```css
:root {
    --tri-bg: #f5f5f5;
    --tri-surface: #ffffff;
    --tri-border: #e8e8e8;
    --tri-accent: #FF8562;
    --tri-text: #050505;
    --tri-muted: #888888;
    --tri-navy: #263146;
    --tri-green: #18A558;
    --tri-red: #DE0000;
    --tri-header-bg: linear-gradient(135deg, #050505 0%, #263146 100%);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    background: var(--tri-bg);
    color: var(--tri-text);
    font-family: 'Onest', Arial, sans-serif;
    min-height: 100vh;
}

/* ---- Header ---- */
.tri-header {
    background: var(--tri-header-bg);
    border-bottom: 3px solid var(--tri-accent);
    padding: 18px 24px 20px;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
}
.tri-header__eyebrow {
    font-size: 11px;
    font-weight: 700;
    color: var(--tri-accent);
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 5px;
}
.tri-header__title {
    font-size: 22px;
    font-weight: 900;
    color: #fff;
    letter-spacing: -0.5px;
    line-height: 1.1;
}
.tri-header__meta {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.45);
    margin-top: 6px;
}
.tri-elapsed-wrap { text-align: right; }
.tri-elapsed-label { font-size: 11px; color: rgba(255, 255, 255, 0.4); margin-bottom: 2px; }
.tri-elapsed {
    font-size: 32px;
    font-weight: 900;
    color: var(--tri-accent);
    font-variant-numeric: tabular-nums;
    letter-spacing: -1px;
    line-height: 1;
}

/* ---- Container ---- */
.tri-container { max-width: 1100px; margin: 0 auto; padding: 20px 16px; }

/* ---- Toolbar (results page) ---- */
.tri-toolbar {
    background: var(--tri-surface);
    border-bottom: 1px solid var(--tri-border);
    padding: 10px 24px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}
.tri-filter-group { display: flex; align-items: center; gap: 6px; }
.tri-label { font-size: 13px; color: var(--tri-muted); white-space: nowrap; }
.tri-select,
.tri-search {
    background: #f5f5f5;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    color: var(--tri-text);
    padding: 7px 12px;
    font-size: 13px;
    font-family: 'Onest', Arial, sans-serif;
    outline: none;
}
.tri-select:focus,
.tri-search:focus { border-color: var(--tri-accent); }
.tri-search { width: 180px; }
.tri-search::placeholder { color: var(--tri-muted); }
.tri-results-count { margin-left: auto; font-size: 12px; color: var(--tri-muted); }

/* ---- Table ---- */
.tri-table-wrap {
    background: var(--tri-surface);
    border-radius: 10px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
    overflow: hidden;
}
table.tri-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.tri-table th {
    background: var(--tri-surface);
    color: var(--tri-navy);
    font-weight: 700;
    padding: 12px 14px;
    text-align: left;
    border-bottom: 2px solid var(--tri-border);
    white-space: nowrap;
}
.tri-table td {
    padding: 11px 14px;
    border-bottom: 1px solid #f0f0f0;
    color: var(--tri-text);
}
.tri-table tbody tr:last-child td { border-bottom: none; }
.tri-table tr:hover td { background: #fafafa; }
.tri-rank { font-weight: 800; width: 36px; }
.tri-name { font-weight: 600; }
.tri-gap--behind { color: var(--tri-red); }
.tri-gap--leader { color: var(--tri-green); font-weight: 700; }
.tri-speed { font-variant-numeric: tabular-nums; }

/* ---- Badges ---- */
.tri-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
}
.tri-badge--personal { background: #f0f0f0; color: #555; }
.tri-badge--relay    { background: #fff0ec; color: var(--tri-accent); }

/* ---- Splits ---- */
.tri-splits { margin-top: 24px; }
.tri-splits__title { font-size: 16px; font-weight: 800; color: var(--tri-text); margin-bottom: 14px; }
.tri-slider-wrap { display: flex; align-items: center; gap: 20px; margin-bottom: 14px; flex-wrap: wrap; }
.tri-slider-label { font-size: 13px; color: var(--tri-muted); min-width: 160px; }
input[type=range] { accent-color: var(--tri-accent); width: 140px; }
.tri-refresh { font-size: 12px; color: var(--tri-muted); margin-top: 8px; }

/* ---- Admin: tabs ---- */
.admin-tabs { display: flex; gap: 4px; margin: 24px 0 16px; }
.admin-tab {
    padding: 8px 20px;
    border: 1px solid var(--tri-border);
    border-radius: 6px;
    background: var(--tri-surface);
    color: var(--tri-muted);
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    font-family: 'Onest', Arial, sans-serif;
}
.admin-tab.active { background: var(--tri-accent); color: #000; border-color: var(--tri-accent); }
.tab-pane { display: none; }
.tab-pane.active { display: block; }

/* ---- Admin: cards ---- */
.admin-card {
    background: var(--tri-surface);
    border: 1px solid var(--tri-border);
    border-radius: 8px;
    padding: 20px;
    max-width: 700px;
    margin-bottom: 12px;
}
.admin-card__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.admin-card__title { font-size: 15px; font-weight: 700; color: var(--tri-accent); }

/* ---- Admin: status badges ---- */
.admin-badge { display: inline-block; padding: 3px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; }
.admin-badge--active   { background: rgba(24, 165, 88, 0.12); color: var(--tri-green); }
.admin-badge--inactive { background: rgba(222, 0, 0, 0.10); color: var(--tri-red); }

/* ---- Admin: buttons ---- */
.btn-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.adm-btn {
    padding: 8px 18px;
    border-radius: 6px;
    border: none;
    font-size: 13px;
    font-weight: 600;
    font-family: 'Onest', Arial, sans-serif;
    cursor: pointer;
    transition: opacity 0.15s;
}
.adm-btn:disabled { opacity: 0.4; cursor: default; }
.adm-btn--start  { background: var(--tri-green); color: #fff; }
.adm-btn--stop   { background: var(--tri-surface); border: 1px solid var(--tri-border); color: var(--tri-text); }
.adm-btn--init   { background: var(--tri-surface); border: 1px solid var(--tri-border); color: var(--tri-text); }
.adm-btn--edit   { background: var(--tri-surface); border: 1px solid var(--tri-border); color: var(--tri-text); }
.adm-btn--save   { background: var(--tri-accent); color: #000; }
.adm-btn--cancel { background: var(--tri-surface); border: 1px solid var(--tri-border); color: var(--tri-text); }

/* ---- Admin: loader table ---- */
.admin-loader-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.admin-loader-table th,
.admin-loader-table td {
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid var(--tri-border);
}
.admin-loader-table th { color: var(--tri-muted); font-weight: 600; font-size: 12px; }
.admin-loader-table tbody tr:last-child td { border-bottom: none; }

/* ---- Admin: preset editor ---- */
.admin-editor { margin-top: 14px; }
.admin-editor__error {
    background: rgba(222, 0, 0, 0.07);
    border: 1px solid var(--tri-red);
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 10px;
    font-size: 13px;
    color: var(--tri-red);
}
.admin-yaml-editor {
    width: 100%;
    height: 280px;
    background: #f5f5f5;
    color: var(--tri-text);
    border: 1px solid var(--tri-border);
    border-radius: 6px;
    padding: 12px;
    font-family: "Courier New", monospace;
    font-size: 13px;
    line-height: 1.5;
    resize: vertical;
    box-sizing: border-box;
}
.admin-editor__actions { display: flex; gap: 8px; margin-top: 10px; }

/* ---- Admin: misc ---- */
.init-result { font-size: 12px; }
.admin-loading { color: var(--tri-muted); font-size: 14px; padding: 12px 0; }
.admin-error   { color: var(--tri-red); font-size: 14px; padding: 12px 0; }
.admin-section-note {
    color: var(--tri-muted);
    font-size: 13px;
    background: var(--tri-surface);
    border: 1px solid var(--tri-border);
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 16px;
    max-width: 700px;
}

/* ---- Logout (header) ---- */
.logout-btn {
    padding: 7px 16px;
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 4px;
    color: rgba(255, 255, 255, 0.6);
    font-size: 13px;
    font-family: 'Onest', Arial, sans-serif;
    cursor: pointer;
    text-decoration: none;
    align-self: flex-start;
}
.logout-btn:hover { border-color: var(--tri-accent); color: var(--tri-accent); }
```

- [ ] **Шаг 2: Визуально проверить CSS**

Открыть в браузере `http://localhost:8000/tri` — должен примениться новый CSS (пока шаблоны не обновлены, страница будет выглядеть частично сломанной — это ожидаемо).

---

## Task 2: Переписать tri_results.html

**Files:**
- Modify: `templates/tri_results.html`

Убираем инлайновый `<style>`, добавляем Google Fonts, новую шапку, убираем `🚴`, обновляем JS-рендер строк (бейджи зачётов), добавляем классы `tri-name` и `tri-table-wrap` на обёртки таблиц.

- [ ] **Шаг 1: Заменить tri_results.html**

Полностью заменить `templates/tri_results.html`:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Triatleta — Суточная велогонка 24ч</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/tri_results.css?v={{ v }}">
</head>
<body>
    <div class="tri-header">
        <div>
            <div class="tri-header__eyebrow">Triatleta · 24 часа</div>
            <div class="tri-header__title">Суточная велогонка<br>25–26 июня 2026</div>
            <div class="tri-header__meta">Красноярск · Триатлон-центр · Круг: 4.04 км</div>
        </div>
        <div class="tri-elapsed-wrap">
            <div class="tri-elapsed-label">Прошло</div>
            <div class="tri-elapsed" id="elapsed">—</div>
        </div>
    </div>

    <!-- Фильтры -->
    <div class="tri-toolbar">
        <div class="tri-filter-group">
            <label class="tri-label">Зачёт:</label>
            <select id="filter-category" class="tri-select" onchange="applyFilters()">
                <option value="">Все</option>
                <option value="individual">Личный</option>
                <option value="relay">Командный</option>
            </select>
        </div>
        <div class="tri-filter-group">
            <label class="tri-label">Пол:</label>
            <select id="filter-gender" class="tri-select" onchange="applyFilters()">
                <option value="">Все</option>
                <option value="M">Мужчины</option>
                <option value="F">Женщины</option>
            </select>
        </div>
        <div class="tri-filter-group">
            <input type="search" id="filter-search" class="tri-search"
                   placeholder="Поиск по фамилии"
                   oninput="applyFilters()" onkeydown="if(event.key==='Enter')applyFilters()">
        </div>
        <span class="tri-results-count" id="results-count"></span>
    </div>

    <div class="tri-container">

        <!-- Таблица результатов -->
        <div class="tri-table-wrap">
            <table class="tri-table">
                <thead>
                    <tr>
                        <th class="tri-rank">#</th>
                        <th>Участник</th>
                        <th>Зачёт</th>
                        <th>Кругов</th>
                        <th>Км</th>
                        <th>Время</th>
                        <th>Скорость</th>
                        <th>Отставание</th>
                    </tr>
                </thead>
                <tbody id="standings-body">
                    <tr><td colspan="8" style="text-align:center;color:var(--tri-muted);padding:24px">Загрузка...</td></tr>
                </tbody>
            </table>
        </div>
        <div class="tri-refresh" id="refresh-label"></div>

        <!-- Сплиты -->
        <div class="tri-splits">
            <div class="tri-splits__title">Сплиты по часам</div>
            <div class="tri-slider-wrap">
                <label class="tri-slider-label">
                    С часа: <span id="from-val">1</span>
                    <input type="range" id="from-slider" min="1" max="24" value="1" oninput="onSlider()">
                </label>
                <label class="tri-slider-label">
                    По час: <span id="to-val">24</span>
                    <input type="range" id="to-slider" min="1" max="24" value="24" oninput="onSlider()">
                </label>
            </div>
            <div class="tri-table-wrap">
                <table class="tri-table">
                    <thead>
                        <tr>
                            <th>Участник</th>
                            <th>Кругов за период</th>
                            <th>Км за период</th>
                        </tr>
                    </thead>
                    <tbody id="splits-body">
                        <tr><td colspan="3" style="text-align:center;color:var(--tri-muted);padding:16px">Ожидание данных...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
    const GUN_UTC_MS = new Date('2026-06-25T13:00:00Z').getTime();
    const LAP_KM = 4.040;
    let allStandings = [];
    let allLaps = [];

    // ---- Счётчик прошедшего времени ----
    function updateElapsed() {
        const now = Date.now();
        const diff = Math.max(0, now - GUN_UTC_MS);
        const h = Math.floor(diff / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        const s = Math.floor((diff % 60000) / 1000);
        document.getElementById('elapsed').textContent =
            `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    }
    setInterval(updateElapsed, 1000);
    updateElapsed();

    function fmtMs(ms) {
        if (!ms) return '—';
        const s = Math.floor(ms / 1000);
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const ss = s % 60;
        return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}`;
    }

    async function loadStandings() {
        try {
            const r = await fetch('/api/tri/standings');
            const data = await r.json();
            allStandings = data.standings || [];
            applyFilters();
            document.getElementById('refresh-label').textContent =
                `Обновлено: ${new Date().toLocaleTimeString('ru-RU')}`;
        } catch(e) { console.error('standings error', e); }
    }

    function applyFilters() {
        const category = document.getElementById('filter-category').value;
        const gender   = document.getElementById('filter-gender').value;
        const search   = document.getElementById('filter-search').value.trim().toLowerCase();

        let rows = allStandings.filter(r => {
            if (category && r.category !== category) return false;
            if (gender   && r.gender !== gender)     return false;
            if (search   && !(r.surname || '').toLowerCase().includes(search)) return false;
            return true;
        });

        document.getElementById('results-count').textContent =
            rows.length ? `${rows.length} участн.` : '';

        renderStandings(rows);
    }

    function renderStandings(rows) {
        const tbody = document.getElementById('standings-body');
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--tri-muted);padding:24px">Нет данных</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map((r, i) => {
            const gapClass = r.gap === '—' ? 'tri-gap--leader' : 'tri-gap--behind';
            const badgeClass = r.category === 'relay' ? 'tri-badge--relay' : 'tri-badge--personal';
            const categoryLabel = r.category === 'relay' ? 'Эстафета' : 'Личный';
            return `<tr>
                <td class="tri-rank">${i + 1}</td>
                <td class="tri-name">${r.surname} ${r.name}</td>
                <td><span class="tri-badge ${badgeClass}">${categoryLabel}</span></td>
                <td>${r.laps_completed}</td>
                <td>${parseFloat(r.total_km).toFixed(1)}</td>
                <td style="font-variant-numeric:tabular-nums">${fmtMs(r.elapsed_ms)}</td>
                <td class="tri-speed">${parseFloat(r.avg_speed_kmh).toFixed(1)} км/ч</td>
                <td class="${gapClass}">${r.gap}</td>
            </tr>`;
        }).join('');
    }

    async function loadLaps() {
        try {
            const r = await fetch('/api/tri/laps');
            const data = await r.json();
            allLaps = data.laps || [];
            renderSplits();
        } catch(e) { console.error('laps error', e); }
    }

    function onSlider() {
        const fromH = parseInt(document.getElementById('from-slider').value);
        let toH = parseInt(document.getElementById('to-slider').value);
        if (toH < fromH) { toH = fromH; document.getElementById('to-slider').value = fromH; }
        document.getElementById('from-val').textContent = fromH;
        document.getElementById('to-val').textContent = toH;
        renderSplits();
    }

    function renderSplits() {
        const fromH = parseInt(document.getElementById('from-slider').value);
        const toH   = parseInt(document.getElementById('to-slider').value);
        const fromMs = (fromH - 1) * 3600000;
        const toMs   = toH * 3600000;
        const byParticipant = {};
        for (const lap of allLaps) {
            if (lap.cumulative_ms > fromMs && lap.cumulative_ms <= toMs) {
                const key = lap.participant_id;
                if (!byParticipant[key]) byParticipant[key] = { name: `${lap.surname} ${lap.name}`, count: 0 };
                byParticipant[key].count++;
            }
        }
        const rows = Object.values(byParticipant).sort((a, b) => b.count - a.count);
        const tbody = document.getElementById('splits-body');
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--tri-muted);padding:16px">Нет кругов в выбранном диапазоне</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(r => `<tr>
            <td class="tri-name">${r.name}</td>
            <td>${r.count}</td>
            <td>${(r.count * LAP_KM).toFixed(1)}</td>
        </tr>`).join('');
    }

    loadStandings();
    loadLaps();
    setInterval(() => { loadStandings(); loadLaps(); }, 30000);
    </script>
</body>
</html>
```

- [ ] **Шаг 2: Проверить страницу результатов**

Открыть `http://localhost:8000/tri`. Проверить:
- Тёмная градиентная шапка с оранжевым eyebrow и белым заголовком
- Таймер справа в шапке оранжевый
- Фильтры — белая полоска под шапкой, светло-серые инпуты
- Таблица — белая карточка с тенью, заголовки тёмно-синие
- Бейдж «Личный» серый, «Эстафета» лосось
- Нет никаких эмодзи

---

## Task 3: Переписать tri_admin.html

**Files:**
- Modify: `templates/tri_admin.html`

Убираем инлайновый `<style>`, добавляем Google Fonts, новую тёмную шапку (без `🔧`), убираем все цвета из inline-стилей (теперь они в CSS). JS-логика не меняется.

- [ ] **Шаг 1: Заменить tri_admin.html**

Полностью заменить `templates/tri_admin.html`:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Triatleta — Управление</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/tri_results.css?v={{ v }}">
</head>
<body>
    <div class="tri-header">
        <div>
            <div class="tri-header__eyebrow">Triatleta · Управление</div>
            <div class="tri-header__title">Панель управления</div>
            <div class="tri-header__meta"><a href="/tri" style="color:var(--tri-accent)">← Live результаты</a></div>
        </div>
        <a href="/logout" class="logout-btn">Выйти</a>
    </div>

    <div class="tri-container">
        <div class="admin-tabs">
            <button class="admin-tab active" onclick="switchTab('loader', this)">Загрузчик</button>
            <button class="admin-tab" onclick="switchTab('preset', this)">Пресет Copernico</button>
        </div>

        <!-- Загрузчик -->
        <div id="tab-loader" class="tab-pane active">
            <div class="admin-section-note">
                Управление сервисом <code>km_tri_loader@tri_24h</code> на сервере.
            </div>
            <div id="loader-wrap">
                <div class="admin-loading">Загрузка статуса...</div>
            </div>
        </div>

        <!-- Пресет -->
        <div id="tab-preset" class="tab-pane">
            <div id="preset-wrap">
                <div class="admin-loading">Загрузка...</div>
            </div>
        </div>
    </div>

    <script>
    function switchTab(name, btn) {
        document.querySelectorAll('.admin-tab').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + name).classList.add('active');
        if (name === 'preset') loadPreset();
    }

    // ---- Загрузчик ----

    async function loadLoader() {
        const wrap = document.getElementById('loader-wrap');
        try {
            const r = await fetch('/api/tri/admin/loader');
            if (!r.ok) throw new Error(await r.text());
            const loaders = await r.json();
            wrap.innerHTML = '';
            if (!loaders.length) {
                wrap.innerHTML = '<div class="admin-loading">Нет данных загрузчика</div>';
                return;
            }
            const table = document.createElement('table');
            table.className = 'admin-loader-table';
            table.innerHTML = `
                <thead><tr>
                    <th>Имя</th><th>Статус</th><th>Действия</th>
                </tr></thead>
                <tbody></tbody>`;
            loaders.forEach(l => table.querySelector('tbody').appendChild(buildLoaderRow(l)));
            wrap.appendChild(table);
        } catch(e) {
            wrap.innerHTML = `<div class="admin-error">Ошибка: ${e.message}</div>`;
        }
    }

    function buildLoaderRow(l) {
        const tr = document.createElement('tr');
        const isActive = l.status === 'active';
        tr.innerHTML = `
            <td><code>${l.name}</code></td>
            <td><span class="admin-badge ${isActive ? 'admin-badge--active' : 'admin-badge--inactive'}">${isActive ? 'active' : 'inactive'}</span></td>
            <td style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
                <button class="adm-btn adm-btn--start btn-start" ${isActive ? 'disabled' : ''}>Start</button>
                <button class="adm-btn adm-btn--stop btn-stop" ${!isActive ? 'disabled' : ''}>Stop</button>
                <button class="adm-btn adm-btn--init btn-init" title="Первичная загрузка участников из Copernico">Инициализация</button>
                <span class="init-result" style="display:none"></span>
            </td>`;

        tr.querySelector('.btn-start').addEventListener('click', () => loaderAction('start', tr));
        tr.querySelector('.btn-stop').addEventListener('click', () => loaderAction('stop', tr));
        tr.querySelector('.btn-init').addEventListener('click', () => loaderInit(tr));
        return tr;
    }

    async function loaderAction(action, tr) {
        const btnStart = tr.querySelector('.btn-start');
        const btnStop  = tr.querySelector('.btn-stop');
        const btnInit  = tr.querySelector('.btn-init');
        btnStart.disabled = true;
        btnStop.disabled  = true;
        btnInit.disabled  = true;
        try {
            const r = await fetch(`/api/tri/admin/loader/${action}`, {method: 'POST'});
            const d = await r.json();
            if (d.output) console.log(`loader ${action}:`, d.output);
        } catch(e) {
            alert('Ошибка: ' + e.message);
        }
        await new Promise(r => setTimeout(r, 1500));
        loadLoader();
    }

    async function loaderInit(tr) {
        const btn    = tr.querySelector('.btn-init');
        const result = tr.querySelector('.init-result');
        const btnStart = tr.querySelector('.btn-start');
        const btnStop  = tr.querySelector('.btn-stop');

        btn.disabled = true;
        btnStart.disabled = true;
        btnStop.disabled  = true;
        btn.textContent = 'Загрузка...';
        result.style.display = 'none';

        try {
            const r = await fetch('/api/tri/admin/loader/init', {method: 'POST'});
            const d = await r.json();
            result.style.display = 'inline';
            if (d.status === 'ok') {
                result.style.color = 'var(--tri-green)';
                result.textContent = `✓ Вставлено: ${d.inserted}`;
            } else {
                result.style.color = 'var(--tri-red)';
                result.textContent = '✗ Ошибка';
                console.error('Init error:', d.output);
            }
        } catch(e) {
            result.style.display = 'inline';
            result.style.color = 'var(--tri-red)';
            result.textContent = `✗ ${e.message}`;
        }

        btn.textContent = 'Инициализация';
        btn.disabled = false;
        loadLoader();
    }

    loadLoader();
    setInterval(loadLoader, 10000);

    // ---- Пресет ----

    let _presetLoaded = false;

    async function loadPreset() {
        if (_presetLoaded) return;
        _presetLoaded = true;

        const wrap = document.getElementById('preset-wrap');
        try {
            const r = await fetch('/api/tri/admin/preset');
            const d = await r.json();
            if (!r.ok) {
                wrap.innerHTML = `<div class="admin-error">Ошибка: ${d.detail || r.status}</div>`;
                return;
            }
            wrap.innerHTML = '';
            wrap.appendChild(buildPresetCard('tri_24h_2026', d.yaml));
        } catch(e) {
            wrap.innerHTML = `<div class="admin-error">Ошибка: ${e.message}</div>`;
        }
    }

    function buildPresetCard(name, yamlContent) {
        const card = document.createElement('div');
        card.className = 'admin-card';
        card.innerHTML = `
            <div class="admin-card__head">
                <div class="admin-card__title">${name}.yaml</div>
                <button class="adm-btn adm-btn--edit btn-edit">Редактировать</button>
            </div>
            <div class="admin-editor" style="display:none">
                <div class="admin-editor__error" style="display:none"></div>
                <textarea class="admin-yaml-editor" spellcheck="false"></textarea>
                <div class="admin-editor__actions">
                    <button class="adm-btn adm-btn--save btn-save">Сохранить</button>
                    <button class="adm-btn adm-btn--cancel btn-cancel">Отмена</button>
                </div>
            </div>`;

        const btnEdit = card.querySelector('.btn-edit');
        const editor  = card.querySelector('.admin-editor');
        const textarea = card.querySelector('.admin-yaml-editor');
        const errBox  = card.querySelector('.admin-editor__error');

        textarea.value = yamlContent;

        btnEdit.addEventListener('click', () => {
            if (editor.style.display !== 'none') {
                editor.style.display = 'none';
                btnEdit.textContent = 'Редактировать';
            } else {
                editor.style.display = '';
                btnEdit.textContent = 'Свернуть';
                errBox.style.display = 'none';
            }
        });

        card.querySelector('.btn-cancel').addEventListener('click', () => {
            editor.style.display = 'none';
            btnEdit.textContent = 'Редактировать';
        });

        card.querySelector('.btn-save').addEventListener('click', async () => {
            const btnSave = card.querySelector('.btn-save');
            btnSave.disabled = true;
            btnSave.textContent = 'Сохранение...';
            errBox.style.display = 'none';
            try {
                const r = await fetch('/api/tri/admin/preset', {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({yaml: textarea.value}),
                });
                const d = await r.json();
                if (r.ok) {
                    editor.style.display = 'none';
                    btnEdit.textContent = 'Редактировать';
                } else {
                    errBox.textContent = d.detail || 'Ошибка сохранения';
                    errBox.style.display = '';
                }
            } catch(e) {
                errBox.textContent = 'Ошибка сети: ' + e.message;
                errBox.style.display = '';
            } finally {
                btnSave.disabled = false;
                btnSave.textContent = 'Сохранить';
            }
        });

        return card;
    }

    document.addEventListener('keydown', e => {
        if (e.key === 'Tab' && e.target.classList.contains('admin-yaml-editor')) {
            e.preventDefault();
            const ta = e.target;
            const s = ta.selectionStart, en = ta.selectionEnd;
            ta.value = ta.value.substring(0, s) + '  ' + ta.value.substring(en);
            ta.selectionStart = ta.selectionEnd = s + 2;
        }
    });
    </script>
</body>
</html>
```

- [ ] **Шаг 2: Проверить панель управления**

Открыть `http://localhost:8000/tri/admin`. Проверить:
- Тёмная шапка, eyebrow «TRIATLETA · УПРАВЛЕНИЕ», заголовок «Панель управления»
- Нет `🔧`
- Вкладки светлые, активная — лосось
- Карточка загрузчика белая, кнопки читаемы
- Бейдж статуса зелёный/красный

---

## Task 4: Commit

- [ ] **Шаг 1: Зафиксировать изменения**

```bash
git add static/css/tri_results.css templates/tri_results.html templates/tri_admin.html
git commit -m "feat: triatleta redesign — light theme + dark header + Onest font, no emojis"
```

- [ ] **Шаг 2: Push**

```bash
git push
```

Деплой применит изменения на сервере автоматически через CI.
