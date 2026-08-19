# Генератор постов Топ-3 для трансляции Жары — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Новая вкладка «Трансляция» в `/admin` Красмарафона, которая по выбранным дистанции («5 км»/«21.1 км») и отметке генерирует два готовых к копированию текстовых поста — «Топ-3 мужчины» и «Топ-3 женщины» — для соцсетей/мессенджера.

**Architecture:** Чисто клиентская фича, backend не меняется. Данные уже существуют — `generate_top10_json()` (`src/krasmarafon/services/live_top10_export.py`) пишет их в статичные JSON-файлы `/live/zhara_5km_top10.json`/`/live/zhara_21km_top10.json` во время гонки (nginx alias, без авторизации, `no-store`). Новый JS-файл фетчит этот JSON и рендерит текст постов; markup новой вкладки в `admin.html` по образцу уже существующих вкладок (`switchTab`/`ADMIN_TAB_STORAGE_KEY`).

**Tech Stack:** Vanilla JS (без фреймворка, как весь остальной фронтенд проекта), Jinja2-шаблон, node:vm для юнит-тестов (в проекте нет выделенного JS-тест-фреймворка).

**Спека:** `docs/superpowers/specs/2026-08-19-krasmarafon-broadcast-top3-posts-design.md` — прочитать целиком перед началом, там все решения по объёму/формату/обработке ошибок, одобрено пользователем.

---

## Файловая структура

- **Create:** `static/js/krasmarafon-broadcast-posts.js` — вся логика: чистая функция форматирования поста + DOM-обвязка (fetch/populate/generate/copy). Один файл, т.к. фича маленькая и самодостаточная — не требует разделения на несколько модулей.
- **Modify:** `templates/krasmarafon/admin.html` — новая кнопка вкладки, новый `<div id="tab-broadcast">` с разметкой, новый `<script src>`.
- **Create:** `tests/js/test_krasmarafon_broadcast_posts.js` — node:vm юнит-тесты чистой функции `buildTop3Post()`.
- **Create:** `static/test-data/zhara_5km_top10_sample.json` — синтетический фикстур-JSON (реальная форма ответа `generate_top10_json()`), используется для живой ручной проверки в браузере (Task 4) и остаётся в репозитории как документирующий пример реальной формы данных.

---

### Task 1: Чистая функция форматирования поста + тесты

**Files:**
- Create: `static/js/krasmarafon-broadcast-posts.js`
- Test: `tests/js/test_krasmarafon_broadcast_posts.js`

- [ ] **Step 1: Написать файл с функцией `buildTop3Post()`**

Создать `static/js/krasmarafon-broadcast-posts.js`:

```javascript
// static/js/krasmarafon-broadcast-posts.js
// Генератор текстовых постов "Топ-3 мужчины"/"Топ-3 женщины" по контрольным
// точкам Жары (5 км/21.1 км) для вкладки "Трансляция" в /admin. Источник
// данных — уже существующие live-JSON файлы, которые generate_top10_json()
// (src/krasmarafon/services/live_top10_export.py) пишет во время гонки
// (см. docs/superpowers/specs/2026-08-18-zhara-live-top10-broadcast-json-design.md).
// Дизайн этой конкретной фичи (формат поста, markdown-конвенция **/__ как у
// Siberman) — docs/superpowers/specs/2026-08-19-krasmarafon-broadcast-top3-posts-design.md.

const BCP_JSON_URLS = {
    '5 км': '/live/zhara_5km_top10.json',
    '21.1 км': '/live/zhara_21km_top10.json',
};

const BCP_NO_DATA_MESSAGE = 'Нет данных — трансляция ещё не активна';

// Строит готовый к копированию текст поста для одной (checkpoint, sexKey).
// checkpoint — один объект из data.checkpoints (см. схему в спеке),
// sexKey — 'male' | 'female'. Чистая функция, без обращения к DOM — легко
// тестируется через node:vm без стабов document/fetch.
function buildTop3Post(checkpoint, sexKey) {
    const list = (sexKey === 'male' ? checkpoint.top10_male : checkpoint.top10_female) || [];
    const top3 = list.slice(0, 3);
    // Пустой топ-3 — короткое сообщение вместо всего поста (тот же приём,
    // что у Siberman: bcBuildStagePost() возвращает голую строку без
    // заголовка/подписи, когда никто ещё не дошёл до отметки).
    if (top3.length === 0) {
        return 'Нет данных для этой отметки — пока никто не финишировал.';
    }

    const sexLabel = sexKey === 'male' ? 'Мужчины' : 'Женщины';
    let titleSuffix;
    if (checkpoint.code === 'finish') {
        titleSuffix = 'Финиш';
    } else {
        // label — "КТ{i} ({N} км)" (live_top10_export.py), N km извлекаем
        // регэкспом, а не пересчитываем на клиенте заново.
        const m = /\(([\d.]+)\s*км\)/.exec(checkpoint.label || '');
        titleSuffix = `Отсечка ${m ? m[1] : '?'} км`;
    }
    const title = `**${sexLabel}. ${titleSuffix}**`;

    const entries = top3.map((entry, idx) => {
        // entry.time уже "ЧЧ:ММ:СС" — обрезаем "00:" в начале, часовую
        // часть оставляем как есть, если гонка реально идёт больше часа.
        let time = entry.time || '';
        if (time.startsWith('00:')) time = time.slice(3);
        const gapSuffix = (entry.gap_sex && entry.gap_sex !== 'Лидер') ? ` (${entry.gap_sex})` : '';
        const lines = [`${idx + 1}. ${entry.surname} ${entry.name}`, `⏱️${time}${gapSuffix}`];
        if (entry.pace) lines.push(`${entry.pace} мин/км`);
        return lines.join('\n');
    });

    const footer = '__👉 ссылка на лайв-результаты: https://analytics.krasmarafon.ru/results__';
    return `${title}\n\n${entries.join('\n\n')}\n\n${footer}`;
}
```

- [ ] **Step 2: Написать тесты**

Создать `tests/js/test_krasmarafon_broadcast_posts.js`:

```javascript
// Тесты для buildTop3Post() из static/js/krasmarafon-broadcast-posts.js —
// чистая функция, DOM не нужен. В проекте нет JS-тест-фреймворка —
// используется node:vm (тот же приём, что в остальных tests/js/*.js).
// Запуск: node tests/js/test_krasmarafon_broadcast_posts.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/krasmarafon-broadcast-posts.js'), 'utf-8');

// Минимальные стабы document/fetch — файл сам их не использует в этом
// Task (DOM-обвязка добавится в Task 2), но заранее готовим тот же
// sandbox-паттерн, что и в остальных tests/js/*.js.
const sandbox = {
    console,
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    document: {
        getElementById: () => null,
        createElement: () => ({}),
        addEventListener: () => {},
    },
    navigator: { clipboard: { writeText: () => Promise.resolve() } },
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(scriptJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

const CP_KT = {
    code: 'kt1', label: 'КТ1 (10.55 км)',
    top10_male: [
        { surname: 'Иванов', name: 'Пётр', sex: 'M', time: '00:45:00', pace: '4:30', gap_sex: 'Лидер' },
        { surname: 'Сидоров', name: 'Олег', sex: 'M', time: '00:50:30', pace: '5:03', gap_sex: '+05:30' },
    ],
    top10_female: [
        { surname: 'Викулова', name: 'Анна', sex: 'F', time: '00:15:00', pace: '3:00', gap_sex: 'Лидер' },
        { surname: 'Томкус', name: 'Полина', sex: 'F', time: '00:20:00', pace: '4:00', gap_sex: '+05:00' },
    ],
};

const CP_FINISH = {
    code: 'finish', label: 'Финиш',
    top10_male: [
        { surname: 'Иванов', name: 'Пётр', sex: 'M', time: '01:32:10', pace: '4:20', gap_sex: 'Лидер' },
    ],
    top10_female: [],
};

check('Заголовок КТ — "Отсечка N км" с числом из label', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'female');
    assert.ok(text.startsWith('**Женщины. Отсечка 10.55 км**'), text);
});

check('Заголовок Финиш — "Финиш" без "Отсечка"', () => {
    const text = sandbox.buildTop3Post(CP_FINISH, 'male');
    assert.ok(text.startsWith('**Мужчины. Финиш**'), text);
});

check('Время "00:15:00" обрезается до "15:00"', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'female');
    assert.ok(text.includes('⏱️15:00'), text);
});

check('Время с ненулевым часом остаётся "ЧЧ:ММ:СС"', () => {
    const text = sandbox.buildTop3Post(CP_FINISH, 'male');
    assert.ok(text.includes('⏱️01:32:10'), text);
});

check('Лидер — без отставания в скобках', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'female');
    assert.ok(text.includes('⏱️15:00\n'), text);
    assert.ok(!text.includes('⏱️15:00 ('), text);
});

check('Не-лидер — отставание в скобках сразу после времени', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'female');
    assert.ok(text.includes('⏱️20:00 (+05:00)'), text);
});

check('Темп выводится отдельной строкой', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'female');
    assert.ok(text.includes('3:00 мин/км'), text);
});

check('pace === null — строка темпа не выводится', () => {
    const cp = { code: 'kt1', label: 'КТ1 (5 км)', top10_male: [], top10_female: [
        { surname: 'Петрова', name: 'Мария', time: '00:20:00', pace: null, gap_sex: 'Лидер' },
    ] };
    const text = sandbox.buildTop3Post(cp, 'female');
    assert.ok(!text.includes('мин/км'), text);
    assert.ok(text.includes('⏱️20:00'), text);
});

check('2 записи вместо 3 — третье место не показывается', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'female');
    assert.ok(text.includes('2. Томкус Полина'), text);
    assert.ok(!text.includes('3.'), text);
});

check('0 записей — короткое сообщение вместо всего поста', () => {
    const text = sandbox.buildTop3Post(CP_FINISH, 'female');
    assert.strictEqual(text, 'Нет данных для этой отметки — пока никто не финишировал.');
});

check('Мужчины vs Женщины — правильный список и заголовок', () => {
    const textM = sandbox.buildTop3Post(CP_KT, 'male');
    const textF = sandbox.buildTop3Post(CP_KT, 'female');
    assert.ok(textM.includes('Мужчины') && textM.includes('Иванов Пётр'));
    assert.ok(textF.includes('Женщины') && textF.includes('Викулова Анна'));
});

check('Заголовок и ссылка в markdown-конвенции Siberman (**bold**/__italic__)', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'male');
    assert.ok(text.includes('**Мужчины. Отсечка 10.55 км**'));
    assert.ok(text.includes('__👉 ссылка на лайв-результаты: https://analytics.krasmarafon.ru/results__'));
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
```

- [ ] **Step 3: Запустить тесты, убедиться, что все проходят**

Run: `node tests/js/test_krasmarafon_broadcast_posts.js`
Expected: `ALL PASSED`, exit code 0. Если что-то падает — почитать `FAIL`-строку (есть текст поста, который не совпал с ожиданием) и поправить либо тест, либо функцию — на этом этапе логика ещё нигде не используется, безопасно итерировать.

- [ ] **Step 4: Commit**

```bash
git add static/js/krasmarafon-broadcast-posts.js tests/js/test_krasmarafon_broadcast_posts.js
git commit -m "feat(krasmarafon): buildTop3Post() — форматирование постов Топ-3 для трансляции Жары"
```

---

### Task 2: DOM-обвязка (fetch, заполнение отметок, генерация, копирование)

**Files:**
- Modify: `static/js/krasmarafon-broadcast-posts.js`

- [ ] **Step 1: Добавить функции обвязки в конец файла**

Дописать в `static/js/krasmarafon-broadcast-posts.js` (после `buildTop3Post`):

```javascript
// ---- DOM-обвязка ----
// Fetch происходит ДВАЖДЫ по дизайну (не кешируем JSON между шагами):
// (1) при смене дистанции — только чтобы заполнить список отметок
//     (структура отметок стабильна в рамках гонки, но перезапрашиваем
//     всё равно ради простоты — один путь кода, не два);
// (2) при каждом клике "Сгенерировать" — гарантирует, что пост строится
//     по самым свежим данным на момент публикации, а не по снапшоту с
//     момента выбора дистанции (тот же принцип, что у Siberman bcGenerate()
//     — там тоже fetch происходит заново на каждый клик "Сгенерировать").

async function bcpFetchDistanceData(distanceLabel) {
    const url = BCP_JSON_URLS[distanceLabel];
    const r = await fetch(url);
    if (!r.ok) throw new Error('not ok');
    return r.json();
}

function bcpShowError(show) {
    const errEl = document.getElementById('bcp-error');
    if (!errEl) return;
    errEl.textContent = BCP_NO_DATA_MESSAGE;
    errEl.style.display = show ? '' : 'none';
}

async function bcpOnDistanceChange() {
    const distSel = document.getElementById('bcp-distance');
    const cpSel = document.getElementById('bcp-checkpoint');
    cpSel.innerHTML = '<option value="">— отметка —</option>';
    document.getElementById('bcp-output-male').value = '';
    document.getElementById('bcp-output-female').value = '';
    bcpShowError(false);
    try {
        const data = await bcpFetchDistanceData(distSel.value);
        (data.checkpoints || []).forEach(cp => {
            const opt = document.createElement('option');
            opt.value = cp.code;
            opt.textContent = cp.label;
            cpSel.appendChild(opt);
        });
    } catch (e) {
        bcpShowError(true);
    }
}

async function bcpGenerate(sexKey) {
    const distSel = document.getElementById('bcp-distance');
    const cpSel = document.getElementById('bcp-checkpoint');
    const outputId = sexKey === 'male' ? 'bcp-output-male' : 'bcp-output-female';
    const ta = document.getElementById(outputId);
    if (!cpSel.value) return;
    bcpShowError(false);
    try {
        const data = await bcpFetchDistanceData(distSel.value);
        const checkpoint = (data.checkpoints || []).find(cp => cp.code === cpSel.value);
        if (!checkpoint) throw new Error('checkpoint not found');
        ta.value = buildTop3Post(checkpoint, sexKey);
    } catch (e) {
        bcpShowError(true);
    }
}

function bcpCopy(textareaId) {
    const ta = document.getElementById(textareaId);
    navigator.clipboard.writeText(ta.value).catch(() => {
        ta.select();
        document.execCommand('copy');
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const distSel = document.getElementById('bcp-distance');
    if (!distSel) return; // разметки вкладки нет на этой странице — не наш случай
    distSel.addEventListener('change', bcpOnDistanceChange);
    document.getElementById('bcp-generate-male').addEventListener('click', () => bcpGenerate('male'));
    document.getElementById('bcp-generate-female').addEventListener('click', () => bcpGenerate('female'));
    document.getElementById('bcp-copy-male').addEventListener('click', () => bcpCopy('bcp-output-male'));
    document.getElementById('bcp-copy-female').addEventListener('click', () => bcpCopy('bcp-output-female'));
    bcpOnDistanceChange(); // заполнить отметки для дистанции, выбранной по умолчанию
});
```

- [ ] **Step 2: Добавить тест на заполнение списка отметок и генерацию через DOM-стабы**

Дописать в `tests/js/test_krasmarafon_broadcast_posts.js` перед финальным `console.log(failures ...)`:

```javascript
// ---- DOM-обвязка: минимальные стабы (тот же паттерн makeElement/domStub,
// что в tests/js/test_analytics_start_list_gender_pills.js) ----
function makeElement(tag) {
    const children = [];
    return {
        tagName: (tag || 'DIV').toUpperCase(),
        value: '',
        textContent: '',
        style: {},
        _children: children,
        set innerHTML(v) { children.length = 0; },
        get innerHTML() { return ''; },
        appendChild(child) { children.push(child); return child; },
        addEventListener() {},
        get options() { return children.filter(c => c.tagName === 'OPTION'); },
        select() {},
    };
}
const elementsById2 = {};
function domStub2(id) {
    if (!elementsById2[id]) elementsById2[id] = makeElement('DIV');
    return elementsById2[id];
}

const BCP_TEST_URL_5KM = '/live/zhara_5km_top10.json';
const domSandbox = {
    console,
    fetch: (url) => {
        if (url === BCP_TEST_URL_5KM) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ checkpoints: [CP_KT, CP_FINISH] }) });
        }
        return Promise.resolve({ ok: false });
    },
    document: {
        getElementById: domStub2,
        createElement: (tag) => makeElement(tag),
        addEventListener: () => {},
    },
    navigator: { clipboard: { writeText: () => Promise.resolve() } },
    window: {},
};
domSandbox.window = domSandbox;
vm.createContext(domSandbox);
vm.runInContext(scriptJs, domSandbox);

(async () => {
    domStub2('bcp-distance').value = '5 км';
    await domSandbox.bcpOnDistanceChange();

    check('bcpOnDistanceChange() заполняет select отметок из checkpoints[]', () => {
        const opts = domStub2('bcp-checkpoint').options;
        // 1-я опция — плейсхолдер "— отметка —", затем kt1 и finish
        assert.strictEqual(opts.length, 3, JSON.stringify(opts.map(o => o.textContent)));
        assert.strictEqual(opts[1].value, 'kt1');
        assert.strictEqual(opts[2].value, 'finish');
    });

    domStub2('bcp-checkpoint').value = 'kt1';
    await domSandbox.bcpGenerate('female');

    check('bcpGenerate("female") заполняет textarea готовым текстом', () => {
        const text = domStub2('bcp-output-female').value;
        assert.ok(text.startsWith('**Женщины. Отсечка 10.55 км**'), text);
    });

    console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
    process.exit(failures === 0 ? 0 : 1);
})();
```

Удалить старый финальный `console.log(failures === 0 ? '\nALL PASSED' : ...); process.exit(...)` (тот, что был в конце файла из Task 1, Step 2) — теперь итог печатает и завершает процесс новый асинхронный блок в конце (иначе процесс завершится раньше, чем отработают `await`).

- [ ] **Step 3: Запустить тесты**

Run: `node tests/js/test_krasmarafon_broadcast_posts.js`
Expected: `ALL PASSED`, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add static/js/krasmarafon-broadcast-posts.js tests/js/test_krasmarafon_broadcast_posts.js
git commit -m "feat(krasmarafon): DOM-обвязка генератора постов — fetch/отметки/генерация/копирование"
```

---

### Task 3: Вкладка «Трансляция» в `/admin`

**Files:**
- Modify: `templates/krasmarafon/admin.html`

- [ ] **Step 1: Добавить кнопку вкладки**

Найти в `templates/krasmarafon/admin.html` (около строки 47):

```html
            <button class="admin-tab" onclick="switchTab('analytics', this)">Аналитика</button>
```

Добавить сразу после:

```html
            <button class="admin-tab" onclick="switchTab('broadcast', this)">Трансляция</button>
```

- [ ] **Step 2: Добавить разметку вкладки**

В `templates/krasmarafon/admin.html` найти этот фрагмент (конец вкладки `tab-analytics`,
конец общего контейнера всех вкладок):

```html
            <div id="analytics-iframe-wrap">
                <div class="admin-loading">Загрузка дашборда...</div>
            </div>
        </div>
    </div>
```

Заменить его целиком на (тот же исходный фрагмент, но с новым блоком вкладки,
вставленным между закрывающим `</div>` вкладки `tab-analytics` и закрывающим `</div>`
общего контейнера вкладок):

```html
            <div id="analytics-iframe-wrap">
                <div class="admin-loading">Загрузка дашборда...</div>
            </div>
        </div>
        <!-- ================================================================ -->
        <!-- ВКЛАДКА: ТРАНСЛЯЦИЯ (посты Топ-3 муж/жен по отметкам, Жара)     -->
        <!-- ================================================================ -->
        <div id="tab-broadcast" class="admin-tab-content" style="display:none">
            <div class="admin-section-note">
                Готовые к копированию посты «Топ-3» по отметкам Жары (5 км / 21.1 км) —
                для соцсетей/мессенджера. Источник — тот же live-JSON, что и у режиссёра
                трансляции; данные появляются только когда идёт гонка и загрузчик
                результатов запущен с флагом <code>--broadcast-json</code>.
            </div>

            <div class="admin-leads-toolbar">
                <div class="admin-leads-filters">
                    <select id="bcp-distance" class="admin-select">
                        <option value="5 км">5 км</option>
                        <option value="21.1 км">21.1 км</option>
                    </select>
                    <select id="bcp-checkpoint" class="admin-select">
                        <option value="">— отметка —</option>
                    </select>
                </div>
            </div>

            <div id="bcp-error" class="admin-error" style="display:none"></div>

            <div class="admin-leads-toolbar">
                <button class="km-btn km-btn--primary" id="bcp-generate-male">Сгенерировать (Мужчины)</button>
                <button class="km-btn km-btn--primary" id="bcp-generate-female">Сгенерировать (Женщины)</button>
            </div>

            <div style="display:flex; gap:16px; flex-wrap:wrap; margin-top:12px">
                <div style="flex:1; min-width:280px">
                    <div style="font-weight:600; margin-bottom:4px">Мужчины</div>
                    <textarea id="bcp-output-male" class="admin-yaml-editor" readonly rows="12"></textarea>
                    <button class="km-btn km-btn--secondary" id="bcp-copy-male" style="margin-top:8px">Копировать</button>
                </div>
                <div style="flex:1; min-width:280px">
                    <div style="font-weight:600; margin-bottom:4px">Женщины</div>
                    <textarea id="bcp-output-female" class="admin-yaml-editor" readonly rows="12"></textarea>
                    <button class="km-btn km-btn--secondary" id="bcp-copy-female" style="margin-top:8px">Копировать</button>
                </div>
            </div>
        </div>
    </div>
```

- [ ] **Step 3: Подключить новый JS-файл**

В конце `templates/krasmarafon/admin.html` найти:

```html
    loadHistoryToggle();
    </script>
</body>
</html>
```

Заменить на:

```html
    loadHistoryToggle();
    </script>
    <script src="/static/js/krasmarafon-broadcast-posts.js"></script>
</body>
</html>
```

(без `?v={{ v }}` — маршрут `/admin` в `src/krasmarafon/routers/pages.py` сейчас не передаёт переменную `v` в шаблон вообще, и ни один другой `<script src>` в этом файле её не использует — сохраняем консистентность с тем, что уже есть в этом конкретном файле, не вводим версионирование только для одного нового файла).

- [ ] **Step 4: Проверить, что страница рендерится без ошибок**

Запустить локальный dev-сервер:

```bash
conda run -n base python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Открыть `http://localhost:8000/admin` в браузере (или через `agent-browser open http://localhost:8000/admin`), убедиться, что вкладка «Трансляция» появилась в списке вкладок, кликнуть — контент вкладки показывается, в консоли браузера нет JS-ошибок (кроме ожидаемого сообщения "Нет данных — трансляция ещё не активна" в `#bcp-error`, т.к. `/live/zhara_5km_top10.json` ещё не существует на локальном сервере).

- [ ] **Step 5: Commit**

```bash
git add templates/krasmarafon/admin.html
git commit -m "feat(krasmarafon): вкладка «Трансляция» в /admin — разметка + подключение JS"
```

---

### Task 4: Синтетический фикстур + живая проверка в браузере

**Files:**
- Create: `static/test-data/zhara_5km_top10_sample.json`

- [ ] **Step 1: Создать синтетический JSON-фикстур**

Создать `static/test-data/zhara_5km_top10_sample.json` — реальная форма ответа `generate_top10_json()` (см. `src/krasmarafon/services/live_top10_export.py` и `docs/superpowers/specs/2026-08-18-zhara-live-top10-broadcast-json-design.md`), с одной промежуточной КТ и финишем, по 3+ записи в каждом списке пола (чтобы явно проверить, что в тексте поста НЕ появляется лишнее 4-е место):

```json
{
  "event_name": "Жара",
  "event_year": 2026,
  "distance": "5 км",
  "generated_at": "2026-08-19T10:00:00+03:00",
  "checkpoints": [
    {
      "code": "kt1",
      "label": "КТ1 (2.5 км)",
      "top10_absolute": [],
      "top10_male": [
        {"start_number": 101, "surname": "Иванов", "name": "Пётр", "sex": "M", "city": "Красноярск",
         "rank_absolute": 1, "rank_sex": 1, "time": "00:10:15", "pace": "4:06",
         "gap_absolute": "Лидер", "gap_sex": "Лидер", "photo_url": "https://analytics.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"},
        {"start_number": 102, "surname": "Сидоров", "name": "Олег", "sex": "M", "city": "Красноярск",
         "rank_absolute": 2, "rank_sex": 2, "time": "00:11:00", "pace": "4:24",
         "gap_absolute": "+00:45", "gap_sex": "+00:45", "photo_url": "https://analytics.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"},
        {"start_number": 103, "surname": "Кузнецов", "name": "Игорь", "sex": "M", "city": "Красноярск",
         "rank_absolute": 3, "rank_sex": 3, "time": "00:11:30", "pace": "4:36",
         "gap_absolute": "+01:15", "gap_sex": "+01:15", "photo_url": "https://analytics.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"},
        {"start_number": 104, "surname": "Морозов", "name": "Данил", "sex": "M", "city": "Красноярск",
         "rank_absolute": 4, "rank_sex": 4, "time": "00:12:00", "pace": "4:48",
         "gap_absolute": "+01:45", "gap_sex": "+01:45", "photo_url": "https://analytics.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"}
      ],
      "top10_female": [
        {"start_number": 201, "surname": "Викулова", "name": "Анна", "sex": "F", "city": "Новосибирск",
         "rank_absolute": 5, "rank_sex": 1, "time": "00:15:00", "pace": "6:00",
         "gap_absolute": "+04:45", "gap_sex": "Лидер", "photo_url": "https://analytics.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"},
        {"start_number": 202, "surname": "Томкус", "name": "Полина", "sex": "F", "city": "Красноярск",
         "rank_absolute": 6, "rank_sex": 2, "time": "00:20:00", "pace": "8:00",
         "gap_absolute": "+09:45", "gap_sex": "+05:00", "photo_url": "https://analytics.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"}
      ]
    },
    {
      "code": "finish",
      "label": "Финиш",
      "top10_absolute": [],
      "top10_male": [
        {"start_number": 101, "surname": "Иванов", "name": "Пётр", "sex": "M", "city": "Красноярск",
         "rank_absolute": 1, "rank_sex": 1, "time": "00:22:10", "pace": "4:26",
         "gap_absolute": "Лидер", "gap_sex": "Лидер", "photo_url": "https://analytics.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"}
      ],
      "top10_female": []
    }
  ]
}
```

- [ ] **Step 2: Временно переключить URL 5 км на фикстур и открыть вкладку**

Это ручной шаг для однократной визуальной проверки — правки в этом шаге НЕ коммитятся.

Запустить (если ещё не запущен) локальный dev-сервер:

```bash
conda run -n base python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Через `agent-browser`:

```bash
agent-browser open http://localhost:8000/admin
agent-browser eval "BCP_JSON_URLS['5 км'] = '/static/test-data/zhara_5km_top10_sample.json';"
```

(если `agent-browser eval` в установленной версии недоступен — открыть DevTools Console в обычном браузере и выполнить ту же строку вручную; это временная подмена в памяти страницы, не правка файла).

- [ ] **Step 3: Пройти сценарий глазами**

1. Кликнуть на вкладку «Трансляция»
2. Дистанция уже «5 км» по умолчанию — список отметок должен заполниться значениями «КТ1 (2.5 км)» и «Финиш» (если не заполнился — переключить select на «21.1 км» и обратно на «5 км», чтобы триггернуть `change`)
3. Выбрать отметку «КТ1 (2.5 км)», нажать «Сгенерировать (Мужчины)» — в левой textarea должен появиться текст, начинающийся с `**Мужчины. Отсечка 2.5 км**`. Фикстура намеренно содержит 4 мужчин (Иванов/Сидоров/Кузнецов/Морозов) — в тексте поста должны быть только первые 3 (Иванов/Сидоров/Кузнецов), Морозов НЕ должен появиться — это и есть проверка обрезки `top10_male.slice(0, 3)` на реальном (не тестовом через node:vm) fetch-цикле
4. Нажать «Сгенерировать (Женщины)» — правая textarea: `**Женщины. Отсечка 2.5 км**`, 2 позиции (Викулова без отставания, Томкус с `(+05:00)`)
5. Выбрать отметку «Финиш», сгенерировать оба поста — мужской: 1 позиция без отставания, женский: `Нет данных для этой отметки — пока никто не финишировал.`
6. Нажать «Копировать» у любого поста — убедиться, что не появляется JS-ошибка в консоли (сам факт копирования в буфер в headless-браузере может не проверяться напрямую — важно отсутствие исключения)

- [ ] **Step 4: Commit фикстура (без временной правки URL — она не в файле)**

```bash
git add static/test-data/zhara_5km_top10_sample.json
git commit -m "test(krasmarafon): синтетический фикстур live-top10 JSON для ручной проверки постов"
```

---

## Финальная проверка

- [ ] `node tests/js/test_krasmarafon_broadcast_posts.js` — `ALL PASSED`
- [ ] `conda run -n base python -m pytest tests/unit/ -v` — полный прогон Python-тестов не должен сломаться (эта фича не трогает Python-код вообще, ожидается тот же результат, что и до начала работы)
- [ ] Живая проверка в браузере (Task 4) пройдена глазами
- [ ] Все 4 задачи закоммичены отдельными коммитами
