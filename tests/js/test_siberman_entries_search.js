// Поиск заявок по фамилии и имени (админка и публичный список). Запуск: node tests/js/test_siberman_entries_search.js
const assert = require('assert');
const { entryMatches } = require('../../static/js/siberman-entries-search.js');

assert.ok(entryMatches('Ёлкина Мария', 'елк'));             // ё = е, без регистра
assert.ok(entryMatches('Ёлкина Мария', 'мария ёлкина'));    // любой порядок слов
assert.ok(entryMatches('Ёлкина Мария', 'мар ел'));          // начала слов
assert.ok(entryMatches('Ёлкина Мария', '  '));              // пустой запрос — всё
assert.ok(!entryMatches('Ёлкина Мария', 'ина'));            // не середина слова
assert.ok(!entryMatches('Ёлкина Мария', 'елкина анна'));
console.log('ok');
