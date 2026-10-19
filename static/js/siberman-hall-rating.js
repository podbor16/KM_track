'use strict';
// Блок «Рейтинг» (/hall/rating): вкладки, «лучший на человека», год, поиск; места — внутри выборки
// (год и режим), поиск только находит строки и места не меняет. Данные — /api/siberman/hall/rating.

let data = null, tab = 'abs', mode = 'all', year = '', query = '';
const table = document.getElementById('table');
const DNF_STAGE = { swim: 'плавание', bike_day1: 'вело, 1 день', bike_day2: 'вело, 2 день', run: 'бег' };

function personKey(r) { return r.person_id ? 'p' + r.person_id : 'n' + hallNorm(`${r.surname} ${r.name}`); }
function fio(r) { return hallEsc(`${r.surname} ${r.name}`); }
function outcome(r) { return r.status === 'dsq' ? 'DSQ' : 'DNF' + (r.dnf_stage ? ` (${DNF_STAGE[r.dnf_stage] || hallEsc(r.dnf_stage)})` : ''); }

function matches(names, bib) {
  const q = hallNorm(query.trim());
  if (!q) return true;
  if (/^\d+$/.test(q)) return String(bib) === q;
  return names.some(n => hallNorm(n).includes(q));
}

function rank(fin) {
  fin.sort((a, b) => a.time_s - b.time_s || a.year - b.year);
  fin.forEach((r, i) => { r.place = i + 1; });
}

function pickIndividual() {
  const g = tab === 'men' ? 'M' : tab === 'women' ? 'F' : null;
  const rows = data.individual.filter(r => (!g || r.gender === g) && (!year || String(r.year) === year));
  let fin = rows.filter(r => r.status === 'finished'), out = rows.filter(r => r.status !== 'finished');
  if (mode === 'best') {
    const best = new Map();
    fin.forEach(r => { const k = personKey(r), b = best.get(k); if (!b || r.time_s < b.time_s) best.set(k, r); });
    fin = [...best.values()];
    const done = new Set(fin.map(personKey)), last = new Map();
    out.forEach(r => { const k = personKey(r); if (!done.has(k) && (!last.has(k) || r.year > last.get(k).year)) last.set(k, r); });
    out = [...last.values()];
  }
  rank(fin);
  out.sort((a, b) => b.year - a.year);
  return { fin, out };
}

function renderIndividual() {
  const { fin, out } = pickIndividual(), abs = tab === 'abs', cols = abs ? 8 : 7;
  const sex = r => abs ? `<td><span class="sx ${r.gender === 'F' ? 'f' : 'm'}">${r.gender === 'F' ? 'Ж' : 'М'}</span></td>` : '';
  const rec = r => r.record ? `<span class="rec">${abs && r.record === 'F' ? 'рекорд Ж' : 'рекорд'}</span>` : '';
  const medal = r => r.medal ? `<span class="dot" style="background:${r.medal.color}" title="${hallEsc(r.medal.name)}"></span>` : '';
  const found = r => matches([`${r.surname} ${r.name}`], r.bib);
  const row = r => `<tr><td>${r.place}</td><td class="num">${hallEsc(r.bib)}</td>
    <td class="l">${hallAthlete(r.person_id, fio(r))}${rec(r)}</td>${sex(r)}<td class="city">${hallEsc(r.city)}</td>
    <td>${hallCard(r.bib, r.year, '<b>' + hallTime(r.time_s) + '</b>')}</td><td>${r.year}</td><td>${medal(r)}${r.finish_no}</td></tr>`;
  const dnf = r => `<tr class="dnf"><td>—</td><td class="num">${hallEsc(r.bib)}</td>
    <td class="l">${hallAthlete(r.person_id, fio(r))}</td>${sex(r)}<td class="city">${hallEsc(r.city)}</td>
    <td>${hallCard(r.bib, r.year, outcome(r))}</td><td>${r.year}</td><td></td></tr>`;
  const f = fin.filter(found), o = out.filter(found);
  let html = `<tr><th>Место</th><th class="num">№</th><th class="l">Участник</th>${abs ? '<th>Пол</th>' : ''}
    <th class="city">Город</th><th>Время</th><th>Год</th><th>Финиш №</th></tr>`;
  html += f.map(row).join('') || `<tr><td colspan="${cols}" class="state-msg">Никого не нашлось</td></tr>`;
  if (o.length) html += `<tr class="sec"><td colspan="${cols}">Не финишировали</td></tr>` + o.map(dnf).join('');
  table.innerHTML = html;
}

function memberLine(m) {
  return `<span class="lbl">${HALL_STAGE[m.stage] || ''}</span>${hallAthlete(m.person_id, hallEsc(`${m.surname} ${m.name}`))}`;
}

function renderRelay() {
  const rows = data.relay.filter(r => !year || String(r.year) === year);
  const fin = rows.filter(r => r.status === 'finished'), out = rows.filter(r => r.status !== 'finished');
  rank(fin);
  out.sort((a, b) => b.year - a.year);
  const found = r => matches([r.team, ...r.members.map(m => `${m.surname} ${m.name}`)], r.bib);
  const name = r => hallCard(r.bib, r.year, `<b>${r.team ? '«' + hallEsc(r.team) + '»' : 'Команда №' + hallEsc(r.bib)}</b>`);
  const rec = r => r.record ? '<span class="rec">рекорд</span>' : '';
  const row = r => `<tr><td>${r.place}</td><td class="num">${hallEsc(r.bib)}</td><td class="l">${name(r)}${rec(r)}</td>
    <td class="stage">${r.members.map(memberLine).join('<br>')}</td>
    <td>${hallCard(r.bib, r.year, '<b>' + hallTime(r.time_s) + '</b>')}</td><td>${r.year}</td></tr>`;
  const dnf = r => `<tr class="dnf"><td>—</td><td class="num">${hallEsc(r.bib)}</td><td class="l">${name(r)}</td>
    <td class="stage">${r.members.map(memberLine).join('<br>')}</td><td>${r.status === 'dsq' ? 'DSQ' : 'DNF'}</td><td>${r.year}</td></tr>`;
  const f = fin.filter(found), o = out.filter(found);
  let html = '<tr><th>Место</th><th class="num">№</th><th class="l">Команда</th><th class="l">Состав</th><th>Время</th><th>Год</th></tr>';
  html += f.map(row).join('') || '<tr><td colspan="6" class="state-msg">Никого не нашлось</td></tr>';
  if (o.length) html += '<tr class="sec"><td colspan="6">Не финишировали</td></tr>' + o.map(dnf).join('');
  table.innerHTML = html;
}

function render() {
  if (!data) return;
  document.getElementById('mode').style.display = tab === 'relay' ? 'none' : '';
  document.getElementById('q').placeholder = tab === 'relay' ? 'Поиск по команде, фамилии или номеру…' : 'Поиск по фамилии или номеру…';
  if (tab === 'relay') renderRelay(); else renderIndividual();
}

document.getElementById('tabs').addEventListener('click', e => {
  const b = e.target.closest('.tab');
  if (!b) return;
  tab = b.dataset.tab;
  document.querySelectorAll('#tabs .tab').forEach(x => x.classList.toggle('active', x === b));
  render();
});
document.getElementById('mode').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  mode = b.dataset.mode;
  document.querySelectorAll('#mode button').forEach(x => x.classList.toggle('on', x === b));
  render();
});
document.getElementById('year').addEventListener('change', e => { year = e.target.value; render(); });
document.getElementById('q').addEventListener('input', e => { query = e.target.value; render(); });

hallLoad('/api/siberman/hall/rating').then(d => {
  data = d;
  document.getElementById('year').insertAdjacentHTML('beforeend', d.years.map(y => `<option value="${y}">${y}</option>`).join(''));
  render();
}).catch(err => { table.innerHTML = `<tr><td class="state-msg">${hallEsc(err.message)}</td></tr>`; });
