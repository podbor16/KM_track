'use strict';
// Блок «Рекорды» (/hall/records): таблица как у организаторов (вариант А), на телефоне — карточки;
// клик по ФИ / команде — переход, по остальной клетке — история рекорда во всплывающем окне рядом
// с клеткой (в iframe окно по центру всей высоты могло бы оказаться вне экрана).

const SEGS = [['race', 'Гонка 515'], ['swim', 'Плавание 10'], ['bike', 'Вело 421'],
              ['bike1', 'Вело, 1 день'], ['bike2', 'Вело, 2 день'], ['run', 'Бег 84']];
const COLS = [['individual', 'Личный зачёт'], ['relay', 'Эстафета'], ['absolute', 'Абсолютно лучшее время']];
const COL_TITLE = { individual: 'личный зачёт', relay: 'эстафета', absolute: 'абсолютно лучшее' };
let data = null;

function holderHtml(rec, key) {
  const h = rec.holder, col = key.split(':')[1];
  if (h.type === 'team') {
    return hallCard(h.bib, h.year, `<b>${h.name ? '«' + hallEsc(h.name) + '»' : 'Команда №' + hallEsc(h.bib)}</b>`);
  }
  const who = hallAthlete(h.slug, hallEsc(h.fio));
  if (!h.team) return who;
  const team = hallCard(h.bib, h.year, '«' + hallEsc(h.team) + '»');
  return col === 'absolute' ? `${who}<div class="team">эстафета<br>${team}</div>` : `${who}<div class="team">${team}</div>`;
}

function body(key) {
  const rec = data.current[key];
  if (!rec) return '<div class="yr">—</div>';
  return `<div class="t">${hallTime(rec.time_s)}</div>${holderHtml(rec, key)}
    <div class="yr">${rec.year}${rec.new ? ' <span class="new">НОВЫЙ</span>' : ''}</div>`;
}

function renderTable() {
  let h = '<tr><th rowspan="2"></th>' + COLS.map(c => `<th colspan="2">${c[1]}</th>`).join('') + '</tr><tr>'
        + COLS.map(() => '<th class="m">Мужчины</th><th class="f">Женщины</th>').join('') + '</tr>';
  for (const [seg, label] of SEGS) {
    h += `<tr><td class="row">${label}</td>`;
    for (const [col] of COLS) {
      if (seg === 'race' && col !== 'individual') {     // эстафета и абсолют гонки — без деления по полу
        h += `<td class="x" colspan="2" data-cell="race:${col}:X" tabindex="0" role="button">${body(`race:${col}:X`)}</td>`;
      } else {
        h += `<td class="m" data-cell="${seg}:${col}:M" tabindex="0" role="button">${body(`${seg}:${col}:M`)}</td>`
           + `<td class="f" data-cell="${seg}:${col}:F" tabindex="0" role="button">${body(`${seg}:${col}:F`)}</td>`;
      }
    }
    h += '</tr>';
  }
  document.getElementById('table').innerHTML = h;
}

function card(key, title, cls, wide) {
  return `<div class="card2 ${cls}" data-cell="${key}" tabindex="0" role="button"${wide ? ' style="grid-column: span 2"' : ''}><b class="lbl2">${title}</b>${body(key)}</div>`;
}

function renderCards() {
  document.getElementById('cards').innerHTML = SEGS.map(([seg, label]) => {
    const pair = (col, title) => seg === 'race'
      ? card(`race:${col}:X`, title, 'x', true)
      : card(`${seg}:${col}:M`, `${title} · М`, 'm') + card(`${seg}:${col}:F`, `${title} · Ж`, 'f');
    return `<div class="rowt">${label}</div><div class="cards">`
      + card(`${seg}:individual:M`, 'Личный · М', 'm') + card(`${seg}:individual:F`, 'Личный · Ж', 'f')
      + pair('relay', 'Эстафета') + pair('absolute', 'Абсолют') + '</div>';
  }).join('');
}

function cellTitle(key) {
  const [seg, col, g] = key.split(':');
  return `${SEGS.find(s => s[0] === seg)[1]} · ${COL_TITLE[col]}${g === 'M' ? ' · мужчины' : g === 'F' ? ' · женщины' : ''}`;
}

const pop = document.getElementById('pop'), hall = document.querySelector('.hall');
let popSeq = 0, popFrom = null;                      // номер последнего открытия; клетка, куда вернуть фокус

function place(anchor) {
  const a = anchor.getBoundingClientRect(), b = hall.getBoundingClientRect();
  pop.style.top = `${a.bottom - b.top + 6}px`;
  hall.style.minHeight = '';
  const need = pop.offsetTop + pop.offsetHeight + 16;   // окно не должно выходить за iframe
  if (need > hall.offsetHeight) hall.style.minHeight = `${need}px`;
}

function closePop() {
  if (pop.hidden) return;
  popSeq++;
  pop.hidden = true;
  hall.style.minHeight = '';
  if (popFrom) popFrom.focus();
  popFrom = null;
}

async function openHistory(key, anchor) {
  const seq = ++popSeq;
  popFrom = anchor;
  pop.innerHTML = `<button type="button" class="close" data-close aria-label="Закрыть">×</button>
    <h4 id="pop-title">История рекорда</h4><div class="team">${hallEsc(cellTitle(key))}</div>
    <div class="state-msg" id="pop-body">Загрузка…</div>`;
  pop.hidden = false;
  place(anchor);
  pop.querySelector('.close').focus();
  try {
    const list = await hallLoad(`/api/siberman/hall/records/history?cell=${encodeURIComponent(key)}`);
    if (seq !== popSeq) return;                      // открыли другую клетку или закрыли окно
    const rows = list.slice().reverse().map((e, i) => `<tr><td><b>${hallTime(e.time_s)}</b></td><td>${holderHtml(e, key)}</td>
      <td>${e.year}</td><td class="gain">${e.delta_s ? '−' + hallTime(e.delta_s) : ''}</td>
      <td class="team">${i === 0 ? 'текущий' : e.delta_s == null ? 'первый' : ''}</td></tr>`).join('');
    document.getElementById('pop-body').outerHTML = `<table>${rows}</table>`;
  } catch (err) {
    if (seq !== popSeq) return;
    document.getElementById('pop-body').textContent = err.message;
  }
  place(anchor);
}

document.addEventListener('click', e => {
  if (e.target.closest('[data-close]')) return closePop();
  if (e.target.closest('a')) return;                       // ФИ / команда — обычный переход
  const cell = e.target.closest('[data-cell]');
  if (cell && !pop.contains(cell)) return openHistory(cell.dataset.cell, cell);
  if (!pop.contains(e.target)) closePop();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') return closePop();
  const cell = (e.key === 'Enter' || e.key === ' ') && e.target.closest && e.target.closest('[data-cell]');
  if (cell && e.target === cell) { e.preventDefault(); openHistory(cell.dataset.cell, cell); }
});

hallLoad('/api/siberman/hall/records').then(d => { data = d; renderTable(); renderCards(); })
  .catch(err => { document.getElementById('table').innerHTML = `<tr><td class="state-msg">${hallEsc(err.message)}</td></tr>`; });
