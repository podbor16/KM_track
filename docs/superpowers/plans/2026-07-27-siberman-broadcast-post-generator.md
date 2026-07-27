# Siberman — генератор постов для трансляции — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Наполнить таб «Трансляция» в `/siberman/admin` генератором текстовых постов (3 режима: по этапу / по всей гонке / по дням) с полным ранжированным списком участников и кнопкой копирования.

**Architecture:** Чисто клиентская фича поверх уже существующего `/api/siberman/results` — новый backend не нужен. Несколько новых чистых функций в `static/js/siberman-common.js` (ранжирование/форматирование, покрыты `node:vm`-тестами по образцу существующих) + новая форма и генератор текста в `templates/siberman/admin.html`. `results.html` НЕ трогаем вообще (см. "Отклонение от спеки" ниже).

**Tech Stack:** Vanilla JS, Jinja2-шаблоны, существующий `node:vm` тест-харнесс (`tests/js/test_siberman_results_merge.js`) — в проекте нет JS-фреймворка тестирования.

**Отклонение от спеки:** Спека (`docs/superpowers/specs/2026-07-27-siberman-broadcast-post-generator-design.md`, Часть 3) предполагала перенос `paceValueLabel`/`fmtSecClock` из `results.html` в `common.js`. При детальном разборе кода выяснилось, что `paceValueLabel` форматирует УЖЕ ГОТОВОЕ значение темпа/скорости (используется только тултипом графика Chart.js) — генератору постов нужна ДРУГАЯ функция: вычислить средний темп/скорость ИЗ дистанции+времени. Вместо переноса существующих функций план вводит новую `avgPaceLabel(dbStage, distKm, elapsedS)` в `common.js`, переиспользующую ту же формулу единиц измерения, что уже есть в `splitPaceLabel`. **`results.html` в этом плане не изменяется совсем** — ниже риск регресса, чем предполагала спека.

---

## Task 1: `siberman-common.js` — вычислитель среднего темпа/скорости (`avgPaceLabel`)

**Files:**
- Modify: `static/js/siberman-common.js:166-176` (рефакторинг `splitPaceLabel` на общий хелпер + новая функция)
- Test: `tests/js/test_siberman_results_merge.js`

Сейчас `splitPaceLabel(dbStage, seq, splitS)` сама вычисляет `distKm` (по разнице соседних КТ) и внутри себя решает, в каких единицах форматировать (темп/100м для заплыва, км/ч для вело, темп/км для бега). Извлекаем эту развилку единиц в отдельный хелпер `_paceOrSpeedLabel(dbStage, distKm, timeS)`, который принимает уже готовые `distKm`/`timeS` — `splitPaceLabel` продолжает работать как раньше (просто передаёт вычисленный `distKm`), а новая `avgPaceLabel` использует тот же хелпер с ПОЛНОЙ дистанцией/временем от старта этапа до КТ (не split между соседними КТ).

- [ ] **Step 1: Написать падающий тест на `avgPaceLabel`**

Добавить в `tests/js/test_siberman_results_merge.js` (после блока `fmtGap`/`fieldGaps`-тестов, рядом с другими чистыми юнит-тестами):

```js
check('avgPaceLabel(swim) — темп на 100м из дистанции и времени', () => {
    // 2,6 км за 1500с → 1500/2.6=576.9 с/км → /10=57.7≈58с/100м → "0:58 /100м"
    const label = sandbox.avgPaceLabel('swim', 2.6, 1500);
    assert.strictEqual(label, sandbox.fmtPace100m(1500 / 2.6), `ожидался тот же формат, что и fmtPace100m: ${label}`);
});
check('avgPaceLabel(bike_day1) — скорость км/ч из дистанции и времени', () => {
    // 72 км за 7200с (2ч) → 36 км/ч
    const label = sandbox.avgPaceLabel('bike_day1', 72, 7200);
    assert.strictEqual(label, sandbox.fmtSpeed(72 / (7200 / 3600)), `ожидалась скорость через fmtSpeed: ${label}`);
});
check('avgPaceLabel(run) — темп мин/км из дистанции и времени', () => {
    // 35 км за 12600с → 360с/км → "6:00 /км"
    const label = sandbox.avgPaceLabel('run', 35, 12600);
    assert.strictEqual(label, sandbox.fmtPace(Math.round(12600 / 35)), `ожидался темп через fmtPace: ${label}`);
});
check('avgPaceLabel — null при отсутствии времени или нулевой дистанции', () => {
    assert.strictEqual(sandbox.avgPaceLabel('run', 10, null), '—', `null timeS → прочерк`);
    assert.strictEqual(sandbox.avgPaceLabel('run', 0, 100), '—', `нулевая дистанция → прочерк`);
});
check('splitPaceLabel не сломан рефакторингом (regression)', () => {
    // Существующий пример поведения ДО рефакторинга: 10 км общий сплит между
    // seq=1(3км) и seq=2(10км) на bike_day1 → distKm=7, если splitS=630 (10.5 мин)
    // → 7/(630/3600)=40 км/ч
    const label = sandbox.splitPaceLabel('bike_day1', 2, 630);
    assert.strictEqual(label, sandbox.fmtSpeed(7 / (630 / 3600)), `splitPaceLabel должен работать как раньше: ${label}`);
});
```

- [ ] **Step 2: Убедиться, что тест падает (функции ещё нет)**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL avgPaceLabel(swim) ...: sandbox.avgPaceLabel is not a function` (и аналогично для остальных трёх новых тестов; `splitPaceLabel` regression-тест должен уже проходить, т.к. функция ещё не тронута)

- [ ] **Step 3: Реализовать рефакторинг + `avgPaceLabel` в `siberman-common.js`**

Заменить текущий блок (строки 166-176):

```js
// Темп/скорость на СПЛИТЕ (между соседними КТ) — единицы зависят от этапа:
// плавание — темп на 100м, вело — скорость км/ч, бег — темп на 1 км.
function splitPaceLabel(dbStage, seq, splitS) {
    if (splitS == null) return '—';
    const distTable = CHECKPOINT_DIST_KM[dbStage];
    const distKm = distTable[seq] - (distTable[seq - 1] ?? 0);
    if (!(distKm > 0)) return '—';
    if (dbStage === 'swim') return fmtPace100m(splitS / distKm);
    if (dbStage === 'bike_day1' || dbStage === 'bike_day2') return fmtSpeed(distKm / (splitS / 3600));
    return fmtPace(Math.round(splitS / distKm));
}
```

на:

```js
// Общая развилка единиц измерения по этапу — плавание темп/100м, вело
// скорость км/ч, бег темп/км. Общий примитив для splitPaceLabel (сплит
// между соседними КТ) и avgPaceLabel (средний темп от старта этапа до КТ,
// нужен генератору постов трансляции) — раньше эта развилка была ТОЛЬКО
// внутри splitPaceLabel, дублировать её для второго случая означало бы
// повторить тот же класс расхождений, что уже чинили в этом проекте
// (см. шапку файла).
function _paceOrSpeedLabel(dbStage, distKm, timeS) {
    if (timeS == null || !(distKm > 0)) return '—';
    if (dbStage === 'swim') return fmtPace100m(timeS / distKm);
    if (dbStage === 'bike_day1' || dbStage === 'bike_day2') return fmtSpeed(distKm / (timeS / 3600));
    return fmtPace(Math.round(timeS / distKm));
}
// Темп/скорость на СПЛИТЕ (между соседними КТ).
function splitPaceLabel(dbStage, seq, splitS) {
    const distTable = CHECKPOINT_DIST_KM[dbStage];
    const distKm = distTable[seq] - (distTable[seq - 1] ?? 0);
    return _paceOrSpeedLabel(dbStage, distKm, splitS);
}
// Средний темп/скорость ОТ СТАРТА ЭТАПА до конкретной КТ (не сплит между
// соседними КТ) — нужен генератору постов трансляции ("темп на отметке X км").
function avgPaceLabel(dbStage, distKm, elapsedS) {
    return _paceOrSpeedLabel(dbStage, distKm, elapsedS);
}
```

- [ ] **Step 4: Прогнать тесты — все должны пройти**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED` (включая все существующие тесты — рефакторинг `splitPaceLabel` не должен сломать ни один)

- [ ] **Step 5: Коммит**

```bash
git add static/js/siberman-common.js tests/js/test_siberman_results_merge.js
git commit -m "feat(siberman): avgPaceLabel — средний темп/скорость от старта этапа до КТ"
```

---

## Task 2: `siberman-common.js` — гэпы и подписи для «Вело (оба дня)»

**Files:**
- Modify: `static/js/siberman-common.js:344-360` (рефакторинг `computeBikeCombinedCheckpointRanks` + новые функции)
- Test: `tests/js/test_siberman_results_merge.js`

Сейчас есть только `computeBikeCombinedCheckpointRanks` (места). Для постов нужен и гэп-вариант, и вычисление raw-времени на виртуальной КТ (не только ранг), и человекочитаемая подпись/дистанция для выпадающего списка КТ в форме генератора.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_siberman_results_merge.js`:

```js
check('bikeCombinedRawCp — виртуальный seq в пределах Дня 1 берёт cp.bike_day1 напрямую', () => {
    const row = { cp: { bike_day1: { 3: 5000 }, bike_day2: {} }, bike1_s: 20000 };
    assert.strictEqual(sandbox.bikeCombinedRawCp(row, 3), 5000, 'seq<=6 (День 1) — сырое значение cp.bike_day1');
});
check('bikeCombinedRawCp — виртуальный seq в Дне 2 прибавляет bike1_s (итог Дня 1)', () => {
    const n1 = sandbox.STAGE_MAX_SEQ.bike_day1; // 6
    const row = { cp: { bike_day1: {}, bike_day2: { 2: 3000 } }, bike1_s: 20000 };
    assert.strictEqual(sandbox.bikeCombinedRawCp(row, n1 + 2), 23000, 'День 2 seq2 → bike1_s + cp.bike_day2[2]');
});
check('bikeCombinedRawCp — null, если КТ ещё не пройдена', () => {
    const row = { cp: { bike_day1: {}, bike_day2: {} }, bike1_s: 20000 };
    assert.strictEqual(sandbox.bikeCombinedRawCp(row, 1), undefined, 'нет данных на этой КТ — undefined/null');
});
check('computeBikeCombinedCheckpointRanks не сломан рефакторингом (regression)', () => {
    const rows = [
        { key: 'A', cp: { bike_day1: { 6: 18000 }, bike_day2: {} }, bike1_s: 18000, status: 'active' },
        { key: 'B', cp: { bike_day1: { 6: 19000 }, bike_day2: {} }, bike1_s: 19000, status: 'active' },
    ];
    const ranks = sandbox.computeBikeCombinedCheckpointRanks(rows);
    assert.strictEqual(ranks[6].A, 1, 'A быстрее на КТ6 Дня 1 — место 1');
    assert.strictEqual(ranks[6].B, 2, 'B медленнее — место 2');
});
check('computeBikeCombinedCheckpointGaps — гэп между участниками на виртуальной КТ', () => {
    const rows = [
        { key: 'A', cp: { bike_day1: { 6: 18000 }, bike_day2: {} }, bike1_s: 18000, status: 'active' },
        { key: 'B', cp: { bike_day1: { 6: 19000 }, bike_day2: {} }, bike1_s: 19000, status: 'active' },
    ];
    const gaps = sandbox.computeBikeCombinedCheckpointGaps(rows);
    assert.strictEqual(gaps[6].A, 0, 'лидер — гэп 0');
    assert.strictEqual(gaps[6].B, 1000, 'отстаёт на 1000с');
});
check('bikeCombinedDistKm — дистанция на виртуальной КТ (День1 и День2)', () => {
    const n1 = sandbox.STAGE_MAX_SEQ.bike_day1;
    assert.strictEqual(sandbox.bikeCombinedDistKm(3), sandbox.CHECKPOINT_DIST_KM.bike_day1[3], 'КТ внутри Дня 1 — прямая дистанция');
    const expectedDay2 = sandbox.CHECKPOINT_DIST_KM.bike_day1[n1] + sandbox.CHECKPOINT_DIST_KM.bike_day2[2];
    assert.strictEqual(sandbox.bikeCombinedDistKm(n1 + 2), expectedDay2, 'КТ в Дне 2 — 145 (весь День1) + дистанция внутри Дня2');
});
check('bikeCombinedCheckpointLabel — подпись с пометкой дня', () => {
    const n1 = sandbox.STAGE_MAX_SEQ.bike_day1;
    assert.ok(sandbox.bikeCombinedCheckpointLabel(3).includes('День 1'), 'КТ Дня 1 помечена "(День 1)"');
    assert.ok(sandbox.bikeCombinedCheckpointLabel(n1 + 2).includes('День 2'), 'КТ Дня 2 помечена "(День 2)"');
});
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL bikeCombinedRawCp ...: sandbox.bikeCombinedRawCp is not a function` и аналогично для остальных пяти новых тестов

- [ ] **Step 3: Реализовать в `siberman-common.js`**

Заменить текущую `computeBikeCombinedCheckpointRanks` (строки 344-360):

```js
// Место "по этапу" для ОБЪЕДИНЁННОГО вело (день1+день2 как один этап,
// 421 км, без разрыва на границе дней) — та же семантика, что и
// computeCheckpointRanks (сравнение только внутри вело-этапа, не по всей
// гонке), но КТ дня2 сравниваются по elapsed-времени ОТ НАЧАЛА ВСЕГО
// вело-этапа (bike1_s + cp.bike_day2[seq]), а не только внутри дня2 —
// иначе участники с разным временем на дне1 сравнивались бы некорректно
// на одинаковых КТ дня2. rows должны нести cp и bike1_s (как в
// computeGlobalCheckpointRanks). Виртуальный seq: 1..STAGE_MAX_SEQ.bike_day1
// — день1, дальше — день2 со сдвигом.
function computeBikeCombinedCheckpointRanks(rows) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    return _checkpointRanksByValueFn(rows, (r, vseq) => {
        if (vseq <= n1) return r.cp?.bike_day1?.[vseq];
        const v2 = r.cp?.bike_day2?.[vseq - n1];
        return v2 == null ? null : (r.bike1_s ?? 0) + v2;
    }, n1 + STAGE_MAX_SEQ.bike_day2);
}
```

на:

```js
// Сырое elapsed-время на ВИРТУАЛЬНОЙ КТ объединённого вело (день1+день2 как
// один этап 0..421 км) — вынесено из computeBikeCombinedCheckpointRanks
// отдельной функцией, т.к. генератору постов трансляции нужно само значение
// времени (для строки "⏱️ Время на отметке"), не только место/гэп.
function bikeCombinedRawCp(row, vseq) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    if (vseq <= n1) return row.cp?.bike_day1?.[vseq];
    const v2 = row.cp?.bike_day2?.[vseq - n1];
    return v2 == null ? null : (row.bike1_s ?? 0) + v2;
}
// Место "по этапу" для ОБЪЕДИНЁННОГО вело (день1+день2 как один этап,
// 421 км, без разрыва на границе дней) — та же семантика, что и
// computeCheckpointRanks (сравнение только внутри вело-этапа, не по всей
// гонке), но КТ дня2 сравниваются по elapsed-времени ОТ НАЧАЛА ВСЕГО
// вело-этапа (bike1_s + cp.bike_day2[seq]), а не только внутри дня2 —
// иначе участники с разным временем на дне1 сравнивались бы некорректно
// на одинаковых КТ дня2. rows должны нести cp и bike1_s (как в
// computeGlobalCheckpointRanks). Виртуальный seq: 1..STAGE_MAX_SEQ.bike_day1
// — день1, дальше — день2 со сдвигом.
function computeBikeCombinedCheckpointRanks(rows) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    return _checkpointRanksByValueFn(rows, (r, vseq) => bikeCombinedRawCp(r, vseq), n1 + STAGE_MAX_SEQ.bike_day2);
}
// Гэп-вариант того же самого — нужен генератору постов трансляции (график
// "Позиция" использовал только Ranks, Gaps раньше не было нигде).
function computeBikeCombinedCheckpointGaps(rows) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    return _checkpointGapsByValueFn(rows, (r, vseq) => bikeCombinedRawCp(r, vseq), n1 + STAGE_MAX_SEQ.bike_day2);
}
// Дистанция (км) на виртуальной КТ объединённого вело — для отображения
// "N из 421 км" и для avgPaceLabel в постах трансляции.
function bikeCombinedDistKm(vseq) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    if (vseq <= n1) return CHECKPOINT_DIST_KM.bike_day1[vseq];
    return CHECKPOINT_DIST_KM.bike_day1[n1] + CHECKPOINT_DIST_KM.bike_day2[vseq - n1];
}
// Человекочитаемая подпись виртуальной КТ с пометкой дня — для выпадающего
// списка КТ в форме генератора постов трансляции.
function bikeCombinedCheckpointLabel(vseq) {
    const n1 = STAGE_MAX_SEQ.bike_day1;
    return vseq <= n1
        ? `${CHECKPOINT_LABELS.bike_day1[vseq]} (День 1)`
        : `${CHECKPOINT_LABELS.bike_day2[vseq - n1]} (День 2)`;
}
```

- [ ] **Step 4: Прогнать тесты — все должны пройти**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED`

- [ ] **Step 5: Коммит**

```bash
git add static/js/siberman-common.js tests/js/test_siberman_results_merge.js
git commit -m "feat(siberman): гэпы/дистанция/подписи для виртуальных КТ Вело (оба дня)"
```

---

## Task 3: `admin.html` — разметка таба «Трансляция» (форма + результат)

**Files:**
- Modify: `templates/siberman/admin.html`

- [ ] **Step 1: Добавить CSS для `<select>` и результата поста**

В `<style>` (после существующего правила `input[type=file], input[type=number] { ... }`, примерно после строки 17):

```css
select {
    display: block; width: 100%; padding: 10px 12px;
    border: 1px solid #ddd; border-radius: 6px; font-size: 14px;
    margin-bottom: 12px; background: #fff; font-family: inherit;
}
#bc-post-preview {
    width: 100%; min-height: 420px; font-family: 'Courier New', monospace;
    font-size: 13px; padding: 12px; border: 1px solid #ddd; border-radius: 6px;
    resize: vertical; white-space: pre-wrap;
}
```

- [ ] **Step 2: Заменить заглушку таба «Трансляция» на форму**

Найти текущий блок (создан коммитом `a9d300d`):

```html
        <div id="tab-broadcast" class="admin-tab-content" style="display:none">
            <div class="card">
                <h2>Трансляция</h2>
                <p style="color:#888;font-size:14px">Функционал для команды трансляции — в разработке.</p>
            </div>
        </div>
```

Заменить на:

```html
        <div id="tab-broadcast" class="admin-tab-content" style="display:none">
            <div class="card">
                <h2>Генератор постов</h2>
                <label>Год</label>
                <input type="number" id="bc-year" value="2025" min="2020" max="2030" style="width:120px">

                <label>Режим</label>
                <select id="bc-mode" style="width:280px">
                    <option value="stage">По этапу</option>
                    <option value="global">По всей гонке (виртуальный зачёт)</option>
                    <option value="day">По дням</option>
                </select>

                <div id="bc-stage-field">
                    <label>Этап</label>
                    <select id="bc-stage" style="width:280px"></select>
                </div>
                <div id="bc-cp-field">
                    <label>Контрольная точка</label>
                    <select id="bc-cp" style="width:360px"></select>
                </div>
                <div id="bc-day-field" style="display:none">
                    <label>День</label>
                    <select id="bc-day" style="width:220px">
                        <option value="day1">День 1</option>
                        <option value="day1plus2">День 1+2</option>
                    </select>
                </div>

                <label>Категория</label>
                <select id="bc-category" style="width:220px">
                    <option value="M">Мужчины</option>
                    <option value="F">Женщины</option>
                    <option value="relay">Эстафеты</option>
                </select>

                <button class="btn btn-primary" id="btn-bc-generate" style="margin-top:8px">Сгенерировать</button>
            </div>

            <div class="card" id="bc-result-card" style="display:none">
                <h2>Готовый пост (полный список)</h2>
                <textarea id="bc-post-preview" readonly></textarea>
                <button class="btn btn-success" id="btn-bc-copy" style="margin-top:12px">Копировать</button>
                <span id="bc-copy-ok" style="display:none;color:#27ae60;font-size:13px;margin-left:10px">✓ Скопировано!</span>
            </div>
        </div>
```

- [ ] **Step 3: Подключить `siberman-common.js`**

В `<head>` (после `<title>`, рядом нет пока никаких `<script src>` — первый в файле):

```html
    <script src="/static/js/siberman-common.js?v={{ v }}"></script>
```

- [ ] **Step 4: Открыть страницу локально и убедиться, что форма отрисовалась без JS-ошибок**

Run (если локальный сервер уже поднят — см. Task 6 для полного запуска): открыть `/siberman/admin` в браузере (потребуется логин), переключиться на таб «Трансляция».
Expected: видна форма (Год/Режим/Этап/КТ/Категория/кнопка «Сгенерировать»), в консоли браузера нет ошибок (поля `bc-stage`/`bc-cp` пока пустые — заполнит JS в Task 4).

- [ ] **Step 5: Коммит**

```bash
git add templates/siberman/admin.html
git commit -m "feat(siberman): разметка таба «Трансляция» — форма генератора постов"
```

---

## Task 4: `admin.html` — JS: заполнение выпадающих списков (Режим/Этап/КТ)

**Files:**
- Modify: `templates/siberman/admin.html` (добавить в существующий `<script>` блок, после блока `prefillRaceStart`)

- [ ] **Step 1: Добавить код заполнения списков**

Добавить в конец `<script>` (после существующего кода `$('btn-startlist').addEventListener(...)`):

```js
    // ---- Трансляция: генератор постов ----

    const BC_STAGE_OPTIONS_BY_MODE = {
        stage:  [['swim', 'Плавание'], ['bike_day1', 'Вело День 1'], ['bike_day2', 'Вело День 2'], ['bike_combined', 'Вело (оба дня)'], ['run', 'Бег']],
        global: [['swim', 'Плавание'], ['bike_day1', 'Вело День 1'], ['bike_day2', 'Вело День 2'], ['run', 'Бег']],
    };

    function bcMaxSeq(stage) {
        return stage === 'bike_combined' ? (STAGE_MAX_SEQ.bike_day1 + STAGE_MAX_SEQ.bike_day2) : STAGE_MAX_SEQ[stage];
    }
    function bcCpLabel(stage, seq) {
        return stage === 'bike_combined' ? bikeCombinedCheckpointLabel(seq) : CHECKPOINT_LABELS[stage][seq];
    }
    function bcDistKm(stage, seq) {
        return stage === 'bike_combined' ? bikeCombinedDistKm(seq) : CHECKPOINT_DIST_KM[stage][seq];
    }

    function bcPopulateStageOptions() {
        const mode = $('bc-mode').value;
        const sel = $('bc-stage');
        sel.innerHTML = '';
        (BC_STAGE_OPTIONS_BY_MODE[mode] || []).forEach(([val, label]) => {
            const opt = document.createElement('option');
            opt.value = val;
            opt.textContent = label;
            sel.appendChild(opt);
        });
        bcPopulateCpOptions();
    }
    function bcPopulateCpOptions() {
        const stage = $('bc-stage').value;
        const sel = $('bc-cp');
        sel.innerHTML = '';
        const maxSeq = bcMaxSeq(stage);
        for (let seq = 1; seq <= maxSeq; seq++) {
            const opt = document.createElement('option');
            opt.value = seq;
            opt.textContent = bcCpLabel(stage, seq);
            sel.appendChild(opt);
        }
    }
    function bcOnModeChange() {
        const mode = $('bc-mode').value;
        $('bc-stage-field').style.display = mode === 'day' ? 'none' : '';
        $('bc-cp-field').style.display = mode === 'day' ? 'none' : '';
        $('bc-day-field').style.display = mode === 'day' ? '' : 'none';
        if (mode !== 'day') bcPopulateStageOptions();
    }

    $('bc-mode').addEventListener('change', bcOnModeChange);
    $('bc-stage').addEventListener('change', bcPopulateCpOptions);
    bcOnModeChange(); // начальное состояние при загрузке страницы
```

- [ ] **Step 2: Проверить в браузере**

Открыть `/siberman/admin` → таб «Трансляция».
Expected: «Этап» показывает 5 вариантов (Плавание…Бег), «КТ» — заполнен подписями для выбранного этапа (например, для «Плавание» — «Разворот 1 (1,3 км)», «1 круг (2,6 км)»...). Переключение «Режим» → «По всей гонке» убирает «Вело (оба дня)» из списка этапов (4 варианта) и пересчитывает КТ. Переключение на «По дням» скрывает поля «Этап»/«КТ», показывает «День».

- [ ] **Step 3: Коммит**

```bash
git add templates/siberman/admin.html
git commit -m "feat(siberman): динамические списки Этап/КТ в генераторе постов"
```

---

## Task 5: `admin.html` — JS: сборка строк участника (имя, роль в эстафете, время+темп)

**Files:**
- Modify: `templates/siberman/admin.html`

- [ ] **Step 1: Добавить код построения пулов по категории и отображения имени**

Добавить сразу после блока из Task 4:

```js
    function bcCategoryRows(data, category) {
        if (category === 'relay') {
            return data.relay.map(t => {
                const g = teamGapRow(t);
                return { key: t.bib, cp: g.cp, status: g.status, swim_s: g.swim_s, bike1_s: g.bike1_s, bike2_s: g.bike2_s, run_s: g.run_s, _team: t };
            });
        }
        return data.individual
            .filter(r => r.gender === category)
            .map(r => ({ key: r.bib, cp: r.cp, status: r.status, swim_s: r.swim_s, bike1_s: r.bike1_s, bike2_s: r.bike2_s, run_s: r.run_s, _ind: r }));
    }

    const BC_ROLE_WORD = { swim: 'плывёт', bike_day1: 'едет', bike_day2: 'едет', bike_combined: 'едет', run: 'бежит' };
    const BC_ROLE_MEMBER_STAGE = { swim: 'swim', bike_day1: 'bike', bike_day2: 'bike', bike_combined: 'bike', run: 'run' };

    function bcDisplayName(row, category, stage) {
        if (category !== 'relay') {
            const p = row._ind;
            return `${p.surname} ${p.name}`;
        }
        const team = row._team;
        const roleWord = BC_ROLE_WORD[stage];
        const memberStage = BC_ROLE_MEMBER_STAGE[stage];
        const member = team.members.find(m => m.relay_stage === memberStage);
        const memberName = member ? `${member.surname} ${member.name}` : '';
        return `${team.team_name} (${roleWord}: ${memberName})`;
    }

    // Сырое elapsed-время НА ЭТАПЕ (для строки "⏱️ ... на отметке") — не
    // глобальное время гонки, даже в режиме "По всей гонке" (там от этого
    // значения зависит только показ времени/темпа, а РАНГ считается отдельно
    // через globalProgress — см. bcBuildStagePost/bcBuildGlobalPost).
    function bcStageRawTime(row, stage, seq) {
        return stage === 'bike_combined' ? bikeCombinedRawCp(row, seq) : row.cp?.[stage]?.[seq];
    }
    // dbStage для форматирования единиц (avgPaceLabel/fmtSpeed и т.п.) —
    // виртуальный "bike_combined" сам по себе не единица измерения, нужно
    // понять, в какой РЕАЛЬНЫЙ день попадает конкретная виртуальная КТ.
    function bcUnitStage(stage, seq) {
        if (stage !== 'bike_combined') return stage;
        return seq <= STAGE_MAX_SEQ.bike_day1 ? 'bike_day1' : 'bike_day2';
    }

    function bcRankEmoji(n) {
        const keycaps = ['0️⃣','1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣'];
        return n <= 9 ? keycaps[n] : `${n}.`;
    }
```

- [ ] **Step 2: Коммит**

```bash
git add templates/siberman/admin.html
git commit -m "feat(siberman): построение пулов по категории + отображение имени/роли эстафетчика"
```

(Визуальной проверки на этом шаге нет — код пока не вызывается ни одним обработчиком, следующая задача подключает генерацию.)

---

## Task 6: `admin.html` — JS: генератор текста, Режим «По этапу» и «По всей гонке»

**Files:**
- Modify: `templates/siberman/admin.html`

- [ ] **Step 1: Добавить построение заголовка и списка записей**

Добавить сразу после блока из Task 5:

```js
    const BC_STAGE_TITLE = { swim: 'ПЛАВАНИЕ', bike_day1: 'ВЕЛО ДЕНЬ 1', bike_day2: 'ВЕЛО ДЕНЬ 2', bike_combined: 'ВЕЛО (ОБА ДНЯ)', run: 'БЕГ' };
    const BC_STAGE_EMOJI = { swim: { M: '🏊🏻‍♂️', F: '🏊🏻', relay: '🏊🏻‍♂️' }, bike_day1: '🚴', bike_day2: '🚴', bike_combined: '🚴', run: '🏃' };
    const BC_CATEGORY_TITLE = { M: 'МУЖЧИНЫ', F: 'ЖЕНЩИНЫ', relay: 'ЭСТАФЕТЫ' };

    function bcStageEmoji(stage, category) {
        const e = BC_STAGE_EMOJI[stage];
        return typeof e === 'string' ? e : e[category];
    }

    // Ранжированный + отфильтрованный по видимости список для одной КТ —
    // общий для обоих режимов (различаются только источником ranksBySeq/gapsBySeq).
    function bcRankedList(rows, ranksBySeq, gapsBySeq, seq) {
        const ranks = ranksBySeq[seq] || {};
        const gaps = gapsBySeq[seq] || {};
        return rows
            .filter(r => ranks[r.key] != null)
            .map(r => ({ row: r, rank: ranks[r.key], gap: gaps[r.key] }))
            .sort((a, b) => a.rank - b.rank);
    }

    function bcGapWording(mode, category) {
        if (mode === 'stage') {
            return { leader: 'Преимущество над 2-м местом', trail: 'Отставание от лидера' };
        }
        return {
            leader: 'Виртуальное преимущество над 2-м местом',
            trail: category === 'relay' ? 'Отставание от лидеров' : 'Отставание от лидера',
        };
    }

    // Дистанции swim — дробные (1.3/2.6 км...), сайт везде показывает их с
    // русской запятой (см. CHECKPOINT_LABELS.swim: "1,3 км" — уже строка с
    // запятой), а не точкой — интерполяция числа в текст поста напрямую дала
    // бы точку, расходясь с остальным сайтом.
    function bcFmtKm(km) {
        return String(km).replace('.', ',');
    }

    // "Время на отметке" — только в режиме "По этапу" (посты 1-3 исходного
    // ТЗ). В "По всей гонке" исходное ТЗ (посты 4-5) подставляет НАЗВАНИЕ
    // ЭТАПА вместо слова "Время" ("Бег на отметке...") — найдено на
    // финальном ревью, где строка ошибочно была одинаковой в обоих режимах.
    const BC_STAGE_TITLE_INLINE = { swim: 'Плавание', bike_day1: 'Вело День 1', bike_day2: 'Вело День 2', bike_combined: 'Вело (оба дня)', run: 'Бег' };

    function bcEntryText(item, idx, list, category, stage, seq, mode) {
        const wording = bcGapWording(mode, category);
        const name = bcDisplayName(item.row, category, stage);
        const timeS = bcStageRawTime(item.row, stage, seq);
        const distKm = bcDistKm(stage, seq);
        const pace = avgPaceLabel(bcUnitStage(stage, seq), distKm, timeS);
        const timeLinePrefix = mode === 'global' ? BC_STAGE_TITLE_INLINE[stage] : 'Время';
        const timeLine = `⏱️ ${timeLinePrefix} на отметке ${bcFmtKm(distKm)} км: ${fmtTime(timeS)} (${pace})`;
        let gapLine;
        if (idx === 0) {
            const second = list[1];
            const advGap = second ? second.gap : null;
            const advText = advGap != null ? fmtGap(advGap).replace(/^\+/, '') : '—';
            gapLine = `📊 ${wording.leader}: ${advText}`;
        } else {
            gapLine = `📊 ${wording.trail}: ${fmtGap(item.gap)}`;
        }
        return `${bcRankEmoji(idx + 1)} ${name}\n${timeLine}\n${gapLine}`;
    }

    // suffix — конец предложения после "N из M км(N кругов)"; по умолчанию
    // просто точка (режим "По этапу"), режим "По всей гонке" передаёт
    // " этапа «Название».", чтобы получить одно связное предложение —
    // раньше это делалось через .replace('.', ...) поверх готовой строки,
    // что ЛОМАЛОСЬ на дробных дистанциях заплыва (нашёл бы первую точку в
    // "1.3 км", а не точку в конце предложения) — суффикс теперь параметр,
    // а не постобработка строки.
    function bcCpHeaderLine(stage, seq, suffix) {
        const distKm = bcDistKm(stage, seq);
        const totalKm = bcDistKm(stage, bcMaxSeq(stage));
        const laps = lapLabel(bcUnitStage(stage, seq), stage === 'bike_combined' ? (seq <= STAGE_MAX_SEQ.bike_day1 ? seq : seq - STAGE_MAX_SEQ.bike_day1) : seq);
        const lapsSuffix = laps ? ` (${laps})` : '';
        return `📍 Контрольная точка: ${bcFmtKm(distKm)} из ${bcFmtKm(totalKm)} км${lapsSuffix}${suffix ?? '.'}`;
    }

    function bcBuildStagePost(data, stage, seq, category) {
        const rows = bcCategoryRows(data, category);
        const maxSeq = bcMaxSeq(stage);
        const { ranksBySeq, gapsBySeq } = stage === 'bike_combined'
            ? { ranksBySeq: computeBikeCombinedCheckpointRanks(rows), gapsBySeq: computeBikeCombinedCheckpointGaps(rows) }
            : { ranksBySeq: computeCheckpointRanks(rows, stage, maxSeq), gapsBySeq: computeCheckpointGaps(rows, stage, maxSeq) };
        const list = bcRankedList(rows, ranksBySeq, gapsBySeq, seq);
        if (list.length === 0) return 'Нет данных для выбранной КТ (никто из категории ещё её не прошёл).';

        const title = `${BC_CATEGORY_TITLE[category]}. ${bcStageEmoji(stage, category)} ${BC_STAGE_TITLE[stage]}. SIBERMAN 2026`;
        const header = bcCpHeaderLine(stage, seq);
        const body = list.map((item, idx) => bcEntryText(item, idx, list, category, stage, seq, 'stage')).join('\n\n');
        return `${title}\n${header}\n\nТекущая расстановка на этапе:\n\n${body}`;
    }

    function bcBuildGlobalPost(data, stage, seq, category) {
        const rows = bcCategoryRows(data, category);
        const maxSeq = STAGE_MAX_SEQ[stage];
        const ranksBySeq = computeGlobalCheckpointRanks(rows, stage, maxSeq);
        const gapsBySeq = computeGlobalCheckpointGaps(rows, stage, maxSeq);
        const list = bcRankedList(rows, ranksBySeq, gapsBySeq, seq);
        if (list.length === 0) return 'Нет данных для выбранной КТ (никто из категории ещё её не прошёл).';

        const titleSuffix = category === 'relay' ? '' : '. ЛИЧНЫЙ ЗАЧЁТ';
        const title = `${BC_CATEGORY_TITLE[category]}${titleSuffix}. SIBERMAN 2026`;
        const header = bcCpHeaderLine(stage, seq, ` этапа «${BC_STAGE_TITLE[stage]}».`);
        const body = list.map((item, idx) => bcEntryText(item, idx, list, category, stage, seq, 'global')).join('\n\n');
        return `${title}\n${header}\n\nТекущая расстановка по сумме трёх дней гонки.\n\n${body}`;
    }
```

- [ ] **Step 2: Проверить сборку в изоляции (Node, без браузера)**

Быстрая ручная проверка синтаксиса без полноценного теста (страница требует реальных данных гонки, которых нет в тестовом харнессе `node:vm` для этого файла — `admin.html` не разбирается тем тестовым скриптом, он только для `results.html`):

Run: `node -e "require('vm').runInNewContext(require('fs').readFileSync('static/js/siberman-common.js','utf8') + require('fs').readFileSync('templates/siberman/admin.html','utf8').match(/<script>([\s\S]*?)<\/script>/g).map(s=>s.replace(/<\/?script>/g,'')).join('\n'), { document: { getElementById: () => ({addEventListener(){}, style:{}}), querySelectorAll: () => [] }, window: {}, fetch: () => {} }); console.log('syntax OK')"`
Expected: `syntax OK` (ловит опечатки/незакрытые скобки без реального запуска браузера)

- [ ] **Step 3: Коммит**

```bash
git add templates/siberman/admin.html
git commit -m "feat(siberman): генератор текста поста — режимы «По этапу» и «По всей гонке»"
```

---

## Task 7: `admin.html` — JS: Режим «По дням» + подключение кнопок «Сгенерировать»/«Копировать»

**Files:**
- Modify: `templates/siberman/admin.html`

- [ ] **Step 1: Добавить построение поста «По дням»**

Добавить сразу после блока из Task 6:

```js
    const BC_DAY_CONFIG = {
        day1:      { stage: 'bike_day1', label: '1' },
        day1plus2: { stage: 'bike_day2', label: '1+2' },
    };

    function bcBuildDayPost(data, dayKey, category) {
        const cfg = BC_DAY_CONFIG[dayKey];
        const rows = bcCategoryRows(data, category);
        const maxSeq = STAGE_MAX_SEQ[cfg.stage];
        const ranksBySeq = computeGlobalCheckpointRanks(rows, cfg.stage, maxSeq);
        const gapsBySeq = computeGlobalCheckpointGaps(rows, cfg.stage, maxSeq);
        const list = bcRankedList(rows, ranksBySeq, gapsBySeq, maxSeq);
        if (list.length === 0) return 'Нет данных — этот день ещё не завершён ни для одного участника категории.';

        const title = `${BC_CATEGORY_TITLE[category]}. ИТОГИ ДНЯ ${cfg.label}. SIBERMAN 2026`;
        const header = `📍 Снапшот на конец дня ${cfg.label}.`;
        const wording = { leader: 'Преимущество над 2-м местом', trail: category === 'relay' ? 'Отставание от лидеров' : 'Отставание от лидера' };
        const body = list.map((item, idx) => {
            const name = bcDisplayName(item.row, category, cfg.stage);
            let gapLine;
            if (idx === 0) {
                const second = list[1];
                const advGap = second ? second.gap : null;
                const advText = advGap == null ? '—' : (advGap === 0 ? '0:00' : fmtGap(advGap).replace(/^\+/, ''));
                gapLine = `📊 ${wording.leader}: ${advText}`;
            } else {
                gapLine = `📊 ${wording.trail}: ${fmtGap(item.gap)}`;
            }
            const timeS = globalProgress(item.row, cfg.stage, maxSeq); // не сырой cp[stage][seq] — для bike_day2 это elapsed от старта ДНЯ 2, а не гонки (см. globalProgress/day2Progress в results.html)
            return `${bcRankEmoji(idx + 1)} ${name}\n⏱️ Итоговое время: ${fmtTime(timeS)}\n${gapLine}`;
        }).join('\n\n');
        return `${title}\n${header}\n\nТекущая расстановка по сумме дня ${cfg.label} гонки:\n\n${body}`;
    }
```

- [ ] **Step 2: Подключить кнопки «Сгенерировать» и «Копировать»**

Добавить сразу после блока из Step 1:

```js
    async function bcGenerate() {
        const btn = $('btn-bc-generate');
        const resultCard = $('bc-result-card');
        const ta = $('bc-post-preview');
        btn.textContent = 'Генерирую…';
        resultCard.style.display = 'none';
        try {
            const year = $('bc-year').value;
            const r = await fetch(`/api/siberman/results?year=${year}`);
            if (!r.ok) throw new Error('Не удалось загрузить данные');
            const data = await r.json();
            const mode = $('bc-mode').value;
            const category = $('bc-category').value;
            let text;
            if (mode === 'stage') {
                text = bcBuildStagePost(data, $('bc-stage').value, Number($('bc-cp').value), category);
            } else if (mode === 'global') {
                text = bcBuildGlobalPost(data, $('bc-stage').value, Number($('bc-cp').value), category);
            } else {
                text = bcBuildDayPost(data, $('bc-day').value, category);
            }
            ta.value = text;
            resultCard.style.display = '';
        } catch (e) {
            ta.value = 'Ошибка: ' + e.message;
            resultCard.style.display = '';
        } finally {
            btn.textContent = 'Сгенерировать';
        }
    }
    $('btn-bc-generate').addEventListener('click', bcGenerate);

    $('btn-bc-copy').addEventListener('click', async () => {
        const ta = $('bc-post-preview');
        const ok = $('bc-copy-ok');
        try {
            await navigator.clipboard.writeText(ta.value);
        } catch (e) {
            ta.select();
            document.execCommand('copy');
        }
        ok.style.display = '';
        setTimeout(() => { ok.style.display = 'none'; }, 2000);
    });
```

- [ ] **Step 3: Синтаксическая проверка**

Run: та же команда, что в Task 6 Step 2.
Expected: `syntax OK`

- [ ] **Step 4: Коммит**

```bash
git add templates/siberman/admin.html
git commit -m "feat(siberman): режим «По дням» + кнопки Сгенерировать/Копировать"
```

---

## Task 8: Полная проверка на реальных данных 2025 года + деплой

**Files:** нет изменений кода — только верификация.

- [ ] **Step 1: Прогнать полный JS-тест-сьют (регрессия)**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED` (все тесты, включая добавленные в Task 1/2)

- [ ] **Step 2: Локальная ручная проверка (если поднимается локальный сервер с доступом к БД)**

Открыть `/siberman/admin`, залогиниться, открыть таб «Трансляция», для года 2025:
1. Режим «По этапу» → Плавание → любая КТ → Мужчины → «Сгенерировать» — сверить с вкладкой «Плавание» на `/siberman/results` (те же люди, те же места на этой КТ)
2. Режим «По этапу» → Плавание → Эстафеты — проверить, что в скобках указан ИМЕННО пловец команды (сверить с карточкой команды на `/siberman/results`)
3. Режим «По этапу» → Вело (оба дня) → КТ из Дня 2 → Мужчины — сверить место с графиком «Позиция → Вело (оба дня)» на той же КТ
4. Режим «По всей гонке» → Бег → любая КТ → Мужчины — сверить место с графиком «Позиция → Вся гонка» на эквивалентной точке (после 155+276=431 км + километраж на этой КТ бега)
5. Режим «По дням» → День 1 → Мужчины — сверить порядок/времена с вкладкой «День 1» на `/siberman/results`
6. Режим «По дням» → День 1+2 → Эстафеты — сверить с вкладкой «День 1+2»
7. Кнопка «Копировать» — вставить в любое текстовое поле, убедиться, что текст скопировался целиком

Expected: во всех 7 пунктах — совпадение мест/времён/отставаний между постом и соответствующей вкладкой `/siberman/results` (в пределах округления секунд).

- [ ] **Step 3: Убедиться, что `results.html` не задет диффом**

Run: `git diff HEAD~7 -- templates/siberman/results.html` (7 коммитов = все коммиты этого плана; число подобрать по факту количества коммитов Task 1-7)
Expected: пустой вывод — `results.html` не изменялся ни в одном коммите этого плана (см. "Отклонение от спеки" в шапке документа)

- [ ] **Step 4: Push и мониторинг деплоя**

```bash
git push origin main
```

Run: `gh run list --limit 1` в цикле до `completed success` (тот же паттерн, что использовался в этой сессии ранее — `gh run list --limit 1 --json status,conclusion`).
Expected: `completed success`

- [ ] **Step 5: Проверка на живом проде через `agent-browser`**

Открыть `https://live.siberman515.com/siberman/admin`, залогиниться, повторить пункты 1-7 из Step 2 на реальных прод-данных. Сделать хотя бы один скриншот итогового поста для визуальной проверки эмодзи/переносов строк.

- [ ] **Step 6: Обновить Obsidian**

Отметить задачу выполненной в `C:\Users\podbo\Documents\Obsidian_vaults\KM_Track\inbox\2026-07-27-siberman-broadcast-post-generator.md` (статус → done) и в `00-home/текущие приоритеты.md` (бэклог-пункт → ✅, с датой и коротким резюме).
