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

check('Заголовок КТ без distanceLabel — "Отметка N км" с числом из label', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'female');
    assert.ok(text.startsWith('**Женщины. Отметка 10.55 км**'), text);
});

check('Заголовок КТ с distanceLabel — "Отметка N/M км"', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'male', '21.1 км');
    assert.ok(text.startsWith('**Мужчины. Отметка 10.55/21.1 км**'), text);
});

check('Заголовок Финиш — "Финиш" без "Отметка"', () => {
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

check('4 записи — 4-я не попадает в пост, первые 3 попадают', () => {
    const cp = {
        code: 'kt1', label: 'КТ1 (10.55 км)',
        top10_male: [
            { surname: 'Иванов', name: 'Пётр', time: '00:45:00', pace: '4:30', gap_sex: 'Лидер' },
            { surname: 'Сидоров', name: 'Олег', time: '00:50:30', pace: '5:03', gap_sex: '+05:30' },
            { surname: 'Кузнецов', name: 'Илья', time: '00:52:00', pace: '5:12', gap_sex: '+07:00' },
            { surname: 'Смирнов', name: 'Артём', time: '00:55:00', pace: '5:30', gap_sex: '+10:00' },
        ],
        top10_female: [],
    };
    const text = sandbox.buildTop3Post(cp, 'male');
    assert.ok(text.includes('1. Иванов Пётр'), text);
    assert.ok(text.includes('2. Сидоров Олег'), text);
    assert.ok(text.includes('3. Кузнецов Илья'), text);
    assert.ok(!text.includes('Смирнов'), text);
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
    assert.ok(text.includes('**Мужчины. Отметка 10.55 км**'));
    assert.ok(text.includes('__👉 ссылка на лайв-результаты: results.krasmarafon.ru/results__'));
});

check('21.1 км, мужчины — строка рекорда трассы (с темпом) после топ-3, перед ссылкой', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'male', '21.1 км');
    const recordIdx = text.indexOf('🏆 Рекорд дистанции: 1:03:03, Чертыков Денис (2024), 2:59 мин/км');
    const linkIdx = text.indexOf('👉 ссылка на лайв-результаты');
    assert.ok(recordIdx > -1, text);
    assert.ok(recordIdx > text.indexOf('2. Сидоров Олег'), text);
    assert.ok(recordIdx < linkIdx, text);
});

check('21.1 км, женщины — свой рекорд трассы (с темпом)', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'female', '21.1 км');
    assert.ok(text.includes('🏆 Рекорд дистанции: 1:13:04, Викулова Анна (2024), 3:28 мин/км'), text);
});

check('5 км — строка рекорда не добавляется (рекорд задан только для 21.1 км)', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'male', '5 км');
    assert.ok(!text.includes('Рекорд дистанции'), text);
});

check('distanceLabel не передан — строка рекорда не добавляется (обратная совместимость)', () => {
    const text = sandbox.buildTop3Post(CP_KT, 'male');
    assert.ok(!text.includes('Рекорд дистанции'), text);
});

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
        set innerHTML(v) {
            // Наивная симуляция парсинга: реальный DOM создаёт дочерний
            // <option> из '<option value="">...</option>', сброшенный
            // innerHTML в stub'е не парсил разметку — из-за этого select
            // терял плейсхолдер-опцию. Здесь заменяем очистку одним
            // синтетическим OPTION-узлом, если строка непустая.
            children.length = 0;
            if (v) children.push({ tagName: 'OPTION', value: '', textContent: '' });
        },
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

// Один общий файл на обе дистанции (5км/21.1км никогда не работают
// одновременно — см. комментарий у BCP_JSON_URLS в исходнике).
const BCP_TEST_URL = '/live/zhara_top10.json';
const domSandbox = {
    console,
    fetch: (url) => {
        if (url === BCP_TEST_URL) {
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

    check('bcpGenerate("female") заполняет textarea готовым текстом (с distanceLabel из select)', () => {
        const text = domStub2('bcp-output-female').value;
        assert.ok(text.startsWith('**Женщины. Отметка 10.55/5 км**'), text);
    });

    console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
    process.exit(failures === 0 ? 0 : 1);
})();
