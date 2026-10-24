'use strict';
// Оверлей жеребьёвки для vMix (мужчины, женщины, эстафеты, wild card): строки страницы (?page=1 — 1–20,
// 2 — 21–40) по макету, подпись разделов слева («… Победители» / «Лист ожидания»), только что вытянутый — подсвечен.
// Данные — /api/siberman/draw/{год}/overlay/{name} раз в 2 с.

const ov = document.getElementById('ov');
const API = `/api/siberman/draw/${ov.dataset.year}/overlay/${ov.dataset.name}`;
const PAGE = Math.max(1, +ov.dataset.page || 1), PER_PAGE = 20, TOP = 85, STEP = 47, H = 41;
const SECTION = { winner: 'Победители', waitlist: 'Лист ожидания', wildcard: '' };
let shown = null;   // имена на экране: номер → ФИ (null — первая отрисовка без подсветки)

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function labels(rows, title) {
  // подряд идущие строки одного раздела — одна плашка; полный текст с названием зачёта — у первой плашки
  // страницы, где он помещается (у женщин 6 мест — название уходит на лист ожидания, как в макете)
  const out = [];
  rows.forEach((r, i) => {
    const last = out[out.length - 1];
    if (last && last.section === r.section) last.end = i;
    else out.push({ section: r.section, start: i, end: i });
  });
  const long = { winner: ov.dataset.name === 'relay' ? 'Победители' : 'Победители жеребьёвки', waitlist: 'Лист ожидания' };
  return out.map(b => {
    const full = b.section === 'wildcard' ? title : `${title}. ${long[b.section]}`;
    const top = TOP + b.start * STEP, height = (b.end - b.start) * STEP + H;
    return `<div class="ov-label ${b.section}" style="top:${top}px;height:${height}px" data-full="${esc(full)}"
      data-short="${esc(SECTION[b.section] || title)}"><span></span></div>`;
  }).join('');
}

function fitLabels() {
  let titled = false;
  document.querySelectorAll('.ov-label').forEach(el => {
    const span = el.firstElementChild;
    span.textContent = el.dataset.full;
    if (!titled && span.offsetWidth <= el.offsetHeight - 14) titled = true;   // 10 px сверху + запас
    else span.textContent = el.dataset.short;
  });
}

function render(data) {
  const rows = data.rows.slice((PAGE - 1) * PER_PAGE, PAGE * PER_PAGE);
  const fresh = new Set(shown ? rows.filter(r => r.name && shown[r.num] !== r.name).map(r => r.num) : []);
  document.getElementById('body').innerHTML = labels(rows, data.label) + rows.map((r, i) => {
    const top = TOP + i * STEP;
    return `<div class="ov-row${fresh.has(r.num) ? ' fresh' : ''}">
      <div class="ov-num" style="top:${top}px">${r.num}</div>
      <div class="ov-name" style="top:${top}px">${esc(r.name)}</div></div>`;
  }).join('');
  fitLabels();
  shown = Object.fromEntries(rows.map(r => [r.num, r.name]));
}

async function poll() {
  try {
    const r = await fetch(API, { cache: 'no-store' });
    if (r.ok) render(await r.json());
  } catch (e) { /* сеть моргнула — оставляем прошлую картинку */ }
  setTimeout(poll, 2000);
}
document.fonts.ready.then(poll);   // ширину подписей меряем уже в Onest
