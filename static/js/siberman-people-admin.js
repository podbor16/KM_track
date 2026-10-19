'use strict';
// Админка реестра людей Siberman (/admin/people): «проверить», поиск и карточка человека,
// журнал с отменой, загрузка заявок Тильды. API: /api/siberman/admin/people/*.

const API = '/api/siberman/admin/people';
const STAGES = { none: 'личный', swim: 'плавание', bike: 'вело', run: 'бег' };
let reviewStatus = 'open';
let reviewsCache = [];
let card = null;
let searchTimer = null;
let noCity = null;

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function api(path, opts = {}) {
  const headers = opts.body && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {};
  const r = await fetch(API + path, { credentials: 'same-origin', ...opts, headers });
  if (r.status === 401) { location.href = '/login?next=/admin/people'; throw new Error('auth'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || ('Ошибка ' + r.status));
  return data;
}
const post = (path, body) => api(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body || {}) });

function msg(text, kind = 'ok') {
  const el = document.getElementById('msg');
  el.className = 'msg msg-' + kind;
  el.textContent = text;
  el.style.display = 'block';
}

async function act(fn, okText) {
  try {
    await fn();
    if (okText) msg(okText);
    await refreshAll();
  } catch (e) {
    if (e.message !== 'auth') msg(e.message, 'error');
  }
}

function startText(s) {
  return s.format === 'individual'
    ? `${s.year} личный №${esc(s.bib)}`
    : `${s.year} эстафета №${esc(s.bib)}, ${esc(STAGES[s.stage])} «${esc(s.team)}»`;
}

function personBox(p, label) {
  if (!p) return `<div class="pbox muted">${esc(label)}: человека уже нет (слит с другим)</div>`;
  return `<div class="pbox"><div class="plabel">${esc(label)}</div>
    <b><a href="#" data-card="${p.id}">${esc(p.fio)}</a></b> · id ${p.id}${p.bib ? ' · личный №' + esc(p.bib) : ''}
    <div class="muted">ДР ${esc(p.birthdate || '—')} · ${esc(p.city || '')}</div>
    <div class="muted">${(p.starts || []).map(startText).join('; ')}</div></div>`;
}

function reviewButtons(r) {
  const B = (label, action, cls = '') => `<button class="btn-small ${cls}" data-act="${esc(action)}">${esc(label)}</button>`;
  const out = [];
  const bd = r.applicant ? r.applicant.birthdate : '';
  if (r.kind === 'namesake_candidate') {
    r.others.forEach(o => { if (o && r.person) out.push(B(`Это ${o.fio} (id ${o.id})`, `merge:${r.person.id}:${o.id}`)); });
    out.push(B('Это другой человек', 'resolve'));
  } else if (r.kind === 'relinked') {
    r.others.forEach(o => { if (o && r.person) out.push(B(`Тот же человек: слить с ${o.fio} (id ${o.id})`, `merge:${r.person.id}:${o.id}`)); });
    out.push(B('Разные люди', 'resolve'));
  } else if (r.kind === 'manual_name_changed') {
    out.push(B('Оставить привязку', 'keep'));
    if (r.participant) out.push(B('Отделить в нового человека', 'split'));
  } else if (r.kind === 'gender_mismatch') {
    r.others.forEach(o => { if (o && r.person) out.push(B(`Это ${o.fio} (id ${o.id})`, `merge:${r.person.id}:${o.id}`)); });
    out.push(B('Это другой человек', 'resolve'));
  } else if (r.kind === 'bib_name_change' || r.kind === 'format_switch' || r.kind === 'bib_gender_mismatch') {
    out.push(B('Тот же человек', 'resolve'));
    if (r.participant) out.push(B('Другой человек — отделить', 'split'));
  } else if (r.kind === 'bd_conflict' && r.person) {
    out.push(B(`Оставить ${r.person.birthdate || '—'}`, 'resolve'));
    if (bd) out.push(B(`Заменить на ${bd}`, `bd:${r.person.id}:${bd}`));
    out.push(B('Это заявка тёзки', 'resolve'));
  } else if (r.kind === 'applicant_ambiguous') {
    r.others.forEach(o => { if (o && bd) out.push(B(`ДР у ${o.fio} (id ${o.id})`, `bd:${o.id}:${bd}`)); });
    out.push(B('Ни у кого из них', 'resolve'));
  } else if ((r.kind === 'applicant_city_mismatch' || r.kind === 'applicant_unconfirmed') && r.person) {
    if (bd) out.push(B('Это он — записать ДР', `bd:${r.person.id}:${bd}`));
    out.push(B('Не он', 'resolve'));
  }
  out.push(r.status === 'open' ? B('Отложить', 'defer') : B('Вернуть в «проверить»', 'reopen'));
  return out.join(' ');
}

async function loadReviews() {
  reviewsCache = await api(`/reviews?status=${reviewStatus}`);
  document.getElementById('reviews-count').textContent = reviewStatus === 'open' ? `(${reviewsCache.length})` : '';
  const box = document.getElementById('reviews');
  if (!reviewsCache.length) { box.innerHTML = '<div class="muted">Пусто</div>'; return; }
  box.innerHTML = reviewsCache.map((r, i) => `<div class="card">
    <div class="rtitle">${esc(r.title)}</div>
    ${r.participant ? `<div>${startText(r.participant)} — ${esc(r.participant.fio)}, ${esc(r.participant.city)}</div>` : ''}
    ${r.applicant ? `<div>Заявка: ${esc(r.applicant.fio)}, ДР ${esc(r.applicant.birthdate)}, ${esc(r.applicant.city)}</div>` : ''}
    <div class="pboxes">${r.person ? personBox(r.person, ['namesake_candidate', 'gender_mismatch', 'relinked'].includes(r.kind) ? 'Сейчас — отдельный человек' : 'Человек') : ''}${r.others.map(o => personBox(o, 'Кандидат')).join('')}</div>
    <div data-i="${i}">${reviewButtons(r)}</div></div>`).join('');
}

async function onReviewAction(r, action) {
  const done = () => post(`/reviews/${r.id}`, { status: 'resolved' });
  if (action === 'resolve') return act(done, 'Отмечено как решённое');
  if (action === 'defer') return act(() => post(`/reviews/${r.id}`, { status: 'deferred' }), 'Отложено');
  if (action === 'keep') return act(() => post(`/reviews/${r.id}/keep`), 'Привязка подтверждена с новым ФИ');
  if (action === 'reopen') return act(() => post(`/reviews/${r.id}`, { status: 'open' }), 'Возвращено в «проверить»');
  // Действие и решение по записи — одним запросом (одна запись в журнале, одна отмена)
  if (action === 'split') {
    return act(() => post('/reassign', { keys: [r.participant.key], target_id: null, review_id: r.id }),
      'Выступление отделено в нового человека');
  }
  const [kind, a, b] = action.split(':');
  if (kind === 'merge') {
    return act(() => post('/merge', { source_id: +a, target_id: +b, review_id: r.id }), 'Слито');
  }
  if (kind === 'bd') {
    return act(() => post(`/${a}/birthdate`, { birthdate: b, review_id: r.id }), 'Дата рождения записана');
  }
}

async function openCard(id) {
  try {
    card = await api(`/${id}`);
    showTab('search');
    renderCard();
  } catch (e) {
    if (e.message !== 'auth') msg(e.message, 'error');
  }
}

function selectedKeys() {
  return [...document.querySelectorAll('#card input[data-k]:checked')].map(c => card.participations[+c.dataset.k].key);
}

function renderCard() {
  const el = document.getElementById('card');
  if (!card) { el.innerHTML = ''; return; }
  const p = card.person;
  el.innerHTML = `<div class="card">
    <h2>${esc(p.surname)} ${esc(p.name)} <span class="muted">id ${p.id}${p.bib_individual ? ' · личный №' + esc(p.bib_individual) : ''} · ${esc(p.city)}${p.country ? ', ' + esc(p.country) : ''}</span></h2>
    <div class="row">Дата рождения <input type="date" id="bd" value="${esc(p.birthdate || '')}">
      <button class="btn-small" id="bd-save">Сохранить</button>
      ${card.reviews.length ? `<span class="tag">в «проверить»: ${card.reviews.length}</span>` : ''}</div>
    <div class="row">Город вручную <input id="city" value="${esc(p.city_manual || '')}" placeholder="${esc(p.city || '')}" maxlength="100" style="width:220px">
      <button class="btn-small" id="city-save">Сохранить</button>
      <span class="muted">для карты «География» главнее протокола; пусто — город из протоколов</span></div>
    <table class="tbl"><tr><th></th><th>Год</th><th>Формат</th><th>№</th><th>ФИ в протоколе</th><th>Статус</th><th>Город</th></tr>
    ${card.participations.map((x, i) => `<tr><td><input type="checkbox" data-k="${i}"></td><td>${x.year}</td>
      <td>${x.format === 'individual' ? 'личный' : 'эстафета, ' + esc(STAGES[x.stage]) + ' «' + esc(x.team) + '»'}</td>
      <td>${esc(x.bib)}</td><td>${esc(x.fio)}${x.manual ? ' <span class="tag">вручную</span>' : ''}</td>
      <td>${esc(x.status)}</td><td>${esc(x.city)}</td></tr>`).join('')}</table>
    <div class="row">Отмеченные выступления: <button class="btn-small" id="mv-new">в нового человека</button>
      или к человеку id <input id="mv-id" type="number" min="1" style="width:100px"> <button class="btn-small" id="mv-to">перенести</button></div>
    <div class="row">Слить этого человека с id <input id="mg-id" type="number" min="1" style="width:100px">
      <button class="btn-small danger" id="mg">слить</button>
      <span class="muted">выступления перейдут к указанному, этот человек исчезнет</span></div></div>`;
  document.getElementById('bd-save').onclick = () =>
    act(() => post(`/${p.id}/birthdate`, { birthdate: document.getElementById('bd').value || null }), 'Дата рождения сохранена');
  document.getElementById('city-save').onclick = () =>
    act(() => post(`/${p.id}/city`, { city: document.getElementById('city').value }), 'Город сохранён');
  document.getElementById('mv-new').onclick = () => {
    const keys = selectedKeys();
    if (!keys.length) return msg('Отметьте выступления галочками', 'error');
    act(() => post('/reassign', { keys, target_id: null }), 'Перенесено в нового человека');
  };
  document.getElementById('mv-to').onclick = () => {
    const keys = selectedKeys(), id = +document.getElementById('mv-id').value;
    if (!keys.length || !id) return msg('Отметьте выступления и укажите id человека', 'error');
    act(() => post('/reassign', { keys, target_id: id }), `Перенесено к id ${id}`);
  };
  document.getElementById('mg').onclick = () => {
    const id = +document.getElementById('mg-id').value;
    if (!id) return msg('Укажите id человека', 'error');
    if (!confirm(`Слить «${p.surname} ${p.name}» (id ${p.id}) с id ${id}?`)) return;
    act(async () => { await post('/merge', { source_id: p.id, target_id: id }); card = await api(`/${id}`); }, 'Слито');
  };
}

async function doSearch() {
  const q = document.getElementById('search').value.trim();
  const box = document.getElementById('results');
  if (q.length < 2 && !/^\d+$/.test(q)) { box.innerHTML = ''; return; }
  const rows = await api(`/search?q=${encodeURIComponent(q)}`);
  box.innerHTML = rows.map(r => `<div class="res" data-card="${r.id}"><b>${esc(r.fio)}</b> · id ${r.id}${r.bib ? ' · №' + esc(r.bib) : ''}
    · ДР ${esc(r.birthdate || '—')} · ${esc(r.years)} · ${esc(r.city)}</div>`).join('') || '<div class="muted">Никого</div>';
}

async function loadJournal() {
  const rows = await api('/journal');
  document.getElementById('journal').innerHTML = rows.map(j => `<div class="jrow ${j.undone_at ? 'cancelled' : ''}">
    <span class="muted">${esc(String(j.created_at).replace('T', ' ').slice(0, 16))} · ${esc(j.created_by)}</span>
    <b>${esc(j.summary)}</b>
    ${j.undone_at ? '<span class="muted">отменено</span>' : `<button class="btn-small danger" data-undo="${j.id}">Отменить</button>`}</div>`).join('')
    || '<div class="jrow muted">Пока пусто</div>';
}

const norm = s => String(s ?? '').toLowerCase().replace(/ё/g, 'е');

function startsText(r) {
  return r.starts.map(s => `${s.year} ${s.format === 'individual' ? 'личный' : STAGES[s.stage] + ' «' + s.team + '»'}`).join('; ');
}

function renderNoCity() {
  if (!noCity) return;
  const q = norm(document.getElementById('nocity-q').value.trim());
  const rows = noCity.people.filter(r => !q || norm(`${r.fio} ${startsText(r)}`).includes(q));
  document.getElementById('nocity').innerHTML = '<tr><th>ФИ</th><th>Выступления</th><th>Город</th></tr>'
    + rows.map(r => `<tr><td>${r.person_id ? `<a href="#" data-card="${r.person_id}">${esc(r.fio)}</a>` : esc(r.fio)}</td>
      <td>${esc(startsText(r))}</td>
      <td>${r.person_id ? `<input data-city-for="${r.person_id}" placeholder="Город" maxlength="100" style="width:160px">
        <button class="btn-small" data-city-save="${r.person_id}">Сохранить</button>` : '<span class="muted">не в реестре</span>'}</td></tr>`).join('');
  const nc = noCity.no_coords;
  document.getElementById('nocoords').innerHTML = nc.length ? `<div class="card"><h2>Города без координат (${nc.length})</h2>
    <p class="muted">В списках «Географии» есть, на карте нет. Добавить: <code>python scripts/siberman_geocode_cities.py</code>,
    проверить <code>data/siberman/cities.json</code> и выложить.</p>
    ${nc.map(c => `<div>${esc(c.name)}${c.country ? ', ' + esc(c.country) : ''} — ${c.count}</div>`).join('')}</div>` : '';
}

async function loadNoCity() {
  noCity = await api('/no-city');
  document.getElementById('nocity-count').textContent = noCity.people.length ? `(${noCity.people.length})` : '';
  renderNoCity();
}

async function refreshAll() {
  await loadReviews();
  await loadJournal();
  await loadNoCity();
  if (card) {
    try { card = await api(`/${card.person.id}`); } catch (e) { card = null; }
    renderCard();
  }
}

function showTab(name) {
  document.querySelectorAll('.admin-tab').forEach(b => b.classList.toggle('admin-tab--active', b.dataset.tab === name));
  document.querySelectorAll('.tab-content').forEach(s => s.classList.toggle('active', s.id === 'tab-' + name));
}

function report(r) {
  const el = document.getElementById('report');
  const s = r.sync || r;
  const lines = [];
  if (r.rows !== undefined) {
    lines.push(`Строк в файле: ${r.rows}. Людей с датой рождения: ${r.people}. Без даты: ${r.no_birthday}. Неверных дат: ${r.bad_birthday}.`);
  }
  lines.push(`Привязано выступлений: ${s.linked}. Новых людей: ${s.new_persons}. Записано дат рождения: ${s.birthdates}. ` +
             `Новых «проверить»: ${s.reviews}. Снято привязок со стёртой фамилией: ${s.dropped}. ` +
             `Убрано устаревших привязок: ${s.stale_links}, людей без выступлений: ${s.orphans}.`);
  el.textContent = lines.join('\n');
  el.style.display = 'block';
}

document.addEventListener('click', e => {
  const t = e.target;
  const tab = t.closest('.admin-tab');
  if (tab) { showTab(tab.dataset.tab); return; }
  if (t.matches('[data-status]')) {
    reviewStatus = t.dataset.status;
    document.querySelectorAll('[data-status]').forEach(b => b.classList.toggle('active', b === t));
    loadReviews().catch(err => msg(err.message, 'error'));
    return;
  }
  const cardLink = t.closest('[data-card]');
  if (cardLink) { e.preventDefault(); openCard(+cardLink.dataset.card); return; }
  if (t.matches('[data-act]')) {
    const i = +t.closest('[data-i]').dataset.i;
    onReviewAction(reviewsCache[i], t.dataset.act);
    return;
  }
  if (t.matches('[data-city-save]')) {
    const id = t.dataset.citySave, v = document.querySelector(`[data-city-for="${id}"]`).value.trim();
    if (!v) return msg('Введите город', 'error');
    act(() => post(`/${id}/city`, { city: v }), 'Город сохранён');
    return;
  }
  if (t.matches('[data-undo]')) {
    act(() => post(`/undo/${t.dataset.undo}`), 'Действие отменено');
  }
});

document.getElementById('search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => doSearch().catch(err => msg(err.message, 'error')), 250);
});
document.getElementById('nocity-q').addEventListener('input', renderNoCity);

document.getElementById('upload').onclick = async () => {
  const f = document.getElementById('csv').files[0];
  if (!f) return msg('Выберите CSV-файл', 'error');
  const fd = new FormData();
  fd.append('file', f);
  try { report(await post('/applicants', fd)); msg('Заявки загружены'); await refreshAll(); }
  catch (e) { if (e.message !== 'auth') msg(e.message, 'error'); }
};

document.getElementById('sync').onclick = async () => {
  try { report(await post('/sync')); msg('Привязки пересобраны'); await refreshAll(); }
  catch (e) { if (e.message !== 'auth') msg(e.message, 'error'); }
};

refreshAll().catch(e => { if (e.message !== 'auth') msg(e.message, 'error'); });
