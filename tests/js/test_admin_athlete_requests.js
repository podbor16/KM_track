// Чистые функции вкладки «Обращения» (static/js/admin-athlete-requests.js)
// Запуск: node tests/js/test_admin_athlete_requests.js
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const src = fs.readFileSync(path.join(__dirname, '../../static/js/admin-athlete-requests.js'), 'utf-8');
const ctx = { console, document: { getElementById() { return null; } }, fetch() {} };
vm.createContext(ctx); vm.runInContext(src, ctx);
const T = ctx.arTest;
const plain = v => JSON.parse(JSON.stringify(v));

// тип — человеческим текстом
assert.strictEqual(T.kindLabel('dispute'), 'Спор: «это моя карточка»');
assert.strictEqual(T.kindLabel('wrong_row'), 'Это не мой забег');
assert.strictEqual(T.kindLabel('not_found'), 'Не могу найти себя');
assert.strictEqual(T.kindLabel('zzz'), 'zzz');

// кнопки по типу
assert.deepStrictEqual(plain(T.actionsFor('dispute')), ['transfer', 'reject']);
assert.deepStrictEqual(plain(T.actionsFor('wrong_row')), ['close']);
assert.deepStrictEqual(plain(T.actionsFor('not_found')), ['close', 'attach']);

// введённые данные not_found: понятные подписи, неизвестные ключи не теряются, пустые пропускаются
assert.deepStrictEqual(plain(T.payloadLines({surname: 'Иванов', name: 'Иван', birthday: '1986-05-01', bib: 77, x: 'y', empty: ''})),
    ['Фамилия: Иванов', 'Имя: Иван', 'Дата рождения: 1986-05-01', 'Номер: 77', 'x: y']);
assert.deepStrictEqual(plain(T.payloadLines(null)), []);

// строка wrong_row
assert.strictEqual(T.rowLabel('results', 12), 'Результат №12');
assert.strictEqual(T.rowLabel('leads', 5), 'Заявка №5');
assert.strictEqual(T.rowLabel(null, null), '');

// решение закрытого обращения
assert.strictEqual(T.resolutionLabel('transfer'), 'Передано заявителю');
assert.strictEqual(T.resolutionLabel('attach'), 'Карточка привязана');
assert.strictEqual(T.resolutionLabel('reject'), 'Отклонено');
assert.strictEqual(T.resolutionLabel('close'), 'Закрыто');

// ошибки API — понятным текстом
assert.ok(T.errorText('taken').includes('уже'));
assert.strictEqual(T.errorText('unknown_code'), 'Ошибка: unknown_code');
console.log('ok');
