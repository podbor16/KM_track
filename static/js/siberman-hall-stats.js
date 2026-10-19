'use strict';
// Блок «Статистика» (/hall/stats): Siberman в цифрах — люди и старты личного зачёта, эстафеты,
// всего людей, страны и города, таблица по годам (макет stats-geo-v10).

function plural(n, one, few, many) {
  const a = n % 10, b = n % 100;
  return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many;
}

function render(s) {
  const i = s.individual, r = s.relay;
  const span = s.first_year === s.last_year ? s.first_year : `${s.first_year}–${s.last_year}`;
  const rows = s.years.map(y => `<tr><td><b>${y.year}</b></td><td>${y.ind_start} / ${y.ind_fin}</td>
    <td>${y.men} / ${y.women}</td><td>${y.relay_start} / ${y.relay_fin}</td><td>${y.newcomers}</td>
    <td>${hallTime(y.best_s)}</td></tr>`).join('');
  document.getElementById('stats').innerHTML = `
    <h3>Siberman в цифрах · ${span}</h3><div class="sub-h">Личный зачёт</div>
    <div class="st-two">
      <div class="st-grp"><div class="st-cap">Люди</div><div class="st-big">${i.people}</div>
        <div class="st-sub">${plural(i.people, 'человек стартовал', 'человека стартовали', 'человек стартовали')}<br>
          ${i.people_finished} из них ${plural(i.people_finished, 'финишировал', 'финишировали', 'финишировали')}</div>
        <div class="st-mf"><div class="m">мужчин<b>${i.people_men}</b></div><div class="f">женщин<b>${i.people_women}</b></div></div></div>
      <div class="st-grp"><div class="st-cap">Старты</div><div class="st-big">${i.starts}</div>
        <div class="st-sub">${plural(i.starts, 'старт', 'старта', 'стартов')} за все годы<br>
          ${i.finishes} ${plural(i.finishes, 'закончился', 'закончились', 'закончились')} финишем</div>
        <div class="st-mf"><div class="m">мужских<b>${i.starts_men}</b><span class="st-fin">финиш ${i.finishes_men}</span></div>
          <div class="f">женских<b>${i.starts_women}</b><span class="st-fin">финиш ${i.finishes_women}</span></div></div></div>
    </div>
    <div class="st-rel">Эстафеты: <b>${r.teams}</b> ${plural(r.teams, 'команда', 'команды', 'команд')},
      <b>${r.finished}</b> ${plural(r.finished, 'финишировала', 'финишировали', 'финишировали')}
      · в составах <b>${r.people}</b> ${plural(r.people, 'человек', 'человека', 'человек')}</div>
    <div class="st-foot"><span>Всего людей в Siberman <b>${s.people_total}</b></span>
      <span>стран <b>${s.countries}</b></span><span>городов <b>${s.cities}</b></span></div>
    <div class="tbl"><table class="years-tbl">
      <tr><th>Год</th><th>Личный<br>старт / финиш</th><th>М / Ж</th><th>Эстафеты<br>старт / финиш</th>
        <th>Новичков</th><th>Лучшее время</th></tr>${rows}</table></div>
    <div class="note">«Новичков» — первый старт человека в Siberman (лично или в эстафете). Страны и города —
      по людям, у которых известен город.</div>`;
}

hallLoad('/api/siberman/hall/stats').then(render)
  .catch(err => { document.getElementById('stats').innerHTML = `<div class="state-msg">${hallEsc(err.message)}</div>`; });
