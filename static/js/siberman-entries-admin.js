'use strict';
// Раздел «Заявки» админки Siberman: заявки года по порядку прихода, статус и комментарий директора
// (сохраняются сразу), поиск, фильтр, карточка с журналом, Excel, загрузка CSV Тильды, адрес вебхука.

// Год заявок — свой, не год жеребьёвки страницы: заявки собираются на гонку после разыгрываемой
let entYear = Number(document.getElementById('entries-admin').dataset.year);
const entApi = () => `/api/siberman/admin/entries/${entYear}`;
const ENT_STATUS = { review: '⌛️ на изучении', admitted: '✅ допущена', rejected: '❌ не соответствует',
                     withdrawn: '🚫 отказ от жеребьёвки' };
const ENT_FORMAT = { individual: 'Личное', relay: 'Эстафета' };
const ENT_IDENTITY = { review: 'Проверить личность', matched: 'Связано автоматически',
                       manual: 'Связь подтверждена', new: 'Новый участник подтверждён' };
let ENT = null;
const entEl = id => document.getElementById(id);
const entEsc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const entUrl = s => /^https?:\/\//i.test(String(s ?? '').trim()) ? String(s).trim() : '';
const entDate = s => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)} ${s.slice(11, 16)}` : '';

async function entFetch(path, opt = {}) {
  const r = await fetch(entApi() + path, { cache: 'no-store', ...opt });
  if (r.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search); throw new Error('нужен вход'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `ошибка ${r.status}`);
  return data;
}

function entMsg(text, kind = 'ok') {
  const cls = kind === 'err' ? 'error' : kind;
  entEl('ent-msg').innerHTML = text ? `<div class="msg msg-${cls}" style="display:block">${entEsc(text)}</div>` : '';
}

async function entriesLoad() {
  try {
    ENT = await entFetch('');
    entEl('ent-year').innerHTML = ENT.years.map(y => `<option${y === entYear ? ' selected' : ''}>${y}</option>`).join('');
    entEl('ent-export').href = `${entApi()}/export.xlsx`;
    entEl('ent-chances-export').href = `/api/siberman/admin/draw/${entYear - 1}/chances.xlsx`;
    entEl('ent-chances-export').textContent = `Черновик шансов на гонку ${entYear}`;
    entEl('ent-chances-year-note').textContent = `Для гонки ${entYear} используется жеребьёвка ${entYear - 1}; этот год указан в адресе выгрузки.`;
    entEl('ent-webhook').textContent = ENT.webhook_path ? location.origin + ENT.webhook_path : 'не настроен (нет SIBERMAN_WEBHOOK_SECRET)';
    entRender();
  } catch (e) { entMsg(e.message, 'err'); }
}

function entRender() {
  const c = ENT.counts;
  entEl('ent-counts').textContent = `Всего ${c.total} · ⌛️ ${c.review} · ✅ ${c.admitted} · ❌ ${c.rejected} · 🚫 ${c.withdrawn}`;
  const q = entEl('ent-q').value, f = entEl('ent-filter').value;
  const rows = ENT.entries.filter(e => (!f || (f === 'identity' ? e.identity.state === 'review' : e.status === f))
    && entryMatches(`${e.surname} ${e.name}`, q));
  entEl('ent-rows').innerHTML = rows.map(e => `<tr data-id="${e.id}">
    <td>${e.n}</td><td>${entDate(e.submitted_at)}</td><td><b>${entEsc(e.surname + ' ' + e.name)}</b>
      <br><small>${ENT_IDENTITY[e.identity.state]}</small></td>
    <td>${ENT_FORMAT[e.format]}</td><td>${{ M: 'М', F: 'Ж' }[e.gender] || ''}</td><td>${entEsc(e.city)}</td>
    <td>${entEsc(e.email)}</td><td>${entEsc(e.phone)}</td>
    <td><select data-status="${e.id}">${Object.entries(ENT_STATUS).map(([k, v]) => `<option value="${k}"${k === e.status ? ' selected' : ''}>${v}</option>`).join('')}</select></td>
    <td><textarea data-comment="${e.id}">${entEsc(e.comment)}</textarea></td></tr>`).join('')
    || '<tr><td colspan="10" class="muted">Заявок нет</td></tr>';
}

async function entSetStatus(sel) {
  const e = ENT.entries.find(x => x.id === +sel.dataset.status), old = e.status;
  try {
    await entFetch(`/${e.id}/status`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: sel.value }) });
    e.status = sel.value;
    ENT.counts[old]--; ENT.counts[sel.value]++;
    entMsg(`${e.surname} ${e.name}: ${ENT_STATUS[sel.value]}`);
    entRender();
  } catch (err) { sel.value = old; entMsg(`Статус не сохранён: ${err.message}`, 'err'); }
}

async function entSetComment(area) {
  const e = ENT.entries.find(x => x.id === +area.dataset.comment);
  if (area.value.trim() === e.comment) return;
  try {
    await entFetch(`/${e.id}/comment`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ comment: area.value }) });
    e.comment = area.value.trim();
    entMsg(`${e.surname} ${e.name}: комментарий сохранён`);
  } catch (err) { entMsg(`Комментарий не сохранён: ${err.message}`, 'err'); }
}

function entPersonLabel(p) {
  return `#${p.id} · ${entEsc(p.surname + ' ' + p.name)} · ${entEsc(p.city_manual || p.city || '—')} · ${entEsc(p.birthdate || 'ДР неизвестна')}`;
}

function entIdentityPanel(e) {
  const { candidates, person_id, state } = e.identity;
  const current = candidates.find(p => p.id === person_id);
  const selectable = candidates.filter(p => p.id !== person_id &&
    (!e.birthdate || !p.birthdate || e.birthdate === p.birthdate));
  const canCreate = e.birthdate && !person_id && !candidates.some(p => p.birthdate === e.birthdate);
  const options = selectable.map(p => `<option value="${p.id}">${entPersonLabel(p)}</option>`).join('');
  const action = options ? `<label>${current ? 'Другая карточка' : 'Карточка'}
    <select id="ent-identity-person">${options}</select></label>
    <button type="button" class="btn-small" onclick="entIdentity(${e.id}, 'link')">${current ? 'Сменить карточку' : 'Подтвердить связь'}</button>` : '';

  return `<h4>Личность</h4>
    <p>${ENT_IDENTITY[state]}${state === 'matched' ? ' · Имя, фамилия и дата рождения совпали' : ''}</p>
    ${current ? `<p>Карточка ${entPersonLabel(current)}</p>` : ''}
    ${!current && !candidates.length ? '<p class="muted">В реестре нет карточки с таким именем и фамилией.</p>' : ''}
    ${!current && candidates.length && !options ? '<p class="muted">У найденных карточек другая дата рождения.</p>' : ''}
    ${current && action ? `<details><summary>Выбрать другую карточку</summary>${action}</details>` : action}
    ${canCreate ? `<button type="button" class="btn-small"
      onclick="entIdentity(${e.id}, 'create')">Подтвердить нового участника</button>` : ''}
    ${person_id ? `<button type="button" class="btn-small"
      onclick="entIdentity(${e.id}, 'review')">Вернуть на проверку</button>` : ''}`;
}

async function entOpenCard(id) {
  try {
    const e = await entFetch(`/${id}`);
    const relay = e.format === 'relay' ? `<p>Команда: <b>${entEsc(e.team_name)}</b><br>Плавание: ${entEsc(e.relay_swim)}<br>Велосипед: ${entEsc(e.relay_bike)}<br>Бег: ${entEsc(e.relay_run)}</p>` : '';
    const audit = e.audit.map(a => `<li>${entDate(a.created_at)} · ${entEsc(a.admin_user)} · ${a.action === 'status' ? `${ENT_STATUS[a.old_value]} → ${ENT_STATUS[a.new_value]}`
      : a.action === 'identity' ? `личность: ${entEsc(a.old_value || 'проверка')} → ${entEsc(a.new_value || 'проверка')}`
        : `комментарий: «${entEsc(a.new_value)}»`}</li>`).join('');
    entEl('ent-card').innerHTML = `<button class="btn-small" style="float:right" onclick="entEl('ent-card').hidden = true">×</button>
      <h3>${entEsc(e.surname + ' ' + e.name)}</h3>
      <p>${ENT_FORMAT[e.format]} · ${entEsc(e.city)} · ДР ${e.birthdate ? e.birthdate.split('-').reverse().join('.') : '—'}<br>${entEsc(e.email)} · ${entEsc(e.phone)}</p>${relay}
      ${entIdentityPanel(e)}
      ${e.wildcard_reason ? `<h4>Почему wild card</h4><div class="text">${entEsc(e.wildcard_reason)}</div>` : ''}
      ${e.results_text ? `<h4>О результатах</h4><div class="text">${entEsc(e.results_text)}</div>` : ''}
      ${entUrl(e.result_url) ? `<p><a href="${entEsc(entUrl(e.result_url))}" target="_blank" rel="noopener noreferrer">Ссылка на результаты</a></p>`
        : e.result_url ? `<p>Ссылка на результаты: ${entEsc(e.result_url)}</p>` : ''}
      <h4>Журнал</h4><ul>${audit || '<li class="muted">изменений не было</li>'}</ul>`;
    entEl('ent-card').hidden = false;
  } catch (err) { entMsg(err.message, 'err'); }
}

async function entIdentity(id, mode) {
  const person_id = mode === 'link' ? Number(entEl('ent-identity-person').value) : null;
  try {
    await entFetch(`/${id}/identity`, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mode, person_id})});
    await entriesLoad();
    await entOpenCard(id);
    entMsg('Решение о личности сохранено');
  } catch (e) { entMsg(e.message, 'err'); }
}

async function entUpload() {
  const file = entEl('ent-file').files[0];
  if (!file) return entMsg('Выберите CSV-файл', 'err');
  const fd = new FormData(); fd.append('file', file);
  try {
    const r = await entFetch('/import', { method: 'POST', body: fd });
    entEl('ent-import-report').innerHTML = `<p>Строк: ${r.rows}, новых: ${r.new}, уже были: ${r.known}, с ошибкой: ${r.errors.length}</p>`
      + (r.errors.length ? `<ul>${r.errors.map(x => `<li>${entEsc(x)}</li>`).join('')}</ul>` : '');
    await entriesLoad();
  } catch (err) { entMsg(err.message, 'err'); }
}

entEl('ent-q').addEventListener('input', () => ENT && entRender());
entEl('ent-filter').addEventListener('change', () => ENT && entRender());
entEl('ent-year').addEventListener('change', e => {
  entYear = +e.target.value;
  const url = new URL(location.href);
  url.searchParams.set('year', entYear);
  history.replaceState(null, '', url);
  entEl('ent-draw-link').href = `/admin/draw?year=${entYear - 1}`;
  entEl('ent-card').hidden = true;
  entEl('ent-import-report').innerHTML = '';
  entMsg('');
  entriesLoad();
});
entEl('ent-upload').addEventListener('click', entUpload);
entEl('ent-webhook-copy').addEventListener('click', () => navigator.clipboard.writeText(entEl('ent-webhook').textContent).then(() => entMsg('Адрес вебхука скопирован')));
entEl('ent-rows').addEventListener('change', e => { if (e.target.dataset.status) entSetStatus(e.target); });
entEl('ent-rows').addEventListener('focusout', e => { if (e.target.dataset.comment) entSetComment(e.target); });
entEl('ent-rows').addEventListener('click', e => {
  if (e.target.closest('select, textarea')) return;
  const tr = e.target.closest('tr[data-id]');
  if (tr) entOpenCard(+tr.dataset.id);
});

entriesLoad().then(() => {
  const id = Number(new URLSearchParams(location.search).get('entry'));
  if (id && ENT?.entries.some(e => e.id === id)) entOpenCard(id);
});
