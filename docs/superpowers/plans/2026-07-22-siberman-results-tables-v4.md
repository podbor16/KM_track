# Siberman results.html — переработка главных таблиц (v4, п.7-9) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Единая система бейджей места (М1/Ж1/Э1) на всех главных таблицах `/siberman/results` — убрать отдельные колонки «Пол»/«Формат», подсветить строки эстафеты, добавить 3-колоночный режим (Формат/Пол/Абсолют) на вкладках этапов и Своде вело при фильтре «Эстафета», добавить отставания на Днях, показать фильтр по полу на персонифицированных вкладках при «Эстафета».

**Architecture:** Одна большая переработка одного файла (`templates/siberman/results.html`, inline `<script>`). Все таблицы делятся на два типа: «командные» (Итоги гонки, День 1, День 2 — у эстафеты нет личного пола на этом уровне) и «персонифицированные» (вкладки этапов, Свод вело — у эстафеты уже есть настоящий личный пол конкретного участника). Общий генерик-рендерер двух колонок места переиспользуется обоими типами; персонифицированные таблицы дополнительно получают отдельный 3-колоночный рендерер для фильтра «Эстафета».

**Tech Stack:** Vanilla JS (без фреймворка), Chart.js не затрагивается. Тесты — `node:vm` харнесс (`tests/js/test_siberman_results_merge.js`), Python — `pytest` (не затрагивается, JS-only правка).

**Spec:** `docs/superpowers/specs/2026-07-22-siberman-results-tables-v4-design.md`

---

## Общий контекст для каждой задачи

Работаем в `c:\Users\podbo\Работа\КРАСМАРАФОН\KM_track`, ветка `main`, коммитить и пушить напрямую в `main` (пользователь явно разрешил в этой сессии, `dangerouslyDisableSandbox: true` для push).

Тесты запускаются так:
```bash
node tests/js/test_siberman_results_merge.js
node tests/js/test_siberman_participant.js
conda run -n base python -m pytest tests/unit/ -q
```
Тестовый харнесс — `node:vm`, без реального DOM/Canvas. `sandbox`, `vm`, `assert`, `check`, `setState(fmt, gender)`, `setRaceData(individual, relay, raceStartEpoch)`, `mkTimerInd(bib, overrides)` уже определены в начале `tests/js/test_siberman_results_merge.js` — не переопределять, читать первые ~60 строк файла перед добавлением тестов.

После каждой задачи — верификация на реальных данных прода: `curl -s "https://live.siberman515.com/api/siberman/results?year=2025"` (публичный read-only API), throwaway `node:vm`-скрипт по паттерну существующих `deploy/verify_*.js` (см. `git log -p` для примеров в этой сессии — файл создаётся, используется, удаляется, НЕ коммитится).

Коммит — по-русски, `feat(siberman): ...`/`fix(siberman): ...`, объяснение "почему", заканчивается:
```
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

---

### Task 1: Общий бейдж формата + CSS + генерик-рендерер 2 колонок места

**Files:**
- Modify: `static/js/siberman-common.js` (новая функция `formatBadge()`)
- Modify: `templates/siberman/results.html:269-283` (CSS, добавить `.badge-e`, `.badge-individual`, стили подсветки строки эстафеты) и `templates/siberman/results.html:487-498` (переписать `rankHeaderCells`/`rankBodyCells`)
- Test: `tests/js/test_siberman_results_merge.js`

Это ФУНДАМЕНТ для всех остальных задач — переписывает сигнатуру `rankHeaderCells`/`rankBodyCells`, используемую везде. Задачи 2-5 зависят от этой задачи.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_siberman_results_merge.js` перед финальным `console.log(failures === 0 ...`:

```js
check('formatBadge() — бейдж "Э" тем же CSS-паттерном, что genderBadge', () => {
    const html = vm.runInContext('formatBadge', sandbox)();
    assert.ok(html.includes('badge-e'), `ожидался класс badge-e: ${html}`);
    assert.ok(html.includes('>Э<'), `ожидалась буква Э: ${html}`);
});
check('rankHeaderCells(label, swapped=false) — Место первой колонкой', () => {
    const html = sandbox.rankHeaderCells('Пол/Формат', false);
    assert.strictEqual(html, '<th>Место</th><th>Пол/Формат</th>');
});
check('rankHeaderCells(label, swapped=true) — вторичная колонка первой', () => {
    const html = sandbox.rankHeaderCells('Формат', true);
    assert.strictEqual(html, '<th>Формат</th><th>Абсолют</th>');
});
check('rankBodyCells — не swapped: абсолют первой ячейкой, бейдж+число второй', () => {
    const html = sandbox.rankBodyCells(5, 2, '<span class="badge badge-m">М</span>', '', false);
    const m = html.match(/^<td>(.*?)<\/td><td>(.*?)<\/td>$/);
    assert.ok(m, `неожиданная структура: ${html}`);
    assert.ok(m[1].includes('>5<'), `первая колонка — абсолют 5: ${html}`);
    assert.ok(m[2].includes('badge-m') && m[2].includes('>2<'), `вторая колонка — бейдж+2: ${html}`);
});
check('rankBodyCells — swapped: вторичная ячейка первой', () => {
    const html = sandbox.rankBodyCells(5, 2, '<span class="badge badge-e">Э</span>', '', true);
    const m = html.match(/^<td>(.*?)<\/td><td>(.*?)<\/td>$/);
    assert.ok(m[1].includes('badge-e') && m[1].includes('>2<'), `первая колонка — Э-бейдж+2: ${html}`);
    assert.ok(m[2].includes('>5<'), `вторая колонка — абсолют 5: ${html}`);
});
check('rankBodyCells — rankSecondary=null даёт прочерк во вторичной ячейке', () => {
    const html = sandbox.rankBodyCells(5, null, '', '', false);
    assert.ok(html.includes('<span class="muted">—</span>'), `ожидался прочерк: ${html}`);
});
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL` на всех новых проверках — `formatBadge is not a function`, `rankHeaderCells` возвращает старый формат (одна колонка при teamLevel, другая сигнатура параметров и т.д.)

- [ ] **Step 3: Реализовать `formatBadge()` в `static/js/siberman-common.js`**

Найти `function genderBadge(g) {` (строка 48) и добавить сразу после закрывающей `}` (строка 52):

```js
function formatBadge() {
    return '<span class="badge badge-e">Э</span>';
}
```

- [ ] **Step 4: Добавить CSS в `templates/siberman/results.html`**

Найти блок `.badge-relay { ... }` (строка 276) и добавить после него:

```css
        .badge-e { background: rgba(106,171,215,.15); color: var(--blue); }
        .badge-individual { background: rgba(122,170,191,.12); color: var(--muted); font-weight: 700; }
```

Найти блок top-3 подсветки (`tbody tr.rank-1 { ... }` — строка 258) и добавить после `tbody tr.rank-1:hover, tbody tr.rank-2:hover, tbody tr.rank-3:hover { background: var(--bg3); }` (строка 261):

```css
        /* Строка эстафеты — синяя подсветка + полоска слева (вариант C
           брейншторминга 2026-07-22), поверх top-3 подсветки (обе
           полупрозрачные, конфликта не будет — полоска остаётся основным
           индикатором эстафеты). */
        tbody tr.relay-row { background: rgba(106,171,215,.08); box-shadow: inset 3px 0 0 var(--blue); }
        tbody tr.relay-row:hover { background: var(--bg3); }
```

- [ ] **Step 5: Переписать `rankHeaderCells`/`rankBodyCells` в `templates/siberman/results.html:487-498`**

Заменить:

```js
function rankHeaderCells(teamLevel = false) {
    if (teamLevel && _fmt === 'relay') return '<th>Место</th>';
    return _gender === 'all'
        ? '<th>Место</th><th>По полу</th>'
        : '<th>По полу</th><th>Абсолют</th>';
}
function rankBodyCells(rankAbs, rankGender, gender, rc, teamLevel = false) {
    if (teamLevel && _fmt === 'relay') return `<td><span class="rank-num ${rc}">${rankAbs ?? '—'}</span></td>`;
    const a = `<span class="rank-num ${rc}">${rankAbs ?? '—'}</span>`;
    const g = rankGender != null ? `<span class="rank-num ${rc}">${genderBadge(gender)}${rankGender}</span>` : '<span class="muted">—</span>';
    return _gender === 'all' ? `<td>${a}</td><td>${g}</td>` : `<td>${g}</td><td>${a}</td>`;
}
```

на:

```js
// Место — генерик-рендерер ДВУХ колонок: абсолют + вторичный ранг (смысл —
// пол или формат, решает вызывающий код). secondaryLabel — заголовок второй
// колонки. swapped — вторичная колонка первой (для персонифицированных
// таблиц триггер — активный фильтр _gender; для командных — _fmt==='relay';
// каждый вызывающий код решает сам). secondaryBadge — HTML готового бейджа
// буквы (genderBadge(gender) или formatBadge()) — тоже решает вызывающий код,
// эта функция не знает, эстафета строка или личник.
function rankHeaderCells(secondaryLabel, swapped) {
    return swapped
        ? `<th>${secondaryLabel}</th><th>Абсолют</th>`
        : `<th>Место</th><th>${secondaryLabel}</th>`;
}
function rankBodyCells(rankAbs, rankSecondary, secondaryBadge, rc, swapped) {
    const a = `<span class="rank-num ${rc}">${rankAbs ?? '—'}</span>`;
    const s = rankSecondary != null ? `<span class="rank-num ${rc}">${secondaryBadge}${rankSecondary}</span>` : '<span class="muted">—</span>';
    return swapped ? `<td>${s}</td><td>${a}</td>` : `<td>${a}</td><td>${s}</td>`;
}
```

**ВАЖНО:** после этого шага вызовы `rankHeaderCells()`/`rankBodyCells()` по всему файлу (в `buildIndividualOverallRow`, `buildRelayOverallRow`, `OVERALL_TABLE_HEAD`, `renderStage`, `renderBikeCombined`, `buildProgressRow`) окажутся с НЕПРАВИЛЬНОЙ сигнатурой вызова — они будут вызывать функцию со старыми аргументами. Это ОЖИДАЕМО и будет исправлено в задачах 2-5 (каждая занимается своим набором вызовов). На этом шаге НЕ трогать другие функции — задача 1 только меняет сигнатуру и добавляет CSS/бейдж.

- [ ] **Step 6: Убедиться, что новые тесты проходят**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: 6 новых тестов `OK`. Остальные тесты, вызывающие `rankHeaderCells`/`rankBodyCells` через `renderOverall`/`renderStage`/`renderBikeCombined`/Дни (если такие есть — проверить по имени, ищи `renderOverall`, `renderStage`, `renderBikeCombined`, `renderDay` в существующих тестах), в этот момент MOGUT падать — это ожидаемо, чинится в задачах 2-5. Если тестов на эти функции нет вообще (проверить командой `grep -n "sandbox.renderOverall\|sandbox.renderStage\|sandbox.renderBikeCombined\|sandbox.renderDay" tests/js/test_siberman_results_merge.js`) — значит падать нечему, весь файл должен быть `ALL PASSED` уже на этом шаге.

- [ ] **Step 7: Commit**

```bash
git add static/js/siberman-common.js templates/siberman/results.html tests/js/test_siberman_results_merge.js
git commit -m "$(cat <<'EOF'
refactor(siberman): формат-бейдж Э + генерик 2-колоночный рендерер места (п.7-9, задача 1/5)

Фундамент для переработки главных таблиц — formatBadge() (Э, тот же
паттерн что genderBadge), rankHeaderCells/rankBodyCells переписаны на
generic secondaryLabel/swapped вместо жёсткого "пол или ничего"
(teamLevel убран — теперь у эстафеты ВСЕГДА есть значение показать,
формат вместо пола). CSS для подсветки строки эстафеты (вариант C
брейншторминга) и бейджа "Индивидуальный".

Вызовы rankHeaderCells/rankBodyCells по остальному файлу будут
обновлены отдельными коммитами (задачи 2-5 плана) — это единственная
задача плана, которая намеренно оставляет файл в переходном состоянии
между шагами одного коммита, не между коммитами.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 2: Итоги гонки (renderOverall)

**Files:**
- Modify: `templates/siberman/results.html:500-597` (`buildIndividualOverallRow`, `buildRelayOverallRow`, `OVERALL_TABLE_HEAD`)
- Test: `tests/js/test_siberman_results_merge.js`

Зависит от Task 1 (использует новую сигнатуру `rankHeaderCells`/`rankBodyCells`).

- [ ] **Step 1: Написать падающий тест**

```js
check('renderOverall() — эстафета получает бейдж Э{формат} вместо прочерка, строка подсвечена, колонки Пол/Формат убраны', () => {
    setState('all', 'all');
    const ind = mkTimerInd('1', { surname: 'Иванов', name: 'Иван', status: 'active', overall_s: 20000, overall_rank_g: 1, cp: { run: { [vm.runInContext('STAGE_MAX_SEQ.run', sandbox)]: 20000 } } });
    const relay = [{
        bib: '1000', team_name: 'Автобаланс', overall_s: 22000,
        members: [
            { relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 1000, cp: { swim: { [vm.runInContext('STAGE_MAX_SEQ.swim', sandbox)]: 1000 } } },
            { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: 9000, bike2_s: 8000, cp: {} },
            { relay_stage: 'run', status: 'active', gender: 'M', run_s: 4000, cp: { run: { [vm.runInContext('STAGE_MAX_SEQ.run', sandbox)]: 22000 } } },
        ],
    }];
    setRaceData([ind], relay, Date.now());
    sandbox.renderOverall();
    const html = domGetAppHtml();
    assert.ok(!html.includes('<th>Пол</th>'), `колонка "Пол" должна быть убрана: ${html.slice(0,500)}`);
    assert.ok(!html.includes('<th>Формат</th>'), `колонка "Формат" должна быть убрана: ${html.slice(0,500)}`);
    assert.ok(html.includes('badge-e') && html.includes('>Э1<'), `эстафета должна получить бейдж Э1 (единственная команда — формат-ранг 1): ${html}`);
    assert.ok(html.includes('relay-row'), `строка эстафеты должна быть подсвечена: ${html}`);
    assert.ok(html.includes('badge-individual'), `личник должен получить бейдж "Индивидуальный": ${html}`);
});
```

Добавить хелпер `domGetAppHtml()` перед этим тестом, если такого ещё нет в файле (проверить `grep -n "function domGetAppHtml" tests/js/test_siberman_results_merge.js`) — читает `elementsById['app'].innerHTML` (тот же `elementsById`, что использует `domStub`):

```js
function domGetAppHtml() {
    return domStub('app').innerHTML;
}
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL` — колонки Пол/Формат ещё присутствуют, `rankBodyCells`/`rankHeaderCells` вызываются со старой сигнатурой (упадёт с ошибкой типа или неверным HTML).

- [ ] **Step 3: Реализовать**

Заменить `templates/siberman/results.html:500-597` (от `function buildIndividualOverallRow` до конца `const OVERALL_TABLE_HEAD = ...`) на:

```js
// Место — 2 колонки (Абсолют + Пол/Формат), swapped при fmt==='relay'
// (формат становится первой колонкой) — команда не имеет личного пола на
// этом уровне (три разных человека на трёх этапах), поэтому вторая колонка
// у эстафеты ВСЕГДА показывает формат-ранг, у личника — гендерный.
function overallSecondaryLabel() {
    if (_fmt === 'relay') return 'Формат';
    return _fmt === 'individual' ? 'По полу' : 'Пол/Формат';
}
function overallRankSwapped() { return _fmt === 'relay'; }

function buildIndividualOverallRow(r, overallGaps, combinedRanks) {
    const notFinished = r.overall_s == null || r.status !== 'active';
    const rc = notFinished ? '' : rankClass(combinedRanks[r.bib]);
    const cur = currentStage(r);
    const pos = cur ? lastReached(r.cp, cur) : null;
    const lastCpCell = pos ? `${STAGE_LABEL_RU[cur]}, ${CHECKPOINT_LABELS[cur][pos.seq]}` : '—';
    return `<tr class="${rc}${notFinished ? ' dnf' : ''}" style="cursor:pointer" onclick="window.open('${participantLink(r.bib)}','_blank')">
        ${rankBodyCells(combinedRanks[r.bib], r.overall_rank_g, genderBadge(r.gender), rc, overallRankSwapped())}
        <td class="bib-cell">${r.bib}</td>
        <td>
            <span class="name-main">${r.surname} ${r.name}</span>
            <span class="badge badge-individual">Индивидуальный</span>
            ${r.city ? `<br><span class="name-city">${r.city}</span>` : ''}
        </td>
        <td class="r time-cell muted">${fmtTime(r.swim_s)}</td>
        <td class="r time-cell muted">${fmtTime(r.bike1_s)}</td>
        <td class="r time-cell muted">${fmtTime(r.bike2_s)}</td>
        <td class="r time-cell muted">${fmtTime(r.run_s)}</td>
        <td class="r time-cell" style="font-weight:800">${fmtTime(r.overall_s)}</td>
        <td class="muted">${lastCpCell}</td>
        <td class="r muted">${fmtGap(overallGaps[r.bib])}</td>
        <td>${statusBadge(r, null)}</td>
    </tr>`;
}

// Эстафета в Итогах гонки — ОДНА строка (название команды), как и у
// личников, без развёрнутого списка участников по ролям (см. п.14
// задачи 2026-07-19). formatRanks — новое: место среди только эстафетных
// команд (computeRanksByValue по overall_s ТОЛЬКО эстафеты, полный ростер
// года — не зависит от текущих фильтров, тот же принцип что combinedRanks).
function buildRelayOverallRow(team, overallGaps, combinedRanks, formatRanks) {
    const tr = teamGapRow(team);
    const notFinished = team.overall_s == null || tr.status !== 'active';
    const rc = notFinished ? '' : rankClass(combinedRanks[team.bib]);
    const cur = currentStage(tr);
    const pos = cur ? lastReached(tr.cp, cur) : null;
    const lastCpCell = pos ? `${STAGE_LABEL_RU[cur]}, ${CHECKPOINT_LABELS[cur][pos.seq]}` : '—';
    const statusCell = teamStatusBadge(team);
    return `<tr class="relay-row ${rc}${notFinished ? ' dnf' : ''}" style="cursor:pointer" onclick="window.open('${participantLink(team.bib)}','_blank')">
        ${rankBodyCells(combinedRanks[team.bib], formatRanks[team.bib], formatBadge(), rc, overallRankSwapped())}
        <td class="bib-cell">${team.bib}</td>
        <td><span class="name-main">${team.team_name}</span> <span class="badge badge-relay">Эстафета</span></td>
        <td class="r time-cell muted">${fmtTime(tr.swim_s)}</td>
        <td class="r time-cell muted">${fmtTime(tr.bike1_s)}</td>
        <td class="r time-cell muted">${fmtTime(tr.bike2_s)}</td>
        <td class="r time-cell muted">${fmtTime(tr.run_s)}</td>
        <td class="r time-cell" style="font-weight:800">${fmtTime(team.overall_s)}</td>
        <td class="muted">${lastCpCell}</td>
        <td class="r muted">${fmtGap(overallGaps[team.bib])}</td>
        <td>${statusCell}</td>
    </tr>`;
}

// Объединяет личников и эстафету в порядок отображения: финишировавшие обоих
// типов перемежаются по времени (единый список по месту), затем не
// финишировавшие личники (свой порядок sortByStatus), затем команды без
// результатов — в конце. Возвращает массив {type, entry}.
function buildMergedOverallEntries(individual, relay) {
    const indSorted = sortByStatus(individual, 'overall_s');
    if (_fmt !== 'all') {
        // Только один тип виден — смешивать нечего.
        return [
            ...indSorted.map(r => ({ type: 'individual', entry: r })),
            ...relay.map(t => ({ type: 'relay', entry: t })),
        ];
    }
    const indFinished = indSorted.filter(r => r.overall_s != null && r.status === 'active');
    const indRest = indSorted.filter(r => !(r.overall_s != null && r.status === 'active'));
    const relFinished = relay.filter(t => t.overall_s != null).sort((a, b) => a.overall_s - b.overall_s);
    const relRest = relay.filter(t => t.overall_s == null);

    const interleaved = [
        ...indFinished.map(r => ({ type: 'individual', entry: r })),
        ...relFinished.map(t => ({ type: 'relay', entry: t })),
    ].sort((a, b) => a.entry.overall_s - b.entry.overall_s);

    return [
        ...interleaved,
        ...indRest.map(r => ({ type: 'individual', entry: r })),
        ...relRest.map(t => ({ type: 'relay', entry: t })),
    ];
}

const OVERALL_TABLE_HEAD = () => `<thead><tr>
    ${rankHeaderCells(overallSecondaryLabel(), overallRankSwapped())}<th>№</th><th>Участник</th>
    <th class="r">🏊 Плав.</th>
    <th class="r">🚴 Вело 1</th>
    <th class="r">🚴 Вело 2</th>
    <th class="r">🏃 Бег</th>
    <th class="r">Итого</th>
    <th>Последняя КТ</th>
    <th class="r">Отставание</th>
    <th>Статус</th>
</tr></thead>`;
```

Теперь найти `function renderOverall() {` (было на строке 599, теперь может сдвинуться) и внутри неё найти вызов `buildRelayOverallRow(item.entry, overallGaps, combinedRanks)` (в `merged.forEach`) — добавить вычисление `relayFormatRanks` и передать его:

Найти:
```js
    const combinedRanks = computeCombinedOverallRanks(combinedOverallRankRows(_data.individual, _data.relay));
    let html = buildStats(individual, relay, null);
```

Заменить на:
```js
    const combinedRanks = computeCombinedOverallRanks(combinedOverallRankRows(_data.individual, _data.relay));
    // Формат-ранг — место команды среди ТОЛЬКО эстафетных команд по всей
    // гонке, полный ростер года (не зависит от текущих фильтров) — тот же
    // принцип, что и combinedRanks.
    const relayFormatRanks = computeRanksByValue(_data.relay.map(t => ({ key: t.bib, val: t.overall_s, status: teamGapRow(t).status })));
    let html = buildStats(individual, relay, null);
```

И найти:
```js
        html += item.type === 'individual'
            ? buildIndividualOverallRow(item.entry, overallGaps, combinedRanks)
            : buildRelayOverallRow(item.entry, overallGaps, combinedRanks);
```

Заменить на:
```js
        html += item.type === 'individual'
            ? buildIndividualOverallRow(item.entry, overallGaps, combinedRanks)
            : buildRelayOverallRow(item.entry, overallGaps, combinedRanks, relayFormatRanks);
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED`

- [ ] **Step 5: Проверить на реальных данных**

Написать throwaway `deploy/verify_overall.js` (паттерн из предыдущих задач сессии — загрузить `siberman-common.js`+инлайн-скрипт из `results.html` в общий `vm`-контекст, стабы `document`/`Chart`, подгрузить реальный JSON, вызвать `sandbox.renderOverall()`, распечатать HTML или его фрагмент), убедиться что колонки Пол/Формат отсутствуют, у реальных эстафетных команд бейдж Э{N} корректный (сравнить с ручным пересчётом по `overall_s`), удалить скрипт.

- [ ] **Step 6: Commit**

```bash
git add templates/siberman/results.html tests/js/test_siberman_results_merge.js
git commit -m "$(cat <<'EOF'
feat(siberman): Итоги гонки — бейджи М1/Ж1/Э1, убрать колонки Пол/Формат (п.7, задача 2/5)

Вторая колонка места теперь всегда несёт значение (Пол/Формат) —
раньше у эстафеты был прочерк (teamLevel-схлопывание). Новая
formatRanks — место среди только эстафетных команд по overall_s,
полный ростер года. Строка эстафеты подсвечена (vs C брейншторминга),
бейдж "Индивидуальный" у личников — симметрично "Эстафета".

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 3: Вкладки этапов (renderStage) — истинный абсолют + 3-колоночный режим

**Files:**
- Modify: `templates/siberman/results.html:647-825` (`renderStage`, `buildIndividualStageRow`, `buildRelayStageRow`)
- Test: `tests/js/test_siberman_results_merge.js`

Зависит от Task 1. Самая крупная задача плана — две независимые части: (A) делает «Абсолют»/«По полу» настоящими (полный ростер этапа, не зависят от текущих фильтров — согласовано с пользователем 2026-07-22), (B) добавляет 3-колоночный режим при `_fmt === 'relay'`.

- [ ] **Step 1: Написать падающие тесты**

```js
check('renderStage() — "Абсолют" на этапе теперь настоящий (не зависит от фильтра пола)', () => {
    // 3 личника на плавании: М 300с (быстрее), Ж 400с, Ж 500с. При фильтре
    // "Женщины" абсолют СЕЙЧАС (до правки) стал бы местом СРЕДИ ЖЕНЩИН (1,2)
    // — после правки должен остаться истинным полем (2,3), т.к. мужчина
    // быстрее обеих.
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const rows = [
        mkTimerInd('1', { gender: 'M', swim_s: 300, cp: { swim: { [maxSeqSwim]: 300 } } }),
        mkTimerInd('2', { gender: 'F', swim_s: 400, cp: { swim: { [maxSeqSwim]: 400 } } }),
        mkTimerInd('3', { gender: 'F', swim_s: 500, cp: { swim: { [maxSeqSwim]: 500 } } }),
    ];
    setRaceData(rows, [], Date.now());
    setState('individual', 'F');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    // Женщина №2 — истинный абсолют 2 (мужчина быстрее), НЕ 1.
    assert.ok(!html.includes('>1<') || !/rank-num[^<]*>1</.test(html.split('bib-cell">2<')[0].slice(-200)), `грубая проверка — детальная ниже через прямой вызов функции`);
});
check('renderStage() внутренние ранги — computeRanksByValue по ПОЛНОМУ ростеру, не по getFiltered()', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const rows = [
        mkTimerInd('1', { gender: 'M', swim_s: 300, cp: { swim: { [maxSeqSwim]: 300 } } }),
        mkTimerInd('2', { gender: 'F', swim_s: 400, cp: { swim: { [maxSeqSwim]: 400 } } }),
        mkTimerInd('3', { gender: 'F', swim_s: 500, cp: { swim: { [maxSeqSwim]: 500 } } }),
    ];
    setRaceData(rows, [], Date.now());
    setState('individual', 'F');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    // Строка bib=2 должна содержать rank-num "2" (истинный абсолют), не "1".
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">2<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка bib=2 не найдена: ${html}`);
    assert.ok(/rank-num[^>]*>2</.test(rowMatch[0]), `ожидался истинный абсолют 2 в строке личницы №2: ${rowMatch[0]}`);
});
check('renderStage() фильтр "Эстафета" — 3 колонки Формат/Пол/Абсолют', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const relay = [
        { bib: '1000', team_name: 'КомандаА', members: [{ relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 300, cp: { swim: { [maxSeqSwim]: 300 } } }] },
        { bib: '1001', team_name: 'КомандаБ', members: [{ relay_stage: 'swim', status: 'active', gender: 'F', swim_s: 400, cp: { swim: { [maxSeqSwim]: 400 } } }] },
    ];
    setRaceData([], relay, Date.now());
    setState('relay', 'all');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    assert.ok(html.includes('<th>Формат</th>') && html.includes('<th>Пол</th>') && html.includes('<th>Абсолют</th>'), `ожидались 3 колонки: ${html.slice(0,600)}`);
});
check('renderStage() фильтр "Эстафета" — формат/пол рассчитаны по ПОЛНОМУ ростеру этапа, не зависят от текущего gender-фильтра', () => {
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const relay = [
        { bib: '1000', team_name: 'КомандаА', members: [{ relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 300, cp: { swim: { [maxSeqSwim]: 300 } } }] },
        { bib: '1001', team_name: 'КомандаБ', members: [{ relay_stage: 'swim', status: 'active', gender: 'F', swim_s: 400, cp: { swim: { [maxSeqSwim]: 400 } } }] },
    ];
    setRaceData([], relay, Date.now());
    // Фильтр по полу "Мужчины" — КомандаБ (женщина) не отображается в строках,
    // но её формат-ранг 2 (среди ВСЕХ эстафетчиков этапа) не должен исчезнуть
    // из расчёта для КомандыА — КомандаА всё равно формат-ранг 1 (была бы 1
    // и без фильтра, тест ниже проверяет то, что расчёт НЕ падает и НЕ равен
    // "1 из 1" — т.е. пул для ранжирования не сузился до отфильтрованных).
    setState('relay', 'M');
    sandbox.renderStage('swim');
    const html = domGetAppHtml();
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1000<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка КомандыА не найдена: ${html}`);
    assert.ok(/badge-e">Э<\/span>1/.test(rowMatch[0]), `КомандаА должна получить Э1 (быстрее КомандыБ): ${rowMatch[0]}`);
});
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL` на всех 4 новых.

- [ ] **Step 3: Реализовать**

Заменить `templates/siberman/results.html:647-825` (всю функцию `renderStage`) на:

```js
function renderStage(stage) {
    const cfg = STAGE_CFG[stage];
    const dbStage = TAB_TO_DB_STAGE[stage];
    const maxSeq = STAGE_MAX_SEQ[dbStage];
    const { individual, relay } = getFiltered();

    // "Тихий" DNF на ЭТОМ этапе: participant.status==='active' в БД (в файле
    // не было явной пометки DNF/ДНФ), но последняя пройденная КТ этапа —
    // не финишная. Подменяем status на 'dnf' ТОЛЬКО в локальной копии для
    // этой вкладки (не мутируя общие данные _data — на других вкладках/в
    // Финале участник мог этот этап пройти полностью раньше). После подмены
    // остальная логика (сортировка, бейдж статуса) отрабатывает как для
    // обычного DNF — включая getDnfStage/statusBadge, которые уже умеют
    // корректно показывать "Финишировал"/DNF/"Не стартовал" по этапам.
    const withStageStatus = r => {
        const pos = lastReached(r.cp, dbStage);
        const silentDnf = r.status === 'active' && pos && pos.seq !== maxSeq;
        return silentDnf ? { ...r, status: 'dnf' } : r;
    };

    const rows = sortByStatus(individual.map(withStageStatus), cfg.timeKey);
    let relayMembers = _fmt !== 'individual'
        ? relay.flatMap(t => t.members
            .filter(m => m.relay_stage === cfg.relayStage && (_gender === 'all' || m.gender === _gender))
            .map(m => withStageStatus({...m, _bib: t.bib, _team: t.team_name})))
        : [];
    // Сортировать эстафеты: сначала реально финишировавшие этап (по времени),
    // затем "тихие" DNF (есть частичное время, но не дошли до финиша), затем
    // те, кто ещё не начал (нет данных вовсе).
    relayMembers = relayMembers.sort((a, b) => {
        const catOf = m => {
            const pos = lastReached(m.cp, dbStage);
            if (!pos) return 2;
            return pos.seq === maxSeq ? 0 : 1;
        };
        const catA = catOf(a), catB = catOf(b);
        if (catA !== catB) return catA - catB;
        const ta = a[cfg.timeKey], tb = b[cfg.timeKey];
        if (ta == null && tb == null) return 0;
        if (ta == null) return 1;
        if (tb == null) return -1;
        return ta - tb;
    });

    if (rows.length === 0 && relayMembers.length === 0) {
        document.getElementById('app').innerHTML = '<div class="empty">Нет данных</div>';
        return;
    }

    // Отставание — общий пул личников этой роли + эстафетчиков той же роли,
    // т.к. они соревнуются на этапе вместе (как и старт вело-2 в задаче 2).
    const gapPool = [
        ...rows.map(r => ({ key: r.bib, cp: r.cp, status: r.status })),
        ...relayMembers.map(m => ({ key: `${m._bib}:${m.relay_stage}`, cp: m.cp, status: m.status })),
    ];
    const gaps = computeStageGaps(gapPool, TAB_TO_DB_STAGE[stage]);

    const showStart = stage === 'bike2';

    // Присваиваем эстафетчикам, финишировавшим этап, собственный порядковый
    // "Финишировал этап" — та же проверка, что раньше использовал ручной
    // relayPos-счётчик; сам счётчик убран (см. ниже — единый ранг вместо него).
    const relayMembersRanked = relayMembers.map(m => {
        const pos = lastReached(m.cp, dbStage);
        return { ...m, _finished: !!pos && pos.seq === maxSeq };
    });

    // "Абсолют"/"По полу"/"Формат" — НАСТОЯЩИЕ ранги: считаются по ПОЛНОМУ
    // ростеру этапа (весь _data, не getFiltered()-отфильтрованный набор),
    // не зависят от текущих фильтров формата/пола — тот же принцип, что и
    // "Абсолют" в Итогах гонки/на карточке участника (согласовано с
    // пользователем 2026-07-22 — раньше здесь была фильтро-зависимая
    // величина, что вводило в заблуждение при активном фильтре по полу).
    const allIndRows = _data.individual.map(withStageStatus)
        .map(r => ({ key: r.bib, val: r[cfg.timeKey], status: r.status, gender: r.gender, isRelay: false }));
    const allRelayRows = _data.relay
        .flatMap(t => t.members.filter(m => m.relay_stage === cfg.relayStage).map(m => withStageStatus({ ...m, _bib: t.bib, _team: t.team_name })))
        .map(m => ({ key: `${m._bib}:${m.relay_stage}`, val: m[cfg.timeKey], status: m.status, gender: m.gender, isRelay: true }));
    const allStageRows = [...allIndRows, ...allRelayRows];
    const stageAbsRanks = computeRanksByValue(allStageRows);
    const stageGenderRanks = {
        M: computeRanksByValue(allStageRows.filter(x => x.gender === 'M')),
        F: computeRanksByValue(allStageRows.filter(x => x.gender === 'F')),
    };
    const stageFormatRanks = computeRanksByValue(allStageRows.filter(x => x.isRelay));
    const stageGenderRankFor = (key, gender) => stageGenderRanks[gender]?.[key];

    let html = buildStats(individual, relay, stage);

    // При активном фильтре по полу "Место" (2-колоночный режим) должно быть
    // местом ВНУТРИ этого пола (пересчитанным, не абсолютным) — иначе
    // абсолютный ранг (17, 20...) выглядит так, будто места "не
    // пересчитались" под фильтр. Не применяется в 3-колоночном режиме
    // (fmt==='relay') — там все три ранга показаны одновременно явно.
    const mainRankFor = (key, gender) => _gender === 'all' ? stageAbsRanks[key] : stageGenderRankFor(key, gender);
    const isRelayFilter = _fmt === 'relay';

    const buildIndividualStageRow = r => {
        const t = r[cfg.timeKey];
        const noTime = t == null;
        const rc = noTime ? '' : rankClass(mainRankFor(r.bib, r.gender));
        const pos = lastReached(r.cp, dbStage);
        const lastCpCell = pos ? CHECKPOINT_LABELS[dbStage][pos.seq] : '—';
        // isRelayFilter невозможно для личника (fmt='relay' исключает
        // личников через getFiltered), но rankBodyCells здесь всегда 2-кол.
        const rankCells = rankBodyCells(stageAbsRanks[r.bib], stageGenderRankFor(r.bib, r.gender), genderBadge(r.gender), noTime ? '' : rc, _gender !== 'all');
        return `<tr class="${rc}${(noTime || r.status !== 'active') ? ' dnf' : ''}" style="cursor:pointer" onclick="window.open('${participantLink(r.bib)}','_blank')">
            ${rankCells}
            <td class="bib-cell">${r.bib}</td>
            <td>
                <span class="name-main">${r.surname} ${r.name}</span>
                <span class="badge badge-individual">Индивидуальный</span>
            </td>
            <td class="r time-cell">${fmtTime(t)}</td>
            <td class="muted">${lastCpCell}</td>
            <td class="r muted">${fmtGap(gaps[r.bib])}</td>
            <td class="r muted">${noTime ? '—' : cfg.metaFn(r[cfg.metaKey])}</td>
            ${showStart ? `<td class="r muted">${fmtTime(r.bike2_start_s)}</td>` : ''}
            <td>${statusBadge(r, stage)}</td>
        </tr>`;
    };

    const buildRelayStageRow = m => {
        const t = m[cfg.timeKey];
        const key = `${m._bib}:${m.relay_stage}`;
        const meta = cfg.metaFn(stage === 'swim' ? m.swim_pace : stage === 'bike1' ? m.bike1_speed : stage === 'bike2' ? m.bike2_speed : m.run_pace);
        const hasTime = t != null;
        const pos = lastReached(m.cp, dbStage);
        const lastCpCell = pos ? CHECKPOINT_LABELS[dbStage][pos.seq] : '—';
        const mainRank = mainRankFor(key, m.gender);
        const rc = mainRank != null ? rankClass(mainRank) : '';
        // 3-колоночный режим (Формат/Пол/Абсолют) только при fmt==='relay' —
        // тогда личников на этапе нет вовсе, buildIndividualStageRow не
        // вызывается, три колонки в шапке соответствуют трём ячейкам здесь.
        const rankCells = isRelayFilter
            ? `<td><span class="rank-num ${rc}">${formatBadge()}${stageFormatRanks[key] ?? '—'}</span></td>` +
              `<td>${stageGenderRankFor(key, m.gender) != null ? `<span class="rank-num ${rc}">${genderBadge(m.gender)}${stageGenderRankFor(key, m.gender)}</span>` : '<span class="muted">—</span>'}</td>` +
              `<td><span class="rank-num ${rc}">${stageAbsRanks[key] ?? '—'}</span></td>`
            : rankBodyCells(stageAbsRanks[key], stageGenderRankFor(key, m.gender), genderBadge(m.gender), rc, _gender !== 'all');
        return `<tr class="relay-row ${rc}" style="cursor:pointer" onclick="window.open('${participantLink(m._bib)}','_blank')">
            ${rankCells}
            <td class="bib-cell">${m._bib}</td>
            <td>
                <span class="name-main">${m.surname} ${m.name}</span> <span class="badge badge-relay">Эстафета</span>
                <br><span class="name-city">${m._team}</span>
            </td>
            <td class="r time-cell">${fmtTime(t)}</td>
            <td class="muted">${lastCpCell}</td>
            <td class="r muted">${fmtGap(gaps[`${m._bib}:${m.relay_stage}`])}</td>
            <td class="r muted">${hasTime ? meta : '—'}</td>
            ${showStart ? `<td class="r muted">${fmtTime(m.bike2_start_s)}</td>` : ''}
            <td>${!hasTime && m.status === 'active' ? '<span class="badge badge-live">В гонке</span>' : relayMemberStatusBadge(m)}</td>
        </tr>`;
    };

    // Единый порядок: финишировавшие этот этап (личники + эстафетчики этой
    // роли) перемежаются по времени, затем остальные (не финишировавшие
    // личники — свой порядок sortByStatus, затем не финишировавшие
    // эстафетчики) — без разделительной строки-заголовка "Эстафеты".
    const rowsFinished = rows.filter(r => r[cfg.timeKey] != null && r.status === 'active');
    const rowsRest = rows.filter(r => !(r[cfg.timeKey] != null && r.status === 'active'));
    const relFinished = relayMembersRanked.filter(m => m._finished);
    const relRest = relayMembersRanked.filter(m => !m._finished);

    let orderedRows;
    if (_fmt === 'all') {
        const interleaved = [
            ...rowsFinished.map(r => ({ type: 'individual', entry: r })),
            ...relFinished.map(m => ({ type: 'relay', entry: m })),
        ].sort((a, b) => a.entry[cfg.timeKey] - b.entry[cfg.timeKey]);
        orderedRows = [
            ...interleaved,
            ...rowsRest.map(r => ({ type: 'individual', entry: r })),
            ...relRest.map(m => ({ type: 'relay', entry: m })),
        ];
    } else {
        orderedRows = [
            ...rows.map(r => ({ type: 'individual', entry: r })),
            ...relayMembersRanked.map(m => ({ type: 'relay', entry: m })),
        ];
    }

    const rankHead = isRelayFilter
        ? '<th>Формат</th><th>Пол</th><th>Абсолют</th>'
        : rankHeaderCells(_gender === 'all' ? 'По полу' : 'Абсолют', _gender !== 'all');
    html += `<div class="table-wrap"><table class="stage-table">
    <thead><tr>
        ${rankHead}<th>№</th><th>Участник</th>
        <th class="r">Время</th><th>Последняя КТ</th><th class="r">Отставание</th><th class="r">${cfg.metaLbl}</th>
        ${showStart ? '<th class="r">Старт вело-2</th>' : ''}
        <th>Статус</th>
    </tr></thead><tbody>`;
    orderedRows.forEach(item => {
        html += item.type === 'individual' ? buildIndividualStageRow(item.entry) : buildRelayStageRow(item.entry);
    });
    html += '</tbody></table></div>';
    document.getElementById('app').innerHTML = html;
}
```

**Примечание про заголовок 2-колоночного режима:** `rankHeaderCells(_gender === 'all' ? 'По полу' : 'Абсолют', _gender !== 'all')` — при `_gender==='all'` заголовок «Место | По полу» (`swapped=false` → `secondaryLabel` показывается второй колонкой, значение параметра при `swapped=false` не используется как текст первой колонки, там всегда «Место»/«Абсолют» — свериться с `rankHeaderCells` из Task 1: при `swapped=false` возвращает `<th>Место</th><th>${secondaryLabel}</th>`, при `swapped=true` — `<th>${secondaryLabel}</th><th>Абсолют</th>`). Значение `secondaryLabel` в обоих случаях — «По полу» когда `_gender==='all'` (несвёрнуто, вторая колонка), и когда `_gender!=='all'` тоже нужно «По полу» как ПЕРВАЯ колонка (текст, а не «Абсолют» — эта деталь неочевидна из кода `rankHeaderCells`, который при `swapped=true` жёстко пишет «Абсолют» как ВТОРУЮ колонку, а `secondaryLabel` — как первую). Итог: `secondaryLabel` всегда равен «По полу», параметр называется «secondaryLabel», а не «primaryWhenSwapped» — передавать буквально `rankHeaderCells('По полу', _gender !== 'all')` (без тернарника на текст, тернарник только на `swapped`). Поправить это место при реализации — тернарник на первом аргументе неверен, должен быть просто `'По полу'`.

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED` — включая ВСЕ существующие тесты, не только новые (эта задача — самый большой риск регрессии в плане, `computeStageGaps`/сортировка/DNF-логика не должны были измениться, только источник ранговых пулов).

- [ ] **Step 5: Проверить на реальных данных**

Throwaway `deploy/verify_stage.js` — вызвать `renderStage('swim')` под разными фильтрами (`_fmt`/`_gender`), убедиться, что «Абсолют» не меняется при переключении фильтра пола (истинный абсолют — та же цифра для одного и того же участника независимо от `_gender`), под `_fmt='relay'` — 3 колонки, формат-ранг не совпадает случайно с абсолютом (если в реальных данных на этапе есть и мужчины, и женщины в эстафете — их будет больше одного, разница должна быть видна). Удалить скрипт.

- [ ] **Step 6: Commit**

```bash
git add templates/siberman/results.html tests/js/test_siberman_results_merge.js
git commit -m "$(cat <<'EOF'
feat(siberman): вкладки этапов — истинный абсолют + 3 колонки Формат/Пол/Абсолют при "Эстафета" (п.7-8, задача 3/5)

"Абсолют"/"По полу" на этапах раньше считались внутри текущего
getFiltered()-пула — при активном фильтре по полу "Абсолют" был
фактически местом СРЕДИ этого пола, что вводило в заблуждение
(согласовано с пользователем 2026-07-22, исправлено на настоящий
полноростерный ранг, тот же принцип что в Итогах гонки).

При fmt="Эстафета" — новый 3-колоночный режим (Формат/Пол/Абсолют)
вместо обычных двух; личников в этом фильтре нет, поэтому шапка/тело
не конфликтуют.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 4: Свод вело (renderBikeCombined) — formatRanks + 3-колоночный режим

**Files:**
- Modify: `templates/siberman/results.html:929-998` (`renderBikeCombined`)
- Test: `tests/js/test_siberman_results_merge.js`

Зависит от Task 1. Структурно похожа на Task 3, но проще — «Абсолют»/«По полу» УЖЕ считаются по полному ростеру (существующий код), нужно только добавить `formatRanks` и 3-колоночный режим.

- [ ] **Step 1: Написать падающий тест**

```js
check('renderBikeCombined() фильтр "Эстафета" — 3 колонки Формат/Пол/Абсолют, formatRanks по полному ростеру', () => {
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const relay = [
        { bib: '1000', team_name: 'КомандаА', members: [
            { relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 100, cp: {} },
            { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: 5000, bike2_s: 4000, cp: {} },
            { relay_stage: 'run', status: 'active', gender: 'M', run_s: 100, cp: {} },
        ] },
        { bib: '1001', team_name: 'КомандаБ', members: [
            { relay_stage: 'swim', status: 'active', gender: 'F', swim_s: 100, cp: {} },
            { relay_stage: 'bike', status: 'active', gender: 'F', bike1_s: 6000, bike2_s: 5000, cp: {} },
            { relay_stage: 'run', status: 'active', gender: 'F', run_s: 100, cp: {} },
        ] },
    ];
    setRaceData([], relay, Date.now());
    setState('relay', 'all');
    sandbox.renderBikeCombined();
    const html = domGetAppHtml();
    assert.ok(html.includes('<th>Формат</th>') && html.includes('<th>Пол</th>') && html.includes('<th>Абсолют</th>'), `ожидались 3 колонки: ${html.slice(0,600)}`);
    const rowA = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1000<[\s\S]*?<\/tr>/)[0];
    assert.ok(/badge-e">Э<\/span>1/.test(rowA), `КомандаА (9000с) быстрее КомандыБ (11000с) — формат-ранг 1: ${rowA}`);
});
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL`

- [ ] **Step 3: Реализовать**

Найти в `renderBikeCombined()` блок вычисления рангов (после `const allRiders = ...`):

```js
    const allRiders = _data.relay.map(bikeCombinedRelayRider).filter(Boolean);
    const rankPool = [
        ..._data.individual.map(r => ({ key: r.bib, val: r.status === 'active' ? bikeCombinedTime(r) : null, status: r.status, gender: r.gender })),
        ...allRiders.map(r => ({ key: r.bib, val: r.status === 'active' ? bikeCombinedTime(r) : null, status: r.status, gender: r.gender })),
    ];
    const absRanks = computeRanksByValue(rankPool);
    const genderRanks = {
        M: computeRanksByValue(rankPool.filter(x => x.gender === 'M')),
        F: computeRanksByValue(rankPool.filter(x => x.gender === 'F')),
    };
```

Заменить на (добавлен `isRelay` флаг в каждую строку пула + `formatRanks`):

```js
    const allRiders = _data.relay.map(bikeCombinedRelayRider).filter(Boolean);
    const rankPool = [
        ..._data.individual.map(r => ({ key: r.bib, val: r.status === 'active' ? bikeCombinedTime(r) : null, status: r.status, gender: r.gender, isRelay: false })),
        ...allRiders.map(r => ({ key: r.bib, val: r.status === 'active' ? bikeCombinedTime(r) : null, status: r.status, gender: r.gender, isRelay: true })),
    ];
    const absRanks = computeRanksByValue(rankPool);
    const genderRanks = {
        M: computeRanksByValue(rankPool.filter(x => x.gender === 'M')),
        F: computeRanksByValue(rankPool.filter(x => x.gender === 'F')),
    };
    const formatRanks = computeRanksByValue(rankPool.filter(x => x.isRelay));
    const isRelayFilter = _fmt === 'relay';
```

Найти блок рендера таблицы (`html += \`<div class="table-wrap"><table>...\`` в этой же функции) и заменить весь оставшийся блок (от `html += \`<div class="table-wrap">...` до конца функции) на:

```js
    const rankHead = isRelayFilter
        ? '<th>Формат</th><th>Пол</th><th>Абсолют</th>'
        : rankHeaderCells('По полу', _gender !== 'all');
    html += `<div class="table-wrap"><table>
    <thead><tr>${rankHead}<th>№</th><th>Участник</th><th class="r">Время</th><th class="r">Скорость</th><th>Статус</th></tr></thead><tbody>`;
    rows.forEach(({ isRelay, entry, v }) => {
        const hasVal = v != null;
        const absRank = hasVal ? absRanks[entry.bib] : null;
        const genderRank = hasVal ? genderRanks[entry.gender]?.[entry.bib] : null;
        const formatRank = hasVal ? formatRanks[entry.bib] : null;
        const mainRank = isRelayFilter ? formatRank : (_gender === 'all' ? absRank : genderRank);
        const rc = mainRank != null ? rankClass(mainRank) : '';
        const subLine = isRelay ? entry.team_name : entry.city;
        const nameCell = `<span class="name-main">${entry.surname} ${entry.name}</span>${isRelay ? ' <span class="badge badge-relay">Эстафета</span>' : ' <span class="badge badge-individual">Индивидуальный</span>'}${subLine ? `<br><span class="name-city">${subLine}</span>` : ''}`;
        const rankCells = isRelayFilter
            ? `<td><span class="rank-num ${rc}">${formatBadge()}${formatRank ?? '—'}</span></td>` +
              `<td>${genderRank != null ? `<span class="rank-num ${rc}">${genderBadge(entry.gender)}${genderRank}</span>` : '<span class="muted">—</span>'}</td>` +
              `<td><span class="rank-num ${rc}">${absRank ?? '—'}</span></td>`
            : rankBodyCells(absRank, genderRank, genderBadge(entry.gender), rc, _gender !== 'all');
        html += `<tr class="${isRelay ? 'relay-row ' : ''}${rc}${hasVal ? '' : ' dnf'}" style="cursor:pointer" onclick="window.open('${participantLink(entry.bib)}','_blank')">
            ${rankCells}
            <td class="bib-cell">${entry.bib}</td>
            <td>${nameCell}</td>
            <td class="r time-cell">${fmtTime(v)}</td>
            <td class="r muted">${hasVal ? fmtSpeed(421 / (v / 3600)) : '—'}</td>
            <td>${progressStatusBadge(entry.status, hasVal)}</td>
        </tr>`;
    });
    html += '</tbody></table></div>';
    document.getElementById('app').innerHTML = html;
}
```

(Колонка «Пол» как отдельная `<td>${genderBadge(entry.gender)}</td>` и колонка «Формат» текстом — уже были убраны из этого фрагмента; строка `<td>${genderBadge(entry.gender)}</td>` из старой версии — проверить, что она реально удалена, не осталась дублем рядом с новым `rankCells`.)

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED`

- [ ] **Step 5: Проверить на реальных данных**

Throwaway `deploy/verify_bike_combined_table.js` — вызвать `renderBikeCombined()` под `_fmt='relay'`, проверить 3 колонки, сравнить formatRank с ручной сортировкой по `bikeCombinedTime`. Удалить скрипт.

- [ ] **Step 6: Commit**

```bash
git add templates/siberman/results.html tests/js/test_siberman_results_merge.js
git commit -m "$(cat <<'EOF'
feat(siberman): Свод вело — formatRanks + 3 колонки Формат/Пол/Абсолют при "Эстафета" (п.7-8, задача 4/5)

Та же переработка, что и на вкладках этапов (задача 3) — Свод вело
уже считал настоящий пол велосипедиста по полному ростеру (не
менялось), добавлен только formatRanks (место среди только
эстафетчиков) и 3-колоночный режим.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 5: Фильтр по полу на персонифицированных вкладках при «Эстафета» (п.8)

**Files:**
- Modify: `templates/siberman/results.html:1914-1923` (`render()`)
- Test: `tests/js/test_siberman_results_merge.js`

Независима от структуры остальных задач, но логически завершает 3-колоночный UX (без видимого фильтра по полу пользователь не смог бы воспользоваться колонкой «Пол» из задач 3-4). Можно делать в любой момент после Task 1, порядок в этом плане — после 3/4 для целостности тестирования одной фичи целиком.

- [ ] **Step 1: Написать падающий тест**

```js
check('render() — фильтр по полу виден на этапах/Своде вело при fmt=relay, скрыт на Итогах/Днях', () => {
    setRaceData([], [{ bib: '1000', team_name: 'К', overall_s: 1000, members: [] }], Date.now());
    setState('relay', 'all');
    const genderGroupTab = (tab) => {
        vm.runInContext(`_tab = ${JSON.stringify(tab)};`, sandbox);
        sandbox.render();
        return domStub('genderGroup').style.display;
    };
    assert.strictEqual(genderGroupTab('overall'), 'none', 'Итоги гонки — фильтр по полу скрыт при эстафете');
    assert.strictEqual(genderGroupTab('day1'), 'none', 'День 1 — фильтр по полу скрыт при эстафете');
    assert.strictEqual(genderGroupTab('swim'), '', 'Плавание — фильтр по полу ВИДЕН при эстафете');
    vm.runInContext(`_bikeSubTab = 'combined';`, sandbox);
    assert.strictEqual(genderGroupTab('bike'), '', 'Свод вело/Вело1/Вело2 — фильтр по полу ВИДЕН при эстафете');
});
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL` — сейчас фильтр скрыт на ВСЕХ вкладках при `_fmt==='relay'`.

- [ ] **Step 3: Реализовать**

Найти в `render()`:
```js
    const hideGender = _fmt === 'relay';
```

Заменить на:
```js
    // Фильтр по полу скрыт при "Эстафета" на командных вкладках (Итоги/Дни —
    // у команды нет личного пола на этом уровне), но виден на
    // персонифицированных (этапы + Свод вело — там уже настоящий личный пол
    // конкретного эстафетчика, задача 2026-07-22 п.8). "bike" покрывает и
    // Свод, и Вело1/Вело2 (оба сабтаба). График/Старт вело-2 — вне скопа,
    // фильтр там остаётся скрытым при эстафете как раньше.
    const PERSONIFIED_TABS = ['swim', 'run', 'bike'];
    const hideGender = _fmt === 'relay' && !PERSONIFIED_TABS.includes(_tab);
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add templates/siberman/results.html tests/js/test_siberman_results_merge.js
git commit -m "$(cat <<'EOF'
feat(siberman): фильтр по полу виден на этапах/Своде вело при "Эстафета" (п.8, задача 5/5а)

Раньше скрывался везде при fmt='relay' — теперь только на командных
вкладках (Итоги/Дни), где у эстафеты нет личного пола. На
персонифицированных (этапы, Свод вело) уже есть настоящий личный пол
конкретного эстафетчика — фильтр там осмыслен, виден.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 6: Дни (День 1 / День 2) — бейджи + 4 колонки места/отставания (п.9)

**Files:**
- Modify: `templates/siberman/results.html:844-921` (`day1Progress`, `day2Progress`, `buildRankedEntries`, `buildProgressRow`, `renderRankedProgress`)
- Test: `tests/js/test_siberman_results_merge.js`

Зависит от Task 1. Независима от Task 2-5 (другой рендер-путь), но использует тот же `formatBadge()`/`rankBodyCells` фундамент.

- [ ] **Step 1: Написать падающие тесты**

```js
check('renderRankedProgress() (Дни) — 4 колонки: Место(формат/пол)+Отставание + Место(абсолют)+Отставание', () => {
    setState('all', 'all');
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const ind = mkTimerInd('1', { gender: 'M', bike1_s: 5000, swim_s: 1000, cp: { swim: {}, bike_day1: { [maxSeqB1]: 5000 } } });
    setRaceData([ind], [], Date.now());
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    ind.cp.swim = { [maxSeqSwim]: 1000 };
    sandbox.renderDay1();
    const html = domGetAppHtml();
    assert.ok(html.includes('<th>Место</th>') || html.includes('Пол/Формат') || html.includes('По полу'), `ожидалась колонка места: ${html.slice(0,500)}`);
    assert.ok(html.includes('Отставание'), `ожидалась колонка отставания: ${html.slice(0,600)}`);
    assert.ok((html.match(/Абсолют/g) || []).length >= 1, `ожидалась колонка "Абсолют": ${html.slice(0,600)}`);
});
check('buildRankedEntries + gap — отставание внутри пула считается от лидера пула (наименьшее v)', () => {
    setState('all', 'all');
    const rowA = mkTimerInd('1', { gender: 'M', swim_s: 1000, bike1_s: 4000, cp: {} });
    const rowB = mkTimerInd('2', { gender: 'M', swim_s: 1000, bike1_s: 5000, cp: {} });
    setRaceData([rowA, rowB], [], Date.now());
    const gapFor = vm.runInContext('poolGap', sandbox);
    const entries = sandbox.buildRankedEntries([rowA, rowB], [], vm.runInContext('day1Progress', sandbox));
    const gaps = gapFor(entries);
    assert.strictEqual(gaps['1'], 0, `лидер (меньший v) — отставание 0: ${JSON.stringify(gaps)}`);
    assert.strictEqual(gaps['2'], 1000, `отстающий — разница v: ${JSON.stringify(gaps)}`);
});
check('День 1 — Место (абсолют) = ранг среди ВСЕХ участников года (личники+эстафета), не только текущего фильтра', () => {
    setState('individual', 'all');
    const maxSeqB1 = vm.runInContext('STAGE_MAX_SEQ.bike_day1', sandbox);
    const maxSeqSwim = vm.runInContext('STAGE_MAX_SEQ.swim', sandbox);
    const ind = mkTimerInd('1', { swim_s: 5000, bike1_s: 5000, cp: { swim: { [maxSeqSwim]: 5000 }, bike_day1: { [maxSeqB1]: 5000 } } });
    const relayFaster = { bib: '1000', team_name: 'К', members: [
        { relay_stage: 'swim', status: 'active', gender: 'M', swim_s: 100, cp: { swim: { [maxSeqSwim]: 100 } } },
        { relay_stage: 'bike', status: 'active', gender: 'M', bike1_s: 100, bike2_s: null, cp: { bike_day1: { [maxSeqB1]: 100 } } },
        { relay_stage: 'run', status: 'active', gender: 'M', run_s: null, cp: {} },
    ] };
    setRaceData([ind], [relayFaster], Date.now());
    sandbox.renderDay1();
    const html = domGetAppHtml();
    // Личник фильтром "individual" не видит эстафету в строках, но эстафета
    // (быстрее на 9900с) должна "обогнать" его в АБСОЛЮТНОМ ранге — личник
    // должен получить абсолютное место 2, не 1.
    const rowMatch = html.match(/<tr[^>]*>[\s\S]*?bib-cell">1<[\s\S]*?<\/tr>/);
    assert.ok(rowMatch, `строка личника не найдена: ${html}`);
    assert.ok(/2/.test(rowMatch[0].split('Абсолют')[0] || rowMatch[0]), `грубая проверка наличия места 2 где-то в строке (детально см. по коду абсолюта): ${rowMatch[0]}`);
});
```

**Примечание для реализующего:** третий тест — намеренно "грубый" (не парсит точную колонку), т.к. точная HTML-структура определяется в Step 3 и может отличаться в деталях; при реализации уточнить assertion под фактическую разметку, сохранив суть проверки (абсолютное место личника = 2, т.к. эстафета быстрее, даже когда сама эстафета не видна в текущем отфильтрованном списке строк).

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `FAIL` — `poolGap` не существует, колонок «Абсолют»/«Отставание» ещё нет на Днях.

- [ ] **Step 3: Реализовать**

Заменить `templates/siberman/results.html:844-921` (от `function day1Progress` до конца `function renderRankedProgress`) на:

```js
function day1Progress(row) {
    return globalProgress(row, 'bike_day1', STAGE_MAX_SEQ.bike_day1);
}
function day2Progress(row) {
    return globalProgress(row, 'bike_day2', STAGE_MAX_SEQ.bike_day2);
}

// individual: getValue вызывается на самой строке участника (есть .cp,
// .bike1_s и т.д.). relay: getValue вызывается на teamGapRow(team) —
// том же "виртуальном участнике", что и в Итогах/Отставании.
function buildRankedEntries(individual, relay, getValue) {
    const withVal = [
        ...individual.map(r => ({ type: 'individual', entry: r, v: r.status === 'active' ? getValue(r) : null })),
        ...relay.map(t => {
            const tr = teamGapRow(t);
            return { type: 'relay', entry: t, status: tr.status, v: tr.status === 'active' ? getValue(tr) : null };
        }),
    ];
    return withVal.sort((a, b) => {
        if (a.v == null && b.v == null) return 0;
        if (a.v == null) return 1;
        if (b.v == null) return -1;
        return a.v - b.v;
    });
}

// Отставание внутри произвольного пула entries (уже отсортированного по
// возрастанию v, как возвращает buildRankedEntries) — от лидера ЭТОГО пула
// (наименьший v среди финишировавших). Простое вычитание — day1Progress/
// day2Progress уже дают единое сравнимое число (не нужен checkpoint-based
// computeOverallGaps). key — bib участника/команды.
function poolGap(entries) {
    const leader = entries.find(e => e.v != null);
    if (!leader) return {};
    const gaps = {};
    entries.forEach(e => {
        if (e.v != null) gaps[e.entry.bib] = e.v - leader.v;
    });
    return gaps;
}

// Старая функция buildProgressRow() УДАЛЯЕТСЯ целиком (не переносится) —
// вся логика строки теперь инлайнена прямо в renderRankedProgress() ниже
// (в цикле entries.forEach), т.к. ей нужны 4 отдельных значения на строку
// (место+отставание по пулу, место+отставание по абсолюту), а не 2 как
// раньше — выносить в отдельную функцию с 6 параметрами менее читаемо, чем
// один цикл со всеми вычислениями рядом.

function renderRankedProgress(getValue, options = {}) {
    const { individual, relay } = getFiltered();
    let html = buildStats(individual, relay, null);
    const entries = buildRankedEntries(individual, relay, getValue);
    if (entries.length === 0) {
        html += '<div class="empty">Нет данных для выбранного фильтра</div>';
        document.getElementById('app').innerHTML = html;
        return;
    }
    // Пул-отставание — от лидера ТЕКУЩЕГО отфильтрованного пула (согласовано
    // с активными фильтрами, п.9). Абсолютное место/отставание — от лидера
    // ПОЛНОГО ростера года (личники+эстафета вместе), тот же принцип что и
    // в Итогах гонки — считается отдельно, не зависит от текущих фильтров.
    const gaps = poolGap(entries);
    const allEntries = buildRankedEntries(_data.individual, _data.relay, getValue);
    const absRanksAll = computeRanksByValue(allEntries.map(e => ({ key: e.entry.bib, val: e.v, status: e.type === 'individual' ? e.entry.status : e.status })));
    const absGapsAll = poolGap(allEntries);
    html += `<div class="table-wrap"><table>
    <thead><tr><th>Место</th><th class="r">Отставание</th><th>Абсолют</th><th class="r">Отставание (абс.)</th><th>№</th><th>Участник</th><th class="r">Время</th>${options.speedFn ? '<th class="r">Скорость</th>' : ''}<th>Статус</th></tr></thead><tbody>`;
    entries.forEach(item => {
        const { type, entry, v } = item;
        const hasVal = v != null;
        const genderRank = options.genderRanks && type === 'individual' ? options.genderRanks[entry.gender]?.[entry.bib] : null;
        const formatRank = options.formatRanks && type === 'relay' ? options.formatRanks[entry.bib] : null;
        const secondaryRank = type === 'individual' ? genderRank : formatRank;
        const secondaryBadge = type === 'individual' ? genderBadge(entry.gender) : formatBadge();
        const absRank = hasVal ? absRanksAll[entry.bib] : null;
        const mainRank = secondaryRank ?? absRank;
        const rc = mainRank != null ? rankClass(mainRank) : '';
        const status = type === 'individual' ? entry.status : item.status;
        const nameCell = type === 'individual'
            ? `<span class="name-main">${entry.surname} ${entry.name}</span> <span class="badge badge-individual">Индивидуальный</span>${entry.city ? `<br><span class="name-city">${entry.city}</span>` : ''}`
            : `<span class="name-main">${entry.team_name}</span> <span class="badge badge-relay">Эстафета</span>`;
        html += `<tr class="${type === 'relay' ? 'relay-row ' : ''}${rc}${hasVal ? '' : ' dnf'}" style="cursor:pointer" onclick="window.open('${participantLink(entry.bib)}','_blank')">
            <td>${secondaryRank != null ? `<span class="rank-num ${rc}">${secondaryBadge}${secondaryRank}</span>` : '<span class="muted">—</span>'}</td>
            <td class="r muted">${fmtGap(gaps[entry.bib])}</td>
            <td><span class="rank-num ${rc}">${absRank ?? '—'}</span></td>
            <td class="r muted">${fmtGap(absGapsAll[entry.bib])}</td>
            <td class="bib-cell">${entry.bib}</td>
            <td>${nameCell}</td>
            <td class="r time-cell">${fmtTime(v)}</td>
            ${options.speedFn ? `<td class="r muted">${hasVal ? fmtSpeed(options.speedFn(v)) : '—'}</td>` : ''}
            <td>${progressStatusBadge(status, hasVal)}</td>
        </tr>`;
    });
    html += '</tbody></table></div>';
    document.getElementById('app').innerHTML = html;
}
```

Также нужно найти и обновить оба вызова `renderRankedProgress` — `day1`/`day2` не имеют `genderRanks`/`formatRanks` сейчас (`renderDay1() { renderRankedProgress(day1Progress); }`), нужно их добавить:

Найти:
```js
function renderDay1() { renderRankedProgress(day1Progress); }
function renderDay2() { renderRankedProgress(day2Progress); }
```

Заменить на:
```js
// genderRanks/formatRanks — по ПОЛНОМУ ростеру года (не по текущим
// фильтрам), тот же принцип что и абсолют — считаются один раз здесь,
// а не внутри renderRankedProgress (там уже есть похожий "весь ростер"
// расчёт для absRanksAll, но пол/формат нужны ОТДЕЛЬНО от абсолюта).
function dayRankOptions(getValue) {
    const allEntries = buildRankedEntries(_data.individual, _data.relay, getValue);
    const rowsFor = (pred) => allEntries.filter(pred).map(e => ({ key: e.entry.bib, val: e.v, status: e.type === 'individual' ? e.entry.status : e.status }));
    return {
        genderRanks: {
            M: computeRanksByValue(rowsFor(e => e.type === 'individual' && e.entry.gender === 'M')),
            F: computeRanksByValue(rowsFor(e => e.type === 'individual' && e.entry.gender === 'F')),
        },
        formatRanks: computeRanksByValue(rowsFor(e => e.type === 'relay')),
    };
}
function renderDay1() { renderRankedProgress(day1Progress, dayRankOptions(day1Progress)); }
function renderDay2() { renderRankedProgress(day2Progress, dayRankOptions(day2Progress)); }
```

И проверить вызов в `renderBikeCombined()` — **эта функция НЕ использует `renderRankedProgress`/`buildProgressRow`** (у неё свой собственный рендер-код, не трогается этой задачей, уже обновлён в Task 4).

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `node tests/js/test_siberman_results_merge.js`
Expected: `ALL PASSED`. Если какой-то из "грубых" тестов из Step 1 не проходит из-за несовпадения точной HTML-структуры — поправить assertion под фактическую разметку (не менять смысл проверки), затем перезапустить.

- [ ] **Step 5: Проверить на реальных данных**

Throwaway `deploy/verify_days.js` — вызвать `renderDay1()`/`renderDay2()` на реальных данных, проверить: (а) отставание в первой паре колонок = 0 у лидера видимого списка, (б) «Абсолют» + «Отставание (абс.)» стабильны при смене `_fmt`/`_gender` (тот, кто абсолютный лидер года по day1Progress, всегда получает Абсолют=1 и Отставание(абс.)='' независимо от фильтра). Удалить скрипт.

- [ ] **Step 6: Commit**

```bash
git add templates/siberman/results.html tests/js/test_siberman_results_merge.js
git commit -m "$(cat <<'EOF'
feat(siberman): Дни — 4 колонки места+отставания (по пулу и по абсолюту), бейджи (п.9, задача 6/6)

Раньше на Днях не было отставания вообще, а место — либо простая
позиция в списке, либо (при genderRanks) 2-колоночный teamLevel-режим.
Теперь: Место(пол/формат)+Отставание (относительно лидера текущего
отфильтрованного пула) + Место(абсолют)+Отставание(абс.) (относительно
лидера полного ростера года, не зависит от фильтров) — 4 колонки,
согласовано с пользователем как на Итогах гонки. buildProgressRow()
удалена как мёртвый код — логика инлайнена в renderRankedProgress.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 7: Финальная сквозная верификация

**Files:** нет изменений кода — только проверка.

- [ ] **Step 1: Полный прогон тестов**

```bash
node tests/js/test_siberman_results_merge.js
node tests/js/test_siberman_participant.js
conda run -n base python -m pytest tests/unit/ -q
```

Expected: все три `ALL PASSED`/`N passed`, без failures.

- [ ] **Step 2: Сквозная проверка на реальных данных всех 5 вкладок**

Throwaway `deploy/verify_v4_tables_final.js` — загрузить реальный JSON 2025 года, вызвать по очереди `renderOverall()`, `renderStage('swim')`, `renderStage('run')`, `renderBikeCombined()`, `renderDay1()`, `renderDay2()` под комбинациями `_fmt`×`_gender` (`all`×`all`, `individual`×`M`, `relay`×`all`, `relay`×`F` — последняя только там, где фильтр по полу теперь виден), распечатать HTML каждой и глазами проверить: нет колонок «Пол»/«Формат» как раньше, бейджи М1/Ж1/Э1 на местах, строки эстафеты подсвечены, нет JS-исключений. Удалить скрипт.

- [ ] **Step 3: Обновить Obsidian**

Дописать в `C:\Users\podbo\Documents\Obsidian_vaults\KM_Track\00-home\текущие приоритеты.md` (раздел Live v4) — пункты 7-9 закрыты, ссылка на итоговую сессионную заметку (создать `sessions/2026-07-22-siberman-results-tables-v4.md` с кратким резюме: что сделано, найденная и исправленная архитектурная непоследовательность «Абсолют» на этапах, финальный список коммитов).

- [ ] **Step 4: Финальный отчёт пользователю**

Не коммит — просто резюме в чате: что сделано по каждому пункту 7-9, какие тесты прошли, что проверено на реальных данных, какие коммиты запушены, статус деплоя (через тот же паттерн GitHub Actions API + опциональная SSH-проверка, что уже устоялся в этой сессии).

---

## Self-Review (проведён при написании плана)

**1. Покрытие спеки:**
- Часть 1 (общий бейдж) → Task 1
- Часть 2 (Итоги/Дни, 2 колонки, подсветка, бейджи) → Task 2 (Итоги) + Task 6 (Дни)
- Часть 3 (этапы+Свод вело, unchanged под все/личный, 3 колонки под эстафета, фильтр по полу) → Task 3 (этапы) + Task 4 (Свод вело) + Task 5 (фильтр)
- Часть 4 (Дни — 4 колонки места+отставания) → Task 6
- Намеренная асимметрия с Итогами (только 1 колонка отставания там) — Task 2 НЕ трогает существующую единственную колонку «Отставание» Итогов, подтверждено явно в шаге 3 (заменяется только состав rank-колонок, `<td class="r muted">${fmtGap(overallGaps[...])}</td>` остаётся как было)
- Истинный абсолют на этапах (решение пользователя в диалоге) → Task 3, Step 3 (`allStageRows` вместо `stageRankRows` на getFiltered())

**2. Плейсхолдеры:** просканировано — при первом черновике Task 6 был случайно оставлен нерабочий `.replace()`-хак в устаревшей версии `buildProgressRow`; функция удалена из плана целиком (логика инлайнена в `renderRankedProgress`), артефакт не воспроизводится. Остальной код — конкретный, без TBD.

**3. Согласованность типов/сигнатур:**
- `formatBadge()` — 0 аргументов, используется одинаково в Task 2/3/4/6.
- `rankHeaderCells(secondaryLabel, swapped)` / `rankBodyCells(rankAbs, rankSecondary, secondaryBadge, rc, swapped)` — сигнатура из Task 1 используется идентично в Task 2 (`overallSecondaryLabel()`/`overallRankSwapped()`), Task 3 (инлайн `_gender==='all' ? 'По полу' : ...` — ПОПРАВЛЕНО в тексте задачи на константу `'По полу'`, см. примечание в Task 3 Step 3), Task 4 (аналогично).
- `computeRanksByValue(rows)` — сигнатура `{key, val, status}` не менялась, используется как есть везде (siberman-common.js, не трогается).
- `poolGap(entries)` — новая функция Task 6, используется только там.
- `.relay-row` CSS-класс — добавлен в Task 1, используется в Task 2/3/4/6 на `<tr>` эстафетных строк одинаково (`class="relay-row ${rc}..."`).
