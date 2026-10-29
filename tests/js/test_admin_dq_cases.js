// Чистые функции экрана дел «Качества данных» (static/js/admin-dq-cases.js)
// Запуск: node tests/js/test_admin_dq_cases.js
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const src = fs.readFileSync(path.join(__dirname, '../../static/js/admin-dq-cases.js'), 'utf-8');
const ctx = { console, document: { addEventListener() {}, getElementById() { return null; } }, window: {},
              localStorage: { getItem() { return null; }, setItem() {} }, setTimeout, clearTimeout };
vm.createContext(ctx); vm.runInContext(src, ctx);
const T = ctx.dqcTest;
// объекты из vm-контекста — с чужими прототипами; deepStrictEqual сравнивает и их
const plain = v => JSON.parse(JSON.stringify(v));

// экранирование
assert.strictEqual(T.esc('<b a="1">&\''), '&lt;b a=&quot;1&quot;&gt;&amp;&#39;');

// категории по полу: свой пол и «любой» (sex = '')
const cats = [{label: 'Ж12-13', sex: 'Женщина'}, {label: 'М12-13', sex: 'Мужчина'}, {label: 'Абсолют', sex: ''}];
assert.deepStrictEqual(plain(T.categoriesFor(cats, 'Мужчина')), ['М12-13', 'Абсолют']);

// тело ответа: inputs выбранного ответа, только непустые; extra_cards
const q = {id: 'R-CAT:r5:1', answers: [{id: 'sex', inputs: [{name: 'sex'}, {name: 'category'}]}, {id: 'keep', inputs: []}]};
assert.deepStrictEqual(plain(T.answerBody(q, 'sex', {sex: 'Женщина', category: 'Ж12-13', birthday: ''}, [7])),
    {question_id: 'R-CAT:r5:1', answer_id: 'sex', inputs: {sex: 'Женщина', category: 'Ж12-13'}, extra_cards: [7]});

// ответ по умолчанию — рекомендованный, иначе первый
assert.strictEqual(T.defaultAnswer({answers: [{id: 'a'}, {id: 'b', recommended: true}]}), 'b');
assert.strictEqual(T.defaultAnswer({answers: [{id: 'a'}, {id: 'b'}]}), 'a');

// разметка вопроса: нет кода находки, есть радиокнопки, закрытый вопрос без кнопки «Применить»
const html = T.questionHtml({id: 'R-FOREIGN:r1:1-2', code: 'R-FOREIGN', stage: 1, state: 'current', text: 'Чей <это> результат?',
    hint: '', answers: [{id: 'to:2', label: 'Пцарев Саша', recommended: true, inputs: []}, {id: 'postpone', label: 'Не знаю', inputs: []}]}, 0);
assert.ok(html.includes('Чей &lt;это&gt; результат?') && !html.includes('R-FOREIGN') && html.includes('type="radio"'));
assert.ok(!T.questionHtml({id: 'x', code: 'R-CAT', stage: 3, state: 'locked', text: 't', hint: '', answers: []}, 1).includes('Применить'));

// строки карточки: проблемная подсвечена, номер карточки не показан
const card = T.cardHtml({id: 1, surname: 'Пцарев', name: 'Александр', birthday: '1980-03-09',
    rows: [{table: 'results', id: 9, year: 2016, event: 'Детский забег 1.0 2016', start_number: 1012, category: 'М', status: 'Finished', problem: true}]});
assert.ok(card.includes('dqc-row--problem') && card.includes('№1012'));
assert.ok(!card.includes('#1'));

console.log('ALL PASSED');
