'use strict';
// Вкладка «Заявки» админки жеребьёвки: заявки года по порядку прихода, статус и комментарий директора
// (сохраняются сразу), поиск, фильтр, карточка с журналом, Excel, загрузка CSV Тильды, адрес вебхука.

const ENT_API = `/api/siberman/admin/entries/${DRAW_YEAR}`;
const ENT_STATUS = { review: '⌛️ на изучении', admitted: '✅ допущена', rejected: '❌ не соответствует',
                     withdrawn: '🚫 отказ от жеребьёвки' };
const ENT_FORMAT = { individual: 'Личное', relay: 'Эстафета' };
let ENT = null;
const entEl = id => document.getElementById(id);
const entEsc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const entUrl = s => /^https?:\/\//i.test(String(s ?? '').trim()) ? String(s).trim() : '';
const entDate = s => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)} ${s.slice(11, 16)}` : '';

async function entFetch(path, opt = {}) {
  const r = await fetch(ENT_API + path, { cache: 'no-store', ...opt });
  if (r.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search + '#entries'); throw new Error('нужен вход'); }
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
    const next = Math.max(...ENT.years) + 1;
    entEl('ent-year').innerHTML = ENT.years.map(y => `<option${y === DRAW_YEAR ? ' selected' : ''}>${y}</option>`).join('')
      + (ENT.years.includes(next) ? '' : `<option value="${next}">${next}</option>`);
    entEl('ent-export').href = `${ENT_API}/export.xlsx`;
    entEl('ent-webhook').textContent = ENT.webhook_path ? location.origin + ENT.webhook_path : 'не настроен (нет SIBERMAN_WEBHOOK_SECRET)';
    entRender();
  } catch (e) { entMsg(e.message, 'err'); }
}

function entRender() {
  const c = ENT.counts;
  entEl('ent-counts').textContent = `Всего ${c.total} · ⌛️ ${c.review} · ✅ ${c.admitted} · ❌ ${c.rejected} · 🚫 ${c.withdrawn}`;
  const q = entEl('ent-q').value, f = entEl('ent-filter').value;
  const rows = ENT.entries.filter(e => (!f || e.status === f) && entryMatches(`${e.surname} ${e.name}`, q));
  entEl('ent-rows').innerHTML = rows.map(e => `<tr data-id="${e.id}">
    <td>${e.n}</td><td>${entDate(e.submitted_at)}</td><td><b>${entEsc(e.surname + ' ' + e.name)}</b></td>
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

async function entOpenCard(id) {
  try {
    const e = await entFetch(`/${id}`);
    const relay = e.format === 'relay' ? `<p>Команда: <b>${entEsc(e.team_name)}</b><br>Плавание: ${entEsc(e.relay_swim)}<br>Велосипед: ${entEsc(e.relay_bike)}<br>Бег: ${entEsc(e.relay_run)}</p>` : '';
    const audit = e.audit.map(a => `<li>${entDate(a.created_at)} · ${entEsc(a.admin_user)} · ${a.action === 'status' ? `${ENT_STATUS[a.old_value]} → ${ENT_STATUS[a.new_value]}` : `комментарий: «${entEsc(a.new_value)}»`}</li>`).join('');
    entEl('ent-card').innerHTML = `<button class="btn-small" style="float:right" onclick="entEl('ent-card').hidden = true">×</button>
      <h3>${entEsc(e.surname + ' ' + e.name)}</h3>
      <p>${ENT_FORMAT[e.format]} · ${entEsc(e.city)} · ДР ${e.birthdate ? e.birthdate.split('-').reverse().join('.') : '—'}<br>${entEsc(e.email)} · ${entEsc(e.phone)}</p>${relay}
      ${e.wildcard_reason ? `<h4>Почему wild card</h4><div class="text">${entEsc(e.wildcard_reason)}</div>` : ''}
      ${e.results_text ? `<h4>О результатах</h4><div class="text">${entEsc(e.results_text)}</div>` : ''}
      ${entUrl(e.result_url) ? `<p><a href="${entEsc(entUrl(e.result_url))}" target="_blank" rel="noopener noreferrer">Ссылка на результаты</a></p>`
        : e.result_url ? `<p>Ссылка на результаты: ${entEsc(e.result_url)}</p>` : ''}
      <h4>Журнал</h4><ul>${audit || '<li class="muted">изменений не было</li>'}</ul>`;
    entEl('ent-card').hidden = false;
  } catch (err) { entMsg(err.message, 'err'); }
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
entEl('ent-year').addEventListener('change', e => { location.href = `${location.pathname}?year=${e.target.value}#entries`; });
entEl('ent-upload').addEventListener('click', entUpload);
entEl('ent-webhook-copy').addEventListener('click', () => navigator.clipboard.writeText(entEl('ent-webhook').textContent).then(() => entMsg('Адрес вебхука скопирован')));
entEl('ent-rows').addEventListener('change', e => { if (e.target.dataset.status) entSetStatus(e.target); });
entEl('ent-rows').addEventListener('focusout', e => { if (e.target.dataset.comment) entSetComment(e.target); });
entEl('ent-rows').addEventListener('click', e => {
  if (e.target.closest('select, textarea')) return;
  const tr = e.target.closest('tr[data-id]');
  if (tr) entOpenCard(+tr.dataset.id);
});

// Смена года во вкладке «Заявки» перезагружает страницу с ?year= — вкладка открывается снова
if (location.hash === '#entries') {
  const btn = [...document.querySelectorAll('.admin-tab')].find(b => b.textContent.trim() === 'Заявки');
  if (btn) switchTab('entries', btn);
}
