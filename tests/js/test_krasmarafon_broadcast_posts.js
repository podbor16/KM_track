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
