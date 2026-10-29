# «Качество данных»: экран дел — план реализации (этап 3 из 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вкладка /admin → «Качество данных» становится экраном «очередь дел + дело с вопросами» (спецификация `docs/superpowers/specs/2026-10-28-data-quality-cases-design.md` → «Этап 3») поверх API этапа 2; старый плоский список удаляется.

**Architecture:** Новый `static/js/admin-dq-cases.js` (чистые функции построения HTML/запросов + обработчики) вместо UI в `static/js/admin-data-quality.js`; разметка вкладки в `templates/krasmarafon/admin.html`; стили в `static/css/admin.css`. Сервер: кеш очереди 10 мин (на проде 3 процесса — минутный кеш почти всегда холодный), удалить старый `GET /api/admin/data-quality`.

**Tech Stack:** vanilla JS (как остальная админка), FastAPI, pytest, node (tests/js), Playwright (браузерная проверка).

---

## Общее

- Тесты Python: `C:/Users/podbo/miniconda3/python.exe -m pytest <пути> -q -p no:warnings`; JS: `node tests/js/<файл>.js`. Не запускать два прогона DB-тестов одновременно.
- JS правится инструментами Edit/Write, **не** через Python-строки (перевод строки `'\n'` ломал JS — урок 2026-10-28); после правки: `node --check static/js/admin-dq-cases.js`.
- Всё, что пришло с сервера, в HTML — только через `dqEsc()`.
- Каждый коммит — со строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Контракт API (этап 2, фактический)

- `GET /api/admin/data-quality/cases?status=open|postponed&event_id=` → `{cases: [{key, title, cards (число), questions_left, events: [строка]}]}`
- `GET /api/admin/data-quality/cases/{key}` → дело `{key, title, cards: [{id, surname, name, birthday, rows: [{table, id, year, event, start_number, category, status, birthday, problem}]}], questions: [{id, code, stage, text, hint, result_id, lead_id, live, state: current|locked|postponed, answers: [{id, label, recommended, inputs: [{name, label, value, type: text|date|select, options?}]}]}], stage_titles: {1,2,3}}`; 404 — дело закрыто.
  `options`: категории — `[{label, sex}]`, пол — `["Мужчина","Женщина"]`, дистанции — строки, `row_id` — `[{value, label}]`.
- `POST /api/admin/data-quality/cases/{key}/answer` `{question_id, answer_id, inputs: {имя: строка}, extra_cards: [id]}` → `{action_ids, case (null — закрыто), conflict?: {message, merge_with, surname, name, birthday}}`; 400 `detail` — ошибка действия; 409 — дело изменилось.
- `POST /api/admin/data-quality/cases/{key}/postpone` `{reason}` → `{ok, action_ids}`.
- `GET /api/admin/data-quality/person/{client_id}` → дело (без находок — ключ `p<id>`, `questions: []`).
- Ручные действия (есть): `GET /cards?q=` → `{cards: [{id, surname, name, birthday, events}]}`; `POST /move {table, row_id, to_client_id | new_card, key}`; `POST /edit {table, id, fields, key}`; `POST /merge {client_ids, surname, name, birthday, key}`; `GET /actions?limit=` → `{actions: [{id, text, done_at, done_by, undone, can_undo, why_not}]}`; `POST /undo {action_id}`; `POST /apply-auto`.

## Файлы

| Файл | Что |
|---|---|
| `src/analytics/dq_cases.py` | `QUEUE_TTL = 600` |
| `src/krasmarafon/routers/data_quality.py` | удалить `GET /api/admin/data-quality` (плоский список) |
| `templates/krasmarafon/admin.html` (вкладка `tab-data-quality`, подключение скрипта) | новая разметка |
| `static/js/admin-dq-cases.js` (новый) | экран |
| `static/js/admin-data-quality.js` | удалить (функции журнала переносятся в новый файл) |
| `static/css/admin.css` | стили `.dqc-*` |
| `tests/js/test_admin_dq_cases.js` (новый) | чистые функции |
| `tests/integration/test_admin_data_quality.py` | убрать тесты удалённого эндпоинта |

---

### Task 1: Сервер — кеш очереди 10 минут, удалить плоский список

- [ ] **Step 1:** в `src/analytics/dq_cases.py` `QUEUE_TTL = 60` → `QUEUE_TTL = 600`, комментарий: `# с: полный прогон очереди (~8 с на проде); 3 процесса сервера — свой процесс сбрасывает кеш после действия, в других дело-«призрак» откроется как «дело закрыто» (get_case проверяет заново)`.
- [ ] **Step 2:** в `src/krasmarafon/routers/data_quality.py` удалить `list_findings` (`GET /api/admin/data-quality`) и ставшую ненужной `_list`/`ORDER`, если больше нигде не используются (grep). В `tests/integration/test_admin_data_quality.py` удалить тест `test_list_sorted_by_severity_and_connection_closed` и тест 503 переписать на другой эндпоинт, например `GET /api/admin/data-quality/actions`.
- [ ] **Step 3:** unit-тест: `assert dq_cases.QUEUE_TTL == 600` не нужен; в `tests/unit/test_dq_cases.py` тест кеша (`test_queue_is_cached_until_an_action`) должен остаться зелёным. Прогон `tests/unit/ tests/integration/`.
- [ ] **Step 4:** Commit `feat(data-quality): кеш очереди дел 10 минут; плоский список находок удалён`.

---

### Task 2: Разметка вкладки и стили

**Files:** `templates/krasmarafon/admin.html:160-190`, подключение скрипта (строка с `admin-data-quality.js`), `static/css/admin.css`.

- [ ] **Step 1:** Заменить содержимое `<div id="tab-data-quality" …>` целиком на:

```html
            <div class="admin-section-note">
                Дела о людях: всё, что не сходится в карточках, заявках и результатах одного человека и его тёзок.
                Откройте дело и отвечайте на вопросы сверху вниз — ответ сам выполнит нужные правки (их можно отменить).
                «Не знаю» откладывает дело во вкладку «Отложено». Очевидное каждую ночь применяется автоматически.
            </div>
            <div class="dqc-toolbar">
                <div class="dqc-search">
                    <input id="dqc-q" class="admin-select" placeholder="Найти человека: фамилия имя" oninput="dqcSearch()" autocomplete="off">
                    <div id="dqc-search-list" class="dqc-search-list" hidden></div>
                </div>
                <select id="dqc-event" class="admin-select" onchange="dqcLoadQueue()"><option value="">Все забеги</option></select>
                <button class="km-btn km-btn--secondary" onclick="dqcApplyAuto(this)">Применить очевидное</button>
            </div>
            <div class="dqc-tabs" role="tablist">
                <button class="dqc-tab dqc-tab--on" data-tab="open" onclick="dqcTab('open')">Нужно решить <span id="dqc-n-open"></span></button>
                <button class="dqc-tab" data-tab="postponed" onclick="dqcTab('postponed')">Отложено <span id="dqc-n-postponed"></span></button>
                <button class="dqc-tab" data-tab="journal" onclick="dqcTab('journal')">Журнал</button>
            </div>
            <div class="dqc-status" id="dqc-status"></div>
            <div class="dqc-layout" id="dqc-layout">
                <div class="dqc-queue" id="dqc-queue"><div class="admin-loading">Собираю очередь…</div></div>
                <div class="dqc-case" id="dqc-case"><div class="admin-loading">Выберите дело слева</div></div>
            </div>
            <div class="dqc-journal" id="dqc-journal" hidden></div>
```

Подключение `<script src="/static/js/admin-data-quality.js?v={{ v }}"></script>` заменить на `<script src="/static/js/admin-dq-cases.js?v={{ v }}"></script>`; в обработчике вкладок `if (name === 'data-quality') loadDataQualityTab();` → `if (name === 'data-quality') dqcInit();`.

- [ ] **Step 2:** Стили — добавить в `static/css/admin.css` после блока `.dq-*` (классы `.dq-*` оставить: ими пользуются другие вкладки — `dq-status`, `dq-muted`, `dq-actions`):

```css
/* ------- Качество данных: дела ------- */
.dqc-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 12px 0; }
.dqc-search { position: relative; flex: 1 1 280px; max-width: 420px; }
.dqc-search input { width: 100%; }
.dqc-search-list { position: absolute; z-index: 20; top: calc(100% + 4px); left: 0; right: 0; max-height: 320px; overflow-y: auto;
    background: var(--km-bg-card); border: 1px solid var(--km-border-light); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,.12); }
.dqc-search-item { display: block; width: 100%; text-align: left; padding: 8px 10px; border: 0; background: none; cursor: pointer; }
.dqc-search-item:hover { background: var(--km-bg, #fafafa); }
.dqc-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--km-border-light); margin-bottom: 10px; }
.dqc-tab { border: 0; background: none; padding: 8px 12px; cursor: pointer; color: var(--km-text-secondary); border-bottom: 2px solid transparent; }
.dqc-tab--on { color: inherit; font-weight: 600; border-bottom-color: #c0392b; }
.dqc-status { min-height: 1.2em; font-size: 0.9rem; color: var(--km-text-secondary); }
.dqc-layout { display: grid; grid-template-columns: 280px 1fr; gap: 14px; align-items: start; }
.dqc-queue { border-right: 1px solid var(--km-border-light); padding-right: 10px; max-height: 75vh; overflow-y: auto; }
.dqc-qitem { display: block; width: 100%; text-align: left; border: 0; background: none; padding: 8px; border-radius: 8px; cursor: pointer; }
.dqc-qitem:hover { background: var(--km-bg, #fafafa); }
.dqc-qitem--on { background: #eef3fd; }
.dqc-qitem small { display: block; color: var(--km-text-secondary); }
.dqc-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.dqc-back { display: none; }
.dqc-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 8px; margin: 10px 0; }
.dqc-card { border: 1px solid var(--km-border-light); border-radius: 8px; padding: 8px 10px; min-width: 0; font-size: 0.9rem; }
.dqc-card-title { font-weight: 600; display: flex; justify-content: space-between; gap: 6px; }
.dqc-row { display: flex; gap: 6px; padding: 2px 0; overflow-wrap: anywhere; }
.dqc-row--problem { background: #fde2e2; border-radius: 4px; }
.dqc-row small { color: var(--km-text-secondary); }
.dqc-done { color: #155724; font-size: 0.9rem; margin: 4px 0; }
.dqc-q { border: 1px solid var(--km-border-light); border-radius: 8px; padding: 10px; margin: 8px 0; }
.dqc-q--current { border-color: #2a6fd6; }
.dqc-q--locked { color: var(--km-text-secondary); }
.dqc-q-text { font-weight: 600; margin-bottom: 4px; overflow-wrap: anywhere; }
.dqc-hint { font-size: 0.85rem; color: var(--km-text-secondary); margin-bottom: 6px; }
.dqc-answer { display: block; padding: 4px 0; }
.dqc-answer-inputs { display: flex; gap: 6px; flex-wrap: wrap; margin: 4px 0 4px 22px; }
.dqc-answer-inputs label { display: flex; flex-direction: column; font-size: 0.8rem; color: var(--km-text-secondary); }
.dqc-answer-inputs .admin-select { min-width: 140px; max-width: 100%; }
.dqc-star { color: #2a9d4b; font-size: 0.85rem; }
.dqc-conflict { margin-top: 8px; padding: 8px; border-radius: 8px; background: #fff3cd; }
.dqc-menu { position: relative; }
.dqc-menu > summary { list-style: none; cursor: pointer; padding: 0 4px; }
.dqc-menu > summary::-webkit-details-marker { display: none; }
.dqc-menu-body { position: absolute; right: 0; z-index: 15; min-width: 260px; padding: 8px; background: var(--km-bg-card);
    border: 1px solid var(--km-border-light); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,.12); }
@media (max-width: 899px) {
    .dqc-layout { grid-template-columns: 1fr; }
    .dqc-layout--case .dqc-queue { display: none; }
    .dqc-layout:not(.dqc-layout--case) .dqc-case { display: none; }
    .dqc-queue { border-right: 0; padding-right: 0; max-height: none; }
    .dqc-back { display: inline-block; }
    .dqc-cards { grid-template-columns: 1fr; }
}
```

- [ ] **Step 3:** Commit (после Task 3, когда скрипт существует — иначе вкладка ломается). Шаги Task 2 и 3 коммитятся вместе.

---

### Task 3: `static/js/admin-dq-cases.js` — чистые функции (с тестами) и экран

**Files:** Create `static/js/admin-dq-cases.js`, `tests/js/test_admin_dq_cases.js`; Delete `static/js/admin-data-quality.js`.

- [ ] **Step 1: Падающий JS-тест** `tests/js/test_admin_dq_cases.js` (по образцу `tests/js/test_analytics_results_time_tiebreak.js` — загрузка скрипта в `vm` с заглушками `document`/`window`/`fetch`; посмотри, как сделано там):

```js
// Чистые функции экрана дел «Качества данных» (static/js/admin-dq-cases.js)
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const src = fs.readFileSync(path.join(__dirname, '../../static/js/admin-dq-cases.js'), 'utf-8');
const ctx = { console, document: { addEventListener() {}, getElementById() { return null; } }, window: {},
              localStorage: { getItem() { return null; }, setItem() {} }, setTimeout, clearTimeout };
vm.createContext(ctx); vm.runInContext(src, ctx);
const T = ctx.dqcTest;

// экранирование
assert.strictEqual(T.esc('<b a="1">&\''), '&lt;b a=&quot;1&quot;&gt;&amp;&#39;');

// категории по полу: свой пол и «любой» (sex = '')
const cats = [{label: 'Ж12-13', sex: 'Женщина'}, {label: 'М12-13', sex: 'Мужчина'}, {label: 'Абсолют', sex: ''}];
assert.deepStrictEqual(T.categoriesFor(cats, 'Мужчина'), ['М12-13', 'Абсолют']);

// тело ответа: inputs выбранного ответа, только непустые; extra_cards
const q = {id: 'R-CAT:r5:1', answers: [{id: 'sex', inputs: [{name: 'sex'}, {name: 'category'}]}, {id: 'keep', inputs: []}]};
assert.deepStrictEqual(T.answerBody(q, 'sex', {sex: 'Женщина', category: 'Ж12-13', birthday: ''}, [7]),
    {question_id: 'R-CAT:r5:1', answer_id: 'sex', inputs: {sex: 'Женщина', category: 'Ж12-13'}, extra_cards: [7]});

// ответ по умолчанию — рекомендованный, иначе первый
assert.strictEqual(T.defaultAnswer({answers: [{id: 'a'}, {id: 'b', recommended: true}]}), 'b');
assert.strictEqual(T.defaultAnswer({answers: [{id: 'a'}, {id: 'b'}]}), 'a');

// разметка вопроса: нет кода находки, есть радиокнопки, закрытый вопрос без кнопки «Применить»
const html = T.questionHtml({id: 'R-FOREIGN:r1:1-2', code: 'R-FOREIGN', stage: 1, state: 'current', text: 'Чей <это> результат?',
    hint: '', answers: [{id: 'to:2', label: 'Пцарев Саша', recommended: true, inputs: []}, {id: 'postpone', label: 'Не знаю', inputs: []}]}, 0);
assert.ok(html.includes('Чей &lt;это&gt; результат?') && !html.includes('R-FOREIGN') && html.includes('type="radio"'));
assert.ok(!T.questionHtml({id: 'x', code: 'R-CAT', stage: 3, state: 'locked', text: 't', hint: '', answers: []}, 1).includes('Применить'));

// строки карточки: проблемная подсвечена
const card = T.cardHtml({id: 1, surname: 'Пцарев', name: 'Александр', birthday: '1980-03-09',
    rows: [{table: 'results', id: 9, year: 2016, event: 'Детский забег 1.0 2016', start_number: 1012, category: 'М', status: 'Finished', problem: true}]});
assert.ok(card.includes('dqc-row--problem') && card.includes('№1012'));

console.log('ALL PASSED');
```

- [ ] **Step 2:** `node tests/js/test_admin_dq_cases.js` — падает (файла нет).

- [ ] **Step 3: Создать `static/js/admin-dq-cases.js`.** Структура (реализовать полностью; ниже — обязательные функции и поведение):

```js
// static/js/admin-dq-cases.js
// Вкладка /admin → «Качество данных»: очередь дел о людях + дело с вопросами
// (спецификация docs/superpowers/specs/2026-10-28-data-quality-cases-design.md, API — src/krasmarafon/routers/data_quality.py).
// Компьютер — две панели, телефон (< 900 px) — очередь → дело («← К списку»).

const DQC = { tab: 'open', cases: [], key: null, caseData: null, done: {}, extra: [], searchTimer: null };

function dqEsc(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

async function dqcRequest(url, body) { /* как dqRequest в старом файле: GET без тела, POST JSON; ошибка → Error с detail и .status */ }

function categoriesFor(options, sex) { return options.filter(o => !o.sex || o.sex === sex).map(o => o.label); }
function defaultAnswer(q) { return (q.answers.find(a => a.recommended) || q.answers[0] || {}).id; }
function answerBody(q, answerId, values, extraCards) {
    const a = q.answers.find(x => x.id === answerId) || { inputs: [] };
    const inputs = {};
    a.inputs.forEach(i => { if (values[i.name]) inputs[i.name] = values[i.name]; });
    return { question_id: q.id, answer_id: answerId, inputs, extra_cards: extraCards || [] };
}
function inputHtml(qi, ai, inp, sexValue) { /* text/date — <input>, select: options — строки или {value,label} или категории {label,sex}
    (категории фильтруются по полу: sexValue — значение поля «Пол» этого же ответа или пол строки); name=`dqc-${qi}-${ai}-${inp.name}` */ }
function questionHtml(q, qi) { /* текст, подсказка, «живой» забег — подсказка жирным; state:
    current — радиокнопки по ответам (★ «рекомендуем» у recommended; checked = defaultAnswer), поля ввода под выбранным ответом
      (поля видны только у выбранного ответа — переключение по change), кнопка «Применить» (onclick dqcApply(qi)), место для conflict;
    locked — серым «Откроется после: <stage_titles[предыдущая ступень]>», без кнопок;
    postponed — текст + «отложено» и те же ответы (можно решить из «Отложено») */ }
function cardHtml(c) { /* «#id» НЕ показывать; заголовок «Фамилия Имя · ДР», меню «⋯» (dqcMenu); строки: «год · событие · №номер · категория · статус»,
    заявка помечена «заявка», problem → .dqc-row--problem; у каждой строки кнопка «⋯» (перенести строку) */ }
function caseHtml(c) { /* «← К списку» (dqcBack), заголовок, «Отложить дело» (поле причины, по умолчанию «не знаю ДР»), «Следующее дело →»;
    карточки; решённые в этой сессии (DQC.done[key]) — строками «✓ <текст ответа> · Отменить» (dqcUndo(actionId));
    вопросы по ступеням; пустой список вопросов — «Вопросов нет» (дело из поиска без находок) */ }

window.dqcTest = { esc: dqEsc, categoriesFor, answerBody, defaultAnswer, questionHtml, cardHtml };
```

Обработчики (глобальные функции, вызываются из разметки):
- `dqcInit()` — один раз заполняет фильтр забегов (из `events` дел очереди, уникальные, по алфавиту), грузит очередь (`dqcLoadQueue`), счётчики «Нужно решить · N» / «Отложено · N» (два запроса `cases?status=`). Пока грузится — «Собираю очередь… (до 10 секунд)».
- `dqcLoadQueue()` — `GET cases?status=<tab>&event_id=<фильтр>` → список `.dqc-qitem` (ФИО, «карточек N · вопросов N», события мелко); клик → `dqcOpen(key)`.
- `dqcTab(name)` — переключение вкладок; «Журнал» скрывает `#dqc-layout` и показывает `#dqc-journal` (список `GET actions?limit=50`: текст, кто/когда, «Отменить» если `can_undo`, иначе причина `why_not`; отменённые — зачёркнуты).
- `dqcOpen(key, extraCards=[])` — `GET cases/{key}`; 404 → «Дело уже закрыто — обновляю очередь» + `dqcLoadQueue()`; на телефоне — класс `.dqc-layout--case`.
- `dqcApply(qi)` — тело `answerBody(...)` (значения полей собрать из DOM выбранного ответа) → `POST cases/{key}/answer`:
  - `conflict` → под вопросом жёлтый блок: текст `conflict.message` + кнопка «Склеить» → повторный ответ `merge_with:<conflict.merge_with>` с inputs `{surname, name, birthday}` из conflict;
  - иначе: запомнить `DQC.done[key].push({text: <label ответа + значения>, ids: action_ids})`; `case` null → «Дело закрыто ✓» + удалить из очереди + кнопка «Следующее дело →»; иначе перерисовать дело (ключ дела мог смениться — брать `case.key`).
  - 409 → «Дело изменилось — обновляю» + `dqcOpen(key)`; 400 → текст ошибки под кнопкой.
  - После любого действия — строка «На сайте обновится в течение 5 минут».
  - Ответ, правящий заявку (вопрос с `lead_id`, ответы birthday/distance) — над кнопкой предупреждение «Повторный импорт файла организатора может перезаписать правку заявки».
- `dqcPostpone()` — `POST cases/{key}/postpone {reason}` → дело уходит в «Отложено», счётчики обновить.
- `dqcUndo(actionId)` — `POST undo` → `dqcOpen(текущего ключа)` + счётчики (без `confirm()`: кнопка сначала меняется на «Точно отменить?», второй клик — отмена).
- `dqcNext()` — следующее дело в очереди после текущего.
- `dqcBack()` — телефон: снять `.dqc-layout--case`.
- `dqcSearch()` — debounce 300 мс, ≥ 2 символа → `GET cards?q=` → список «Фамилия Имя, ДР · события» (`events.join('; ')` мелко); клик → `dqcOpen` через `GET person/{id}` (ключ `p…` — дело без вопросов; `extra_cards = [id]` при ответах).
- `dqcMenu` (карточка «⋯»): «Склеить с…» — поиск карточки (`cards?q=`) → форма Ф/И/ДР (по умолчанию значения текущей карточки) → `POST /merge {client_ids: [текущая, выбранная], surname, name, birthday}`; «Исправить ФИО/ДР» → `POST /edit {table: 'clients', id, fields}`.
- Строка «⋯»: «Перенести на…» — поиск карточки → `POST /move {table, row_id, to_client_id}`; «Новая карточка» → `new_card`.
- После ручного действия — `dqcOpen(текущего)` с `extra_cards`, запись в `DQC.done` с id действия.
- Без `alert()`/`confirm()` — только текст в интерфейсе (у Playwright-проверки диалоги закрываются, у пользователя они раздражают).

- [ ] **Step 4:** `node --check static/js/admin-dq-cases.js` и `node tests/js/test_admin_dq_cases.js` → `ALL PASSED`. Удалить `static/js/admin-data-quality.js`; `grep -rn "admin-data-quality\|loadDataQualityTab\|dqFindings" templates static` → пусто (кроме CSS-классов `.dq-*`).
- [ ] **Step 5:** `tests/unit/ tests/integration/` зелёные (`tests/js/test_analytics_athlete_profile_view_toggle.js` и прочие js-тесты — тоже).
- [ ] **Step 6:** Commit (Task 2+3) `feat(admin/data-quality): экран дел — очередь, дело с вопросами, поиск, отложено, журнал`.

---

### Task 4: Проверка в браузере (локально)

- [ ] **Step 1:** Локальный сервер на `.env.local` на свободном порту (проверить `netstat -ano | grep LISTEN`: чужие сессии держат 8011). В локальной БД создать тестовые случаи на событиях 2099 года с уникальной фамилией (как в `tests/integration/test_dq_cases_db.py`): «Пцаревы» (детский результат отца + сын «Саша» + заглушка), «Ветрова» (ДР-заглушка в протоколе), двойник с предохранителем, заявка на детский забег родителя. После проверки — удалить.
- [ ] **Step 2: Playwright, 1400 px:** очередь показывает дела; открыть «Пцарев» — карточки рядом, проблемная строка подсвечена; ответ ★ «Пцарев Саша» → строка ✓ с «Отменить», следующий вопрос стал текущим; «Отменить» → вопрос вернулся; «Ветрова»: «Как в карточке» → дело закрыто → «Следующее дело»; конфликт → жёлтый блок «Склеить» → склеено; «Отложить дело» → дело во вкладке «Отложено» → оттуда ответить; поиск «Пцар» → дело; «Журнал» → отмена; «⋯» строки → перенести на другую карточку. Ни одного браузерного диалога.
- [ ] **Step 3: 390 px:** очередь → дело → «← К списку»; нет горизонтальной прокрутки; кнопки не обрезаны. Скриншоты обоих размеров — в отчёт.
- [ ] **Step 4:** Удалить тестовые данные, остановить сервер.

---

### Task 5: Деплой и прод

- [ ] **Step 1:** Полный прогон `tests/unit/ tests/integration/` и `node tests/js/*.js`.
- [ ] **Step 2:** После подтверждения пользователя — `git push origin main`, `gh run watch … --exit-status`.
- [ ] **Step 3: Прод (только чтение):** вкладка «Качество данных» под админ-сессией открывает очередь (время первой загрузки и повторной — в отчёт), дело открывается, вопросы читаемые; ничего не нажимать, кроме открытия дел и вкладок.
- [ ] **Step 4:** Ревью в `.taskmaster/tasks/todo.md`; Obsidian: заметка в `sessions/`, приоритеты (переработка «Качества данных» — выполнена, хвосты).
