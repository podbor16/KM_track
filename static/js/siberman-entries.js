'use strict';
// Публичный список заявок Siberman (/entries/{год}): по алфавиту, поиск по ФИ (номера — из полного списка),
// обновление раз в минуту; высоту iframe сообщает siberman-hall.js.

const root = document.getElementById('entries');
const API = `/api/siberman/entries/${root.dataset.year}`;
const EMOJI = { admitted: '✅', rejected: '❌', review: '⌛️', withdrawn: '🚫' };
let data = null;

function render() {
  const q = document.getElementById('q').value;
  const rows = data.entries.filter(e => entryMatches(e.fio, q));
  document.getElementById('rows').innerHTML = rows.map(e =>
    `<tr><td class="n">${e.n}</td><td>${hallEsc(e.fio)}</td><td>${hallEsc(e.format)}</td><td class="st">${EMOJI[e.status] || ''}</td></tr>`
  ).join('') || `<tr><td colspan="4" class="msg">${data.total ? 'Никого не нашли' : 'Заявок пока нет'}</td></tr>`;
  document.getElementById('counts').textContent = `Заявок: ${data.total}, допущено: ${data.admitted}`;
}

async function load() {
  try {
    data = await hallLoad(API);
    render();
  } catch (err) {
    if (!data) document.getElementById('rows').innerHTML = `<tr><td colspan="4" class="msg">${hallEsc(err.message)}</td></tr>`;
  }
}

document.getElementById('q').addEventListener('input', () => data && render());
load();
setInterval(load, 60000);
