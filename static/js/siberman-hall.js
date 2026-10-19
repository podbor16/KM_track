'use strict';
// Общие помощники блоков Siberman (рейтинг, рекорды, статистика, география, страница спортсмена): экранирование, время,
// ссылки, загрузка API и высота содержимого для страницы Тильды (docs/siberman/hall-tilda-snippet.md).

function hallEsc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function hallTime(s) {
  if (s == null) return '—';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}`;
}

function hallNorm(s) { return String(s ?? '').toLowerCase().replace(/ё/g, 'е'); }

function hallPlural(n, one, few, many) {
  const a = n % 10, b = n % 100;
  return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many;
}

const HALL_STAGE = { swim: 'плавание', bike: 'велосипед', run: 'бег', bike_day1: 'вело, 1 день', bike_day2: 'вело, 2 день' };

// Ссылки из iframe — в новой вкладке: страница Тильды остаётся на месте.
function hallLink(href, html) { return `<a href="${href}" target="_blank" rel="noopener">${html}</a>`; }
// Страница спортсмена — по slug (личный стартовый номер или r{id}), его добавляет сервер к записям с person_id.
function hallAthlete(slug, html) { return slug ? hallLink(`/athlete/${encodeURIComponent(slug)}`, html) : html; }
function hallCard(bib, year, html) { return hallLink(`/participant/${encodeURIComponent(bib)}?year=${year}`, html); }

async function hallLoad(path) {
  const r = await fetch(path, { cache: 'no-store' });
  if (!r.ok) throw new Error(r.status === 503 ? 'Данные временно недоступны — обновите страницу через минуту' : 'Не удалось загрузить данные');
  return r.json();
}

(function () {
  if (window.parent === window) return;
  // documentElement.scrollHeight не меньше окна iframe — iframe не сжимался бы; меряем сам блок
  const box = () => document.querySelector('.hall') || document.body;
  const send = () => window.parent.postMessage({ sibermanHallHeight: Math.ceil(box().getBoundingClientRect().height) + 8 }, '*');
  window.addEventListener('load', () => { new ResizeObserver(send).observe(box()); send(); });
  setInterval(send, 2000); // скрипт-слушатель Тильды может подключиться позже iframe
})();
