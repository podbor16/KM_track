'use strict';
// Страница спортсмена Siberman (/athlete/{id}): шапка, сводка, медали, лучшие результаты, все участия,
// рекорды (спецификация hall §8, макет athlete-v2). Данные — /api/siberman/athlete/{id}.

const SEG = { race: 'Гонка 515', swim: 'Плавание 10', bike: 'Вело 421', bike1: 'Вело, 1 день', bike2: 'Вело, 2 день', run: 'Бег 84' };
const COL = { individual: 'личный', relay: 'эстафета', absolute: 'абсолют' };
const SEX = { M: 'М', F: 'Ж' };
const root = document.getElementById('athlete');

function cellTitle(key) {
  const [seg, col, g] = key.split(':');
  return `${SEG[seg]} · ${COL[col]}${SEX[g] ? ' · ' + SEX[g] : ''}`;
}

function medal(m, label, caption, cls = '') {
  const shape = m.key.startsWith('hex') ? 'hex' : 'disc';
  const pic = m.image ? `<img src="${hallEsc(m.image)}" alt="${hallEsc(m.name)}">`
    : `<div class="${shape}" style="background:${m.color}">${label}</div>`;   // цвет — константа medals.py
  return `<div class="md ${cls}" title="${hallEsc(m.name)}">${pic}${caption}</div>`;
}

function medals(a) {
  const shortName = m => hallEsc(m.name.split(' (')[0]);
  const items = a.medals.map(x => medal(x.medal, x.n, `${x.n}-й финиш<br>${shortName(x.medal)} · ${x.year}`))
    .concat(a.relay_medals.map(x => medal(x.medal, 'Э', `эстафета<br>${x.year} · «${hallEsc(x.team)}»`, 'small')));
  if (a.next_medal) items.push(medal(a.next_medal, a.medals.length + 1, `следующая<br>${shortName(a.next_medal)}`, 'next'));
  return `<h2>Медали</h2><div class="medals">${items.join('')}</div>`;
}

function best(a) {
  if (!a.best.length) return '';
  const boxes = a.best.map(b => `<div class="bx">${SEG[b.seg]}<b>${hallTime(b.time_s)}</b>
    <span class="muted">${b.year}${b.place ? ' · ' + b.place + ' место' : ''}</span>${b.record ? ' <span class="rec">РЕКОРД</span>' : ''}</div>`).join('');
  const notes = [a.best_place ? `Лучшее место: ${a.best_place.place} (${a.best_place.year}).` : '',
                 a.rating ? `В общем рейтинге «лучший на человека»: ${a.rating.position} из ${a.rating.total}.` : '']
    .filter(Boolean).join(' ');
  return `<h2>Лучшие результаты</h2><div class="best">${boxes}</div>${notes ? `<div class="muted ath-note">${notes}</div>` : ''}`;
}

function outcome(r) {
  if (r.status === 'finished') {
    return `<b>${hallTime(r.time_s)}</b>${r.format === 'relay' ? ' <span class="muted">команда</span>' : ''}`
      + (r.record ? ' <span class="rec">РЕКОРД</span>' : '');
  }
  if (r.status === 'racing') return '<span class="muted">на дистанции</span>';
  const st = r.dnf_stage && HALL_STAGE[r.dnf_stage] ? ` (${HALL_STAGE[r.dnf_stage]})` : '';
  return r.status === 'dsq' ? 'DSQ' : `DNF${st}`;
}

function participations(a) {
  const time = (r, k) => (k in r.times ? (r.times[k] == null ? '—' : hallTime(r.times[k])) : '<span class="muted">—</span>');
  const rows = a.participations.map(r => {
    const fmt = r.format === 'individual'
      ? `Личный${r.finish_no ? ` · <b>${r.finish_no}-й финиш</b>` : ''}`
      : `Эстафета · ${r.stages.map(s => HALL_STAGE[s]).join(', ')}<br>${hallCard(r.bib, r.year, '«' + hallEsc(r.team) + '»')}`;
    const place = !r.place ? '—' : r.format === 'individual' ? `${r.place.abs} / ${r.place.gender} ${SEX[r.gender] || ''}` : `${r.place.relay} эстаф.`;
    return `<tr class="${r.status === 'finished' || r.status === 'racing' ? '' : 'dnf'}"><td>${r.year}</td><td class="l">${fmt}</td>
      <td>${outcome(r)}</td><td>${place}</td><td>${time(r, 'swim')}</td><td>${time(r, 'bike')}</td><td>${time(r, 'run')}</td>
      <td>${hallCard(r.bib, r.year, 'карточка')}</td></tr>`;
  }).join('');
  return `<h2>Все участия</h2><div class="tbl"><table><tr><th>Год</th><th class="l">Формат</th><th>Итог</th><th>Место</th>
    <th>Плавание</th><th>Вело</th><th>Бег</th><th></th></tr>${rows}</table></div>`;
}

function records(a) {
  if (!a.records.length) return '';
  const rows = a.records.map(r => `<tr><td class="l${r.current ? '' : ' old'}">${cellTitle(r.cell)}${r.team ? ` · «${hallEsc(r.team)}»` : ''}</td>
    <td class="${r.current ? '' : 'old'}"><b>${hallTime(r.time_s)}</b></td><td class="${r.current ? '' : 'old'}">${r.year}</td>
    <td>${r.current ? '<span class="rec">действует</span>' : `<span class="muted">побит в ${r.beaten.year} (${hallTime(r.beaten.time_s)})</span>`}</td></tr>`).join('');
  return `<h2>Рекорды</h2><div class="tbl"><table><tr><th class="l">Рекорд</th><th>Время</th><th>Год</th><th>Статус</th></tr>${rows}</table></div>`;
}

function render(a) {
  const p = a.person, s = a.summary;
  document.title = `${p.fio} — Siberman`;
  const meta = [[p.city, p.country].filter(Boolean).join(', '), `Siberman с ${p.since}`].filter(Boolean).join(' · ');
  const stat = (n, one, few, many) => `<div><b>${n}</b>${hallPlural(n, one, few, many)}</div>`;
  root.innerHTML = `<div class="ath-head"><div><h1>${hallEsc(p.fio)}</h1><div class="ath-meta">${hallEsc(meta)}</div></div>
      ${p.bib ? `<div class="ath-bib"><span>№ ${hallEsc(p.bib)}</span><div>личный номер навсегда</div></div>` : ''}</div>
    <div class="ath-stats">${stat(s.starts, 'старт', 'старта', 'стартов')}${stat(s.finishes, 'финиш лично', 'финиша лично', 'финишей лично')}
      ${stat(s.relays, 'эстафета', 'эстафеты', 'эстафет')}${stat(s.records, 'рекорд сейчас', 'рекорда сейчас', 'рекордов сейчас')}</div>
    ${medals(a)}${best(a)}${participations(a)}${records(a)}`;
}

hallLoad(`/api/siberman/athlete/${encodeURIComponent(root.dataset.id)}`).then(render)
  .catch(err => { root.innerHTML = `<div class="state-msg">${hallEsc(err.message)}</div>`; });
