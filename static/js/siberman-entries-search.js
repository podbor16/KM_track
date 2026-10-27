'use strict';
// Поиск заявок Siberman по фамилии и имени: без регистра, ё = е, слова запроса — начала слов ФИ в любом порядке.

function entryNorm(s) { return String(s ?? '').toLowerCase().replace(/ё/g, 'е').trim(); }

function entryMatches(fio, query) {
  const words = entryNorm(fio).split(/\s+/);
  return entryNorm(query).split(/\s+/).filter(Boolean).every(q => words.some(w => w.startsWith(q)));
}

if (typeof module !== 'undefined') module.exports = { entryNorm, entryMatches };
