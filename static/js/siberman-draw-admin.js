// Админка жеребьёвки Siberman (templates/siberman/draw_admin.html):
// экран оператора (раунды, поиск, журнал с «Исправить»/«Отменить», зачёты),
// оплаты, настройки. Подтверждения — вторым кликом, без диалоговых окон (эфир).
const API = `/api/siberman/admin/draw/${DRAW_YEAR}`;
const ROUND_COLORS = { 0: 'red', 1: 'blue', 2: 'black', 3: 'black', 4: 'black' };
const POOL = { wildcard: 'wild card', relay: 'эстафета', repeat: 'повторный', novice: 'новичок' };
const PAY = { none: '—', pending: '⏳ ожидает', paid: '✅ оплачено', unpaid: '❌ не оплачено' };
const PAY_ICON = { none: '', pending: '⏳', paid: '✅', unpaid: '❌' };
const CFG_FIELDS = [
  ['capacity_men', 'Мест: мужчины'], ['capacity_women', 'Мест: женщины'], ['capacity_relay', 'Мест: эстафеты'],
  ['quota_repeat_men', 'Повторные: мужчины'], ['quota_repeat_women', 'Повторные: женщины'],
  ['quota_novice_men', 'Новички: мужчины'], ['quota_novice_women', 'Новички: женщины'],
];
const GROUP_LABELS = {
  wildcard_M: 'Wild card — мужчины', wildcard_F: 'Wild card — женщины', wildcard: 'Wild card — эстафеты',
  relay: 'Эстафеты', repeat_M: 'Повторные — мужчины', repeat_F: 'Повторные — женщины',
  novice_M: 'Новички — мужчины', novice_F: 'Новички — женщины',
};

let S = null;          // последнее состояние с сервера
let highlight = 0;     // подсвеченный результат поиска
let replacing = null;  // запись журнала, которую исправляем
let busy = false;      // запрос «вытянуть» в полёте — повторный Enter игнорируем

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const norm = s => String(s ?? '').toLowerCase().replace(/ё/g, 'е');
const fio = a => `${a.surname} ${a.name}`.trim();
const catLabel = c => S.category_labels[c];

async function api(path, body) {
  const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(API + path, opt);
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) { location.href = '/login'; throw new Error('нужно войти'); }
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

function msg(text, kind = 'ok') {
  const el = $('msg');
  el.className = `msg msg-${kind}`;
  el.textContent = text;
  el.style.display = text ? 'block' : 'none';
}

function confirmClick(btn, action) {
  if (btn.dataset.armed) { delete btn.dataset.armed; action(); return; }
  btn.dataset.armed = '1';
  const text = btn.textContent;
  btn.textContent = 'Точно?';
  setTimeout(() => { if (btn.dataset.armed) { delete btn.dataset.armed; btn.textContent = text; } }, 4000);
}

async function load() {
  try { S = await api('/state'); render(); } catch (e) { msg(`Ошибка загрузки: ${e.message}`, 'error'); }
}

function render() { renderRounds(); renderCounters(); renderSearch(); renderJournal(); renderLists(); }

// ── Раунды и счётчики ──
function renderRounds() {
  $('rounds').innerHTML = Object.entries(S.round_labels).map(([n, label]) => {
    const active = Number(n) === S.config.current_round;
    const prefix = n === '0' ? '' : `Р${n} `;
    return `<button class="round-btn ${ROUND_COLORS[n]} ${active ? 'active' : ''}" onclick="setRound(${n}, this)">● ${prefix}${esc(label)}</button>`;
  }).join('');
}

function setRound(n, btn) {
  if (n === S.config.current_round) return;
  confirmClick(btn, async () => {
    try { await api('/round', { round: n }); replacing = null; await load(); $('search').focus(); }
    catch (e) { msg(e.message, 'error'); }
  });
}

function renderCounters() {
  const c = S.counters, cfg = S.config, k = c.kinds, q = v => v ?? '?';
  $('counters').innerHTML =
    `Мужчины <b>${c.categories.men}/${q(cfg.capacity_men)}</b> · Женщины <b>${c.categories.women}/${q(cfg.capacity_women)}</b> · Эстафеты <b>${c.categories.relay}/${q(cfg.capacity_relay)}</b><br>` +
    `Повторные: М <b>${k.repeat_M}/${q(cfg.quota_repeat_men)}</b>, Ж <b>${k.repeat_F}/${q(cfg.quota_repeat_women)}</b> · ` +
    `Новички: М <b>${k.novice_M}/${q(cfg.quota_novice_men)}</b>, Ж <b>${k.novice_F}/${q(cfg.quota_novice_women)}</b> · ` +
    `В ёмкости раунда: <b>${c.pool_people}</b> чел., <b>${c.pool_balls}</b> шар.`;
}

// ── Поиск ──
function inRound(a, rnd) { // зеркало logic.in_round_pool
  if (rnd === 0) return a.is_wildcard;
  if (a.is_wildcard) return false;
  return ({ 1: a.pool === 'relay', 2: a.pool === 'repeat', 3: a.pool === 'novice', 4: a.pool === 'repeat' || a.pool === 'novice' })[rnd] || false;
}

function reasonFor(a) {
  if (a.placed) return `уже вытянут — ${catLabel(a.placed.category)} №${a.placed.position}`;
  if (replacing) {
    if (a.category !== replacing.category) return `другой зачёт: ${catLabel(a.category)}`;
    if (!inRound(a, replacing.round)) return 'не из раунда исправляемой записи';
    return '';
  }
  return a.block || ''; // сервер: не в этом раунде / квота или места набраны (logic.check_pick)
}

function candidates() {
  const q = norm($('search').value.trim());
  if (!q) return [];
  return S.applicants
    .filter(a => norm(fio(a)).startsWith(q))
    .map(a => ({ a, reason: reasonFor(a) }))
    .sort((x, y) => (x.reason ? 1 : 0) - (y.reason ? 1 : 0) || fio(x.a).localeCompare(fio(y.a), 'ru'))
    .slice(0, 12);
}

function renderSearch() {
  const list = candidates();
  const selectable = list.filter(x => !x.reason);
  if (highlight >= selectable.length) highlight = 0;
  const banner = $('replace-banner');
  banner.style.display = replacing ? 'block' : 'none';
  if (replacing) {
    banner.innerHTML = `Исправление: вместо <b>${esc(replacing.name)}</b> (${catLabel(replacing.category)} №${replacing.position}) выберите правильного участника. <button class="btn-link" onclick="cancelReplace()">Отмена</button>`;
  }
  $('results').innerHTML = list.map(x => {
    const a = x.a, idx = selectable.indexOf(x);
    const cls = x.reason ? 'res disabled' : (idx === highlight ? 'res hl' : 'res');
    const wc = a.is_wildcard ? ' <span class="wc">WC</span>' : '';
    const click = x.reason ? '' : `onclick="choose(${a.id})"`;
    return `<div class="${cls}" ${click}><b>${esc(fio(a))}</b>${wc} · ${esc(a.city)} · ${a.chances} шанс. · ${catLabel(a.category)}${x.reason ? ` — <i>${esc(x.reason)}</i>` : ''}</div>`;
  }).join('');
}

async function choose(id) {
  if (busy) return;
  busy = true;
  const a = S.applicants.find(x => x.id === id);
  try {
    if (replacing) {
      await api(`/picks/${replacing.pick_id}/replace`, { applicant_id: id });
      msg(`Исправлено: ${fio(a)} → ${catLabel(replacing.category)} №${replacing.position}`);
      replacing = null;
    } else {
      const r = await api('/pick', { applicant_id: id });
      msg(`${fio(a)} → ${catLabel(r.category)} №${r.position}`);
    }
    $('search').value = '';
    highlight = 0;
  } catch (e) {
    msg(e.message, 'error');
  } finally {
    busy = false;
    await load();
    $('search').focus();
  }
}

function startReplace(pickId) {
  const j = S.journal.find(x => x.pick_id === pickId);
  replacing = { pick_id: pickId, name: `${j.surname} ${j.name}`, category: j.category, position: j.position, round: j.round };
  $('search').value = '';
  renderSearch();
  $('search').focus();
}

function cancelReplace() { replacing = null; renderSearch(); }

// ── Журнал и зачёты ──
function renderJournal() {
  $('journal').innerHTML = S.journal.map(j => {
    const t = (j.created_at || '').slice(11, 19);
    const where = j.cancelled_at ? (j.replaced_by ? '<i>исправлено</i>' : '<i>отменено</i>') : `${catLabel(j.category)} №${j.position}`;
    const btns = j.cancelled_at ? '' :
      `<button class="btn-small" onclick="startReplace(${j.pick_id})">Исправить</button> ` +
      `<button class="btn-small danger" onclick="confirmClick(this, () => cancelPick(${j.pick_id}))">Отменить</button>`;
    return `<div class="jrow ${j.cancelled_at ? 'cancelled' : ''}">${t} · ${esc(S.round_labels[j.round])} · <b>${esc(j.surname + ' ' + j.name)}</b> → ${where} ${btns}</div>`;
  }).join('') || '<div class="jrow muted">Пока пусто</div>';
}

async function cancelPick(pickId) {
  try { await api(`/picks/${pickId}/cancel`, {}); msg('Запись отменена'); await load(); }
  catch (e) { msg(e.message, 'error'); }
}

function renderLists() {
  $('lists').innerHTML = ['men', 'women', 'relay'].map(c => {
    const rows = S.lists[c], cap = S.config[`capacity_${c}`];
    return `<div class="list"><div class="list-title">${catLabel(c)} ${rows.length}/${cap ?? '?'}</div>` +
      rows.map(r => `<div class="lrow ${r.section === 'waitlist' ? 'wait' : ''}" onclick="openSummary(${r.applicant_id})">${r.position}. ${esc(r.surname + ' ' + r.name)}${r.is_wildcard ? ' <span class="wc">WC</span>' : ''} ${PAY_ICON[r.payment_status]}</div>`).join('') +
      '</div>';
  }).join('');
}

// ── Сводка по участнику ──
function payEditor(a, prefix) {
  const options = Object.entries(PAY).map(([k, v]) => `<option value="${k}" ${k === a.payment_status ? 'selected' : ''}>${v}</option>`).join('');
  return `<select id="${prefix}-${a.id}">${options}</select> <input id="${prefix}-c-${a.id}" value="${esc(a.payment_comment)}" placeholder="Комментарий"> ` +
    `<button class="btn-small" onclick="savePayment(${a.id}, '${prefix}')">Сохранить</button>`;
}

async function openSummary(id) {
  try {
    const d = await api(`/applicant/${id}`);
    const a = d.applicant, h = d.history, p = d.placement;
    const yrs = arr => (arr.length ? arr.join(', ') : '—');
    const who = a.format === 'relay' ? 'эстафета (капитан)' : (a.gender === 'M' ? 'мужчина' : 'женщина');
    $('summary-body').innerHTML = `
      <h3>${esc(fio(a))}${a.is_wildcard ? ' <span class="wc">WC</span>' : ''}</h3>
      <div>${esc(a.city)} · ${who} · ${POOL[a.pool]}</div>
      <h4>Шансы: ${a.chances}</h4>
      <div>заявка 1 · старты лично ${a.starts_individual} · старты в эстафете ${a.starts_relay} · накопленные за жеребьёвки ${a.draw_accumulated}
        <span class="muted">(обнуляются после выигрыша)</span> · местный ${a.is_local} · Дуатлон 222 ${a.duathlon_222} · 24 часа ${a.race_24h} · тату ${a.tattoo}</div>
      <h4>Siberman</h4>
      <div>Старты лично: ${yrs(h.individual)}<br>Финиши лично: ${yrs(h.finished)}<br>Старты в эстафете: ${yrs(h.relay)}</div>
      ${a.format === 'relay' ? `<h4>Состав</h4><div>Плавание: ${esc(a.relay_swim)}<br>Вело: ${esc(a.relay_bike)}<br>Бег: ${esc(a.relay_run)}</div>` : ''}
      <h4>Жеребьёвка</h4>
      <div>${p ? `${catLabel(p.category)} №${p.position} · ${esc(S.round_labels[p.round])} · ${(p.created_at || '').slice(11, 19)}` : 'ещё не вытянут'}</div>
      ${p ? `<h4>Оплата</h4>${payEditor(a, 'pay')}` : ''}
      ${a.wildcard_reason ? `<h4>Почему wild card</h4><div class="text">${esc(a.wildcard_reason)}</div>` : ''}
      ${a.results_text ? `<h4>О результатах</h4><div class="text">${esc(a.results_text)}</div>` : ''}`;
    $('summary').classList.add('open');
  } catch (e) { msg(e.message, 'error'); }
}

function closeSummary() { $('summary').classList.remove('open'); }

// ── Оплаты ──
async function savePayment(id, prefix) {
  const status = $(`${prefix}-${id}`).value, comment = $(`${prefix}-c-${id}`).value;
  try {
    const r = await api('/payment', { applicant_id: id, status, comment });
    let text = 'Статус сохранён.';
    if (r.auto_invited) {
      const x = r.auto_invited;
      text += ` ⏳ поставлен: ${x.surname} ${x.name} (${catLabel(x.category)} №${x.position}) — отправьте счёт.`;
    }
    if (r.waitlist_empty) text += ' Лист ожидания пуст.';
    msg(text, r.waitlist_empty ? 'warn' : 'ok');
    if (r.suggest_revert) showRevert(r.suggest_revert);
    await load();
    if ($('tab-payments').classList.contains('active')) renderPayments();
  } catch (e) { msg(e.message, 'error'); }
}

function showRevert(s) {
  const el = $('revert');
  el.style.display = 'block';
  el.innerHTML = `${esc(s.surname + ' ' + s.name)} получил ⏳ автоматически из-за этой неоплаты. ` +
    `<button class="btn-small" onclick="revertInvite(${s.applicant_id})">Снять ⏳</button> ` +
    `<button class="btn-small" onclick="$('revert').style.display='none'">Оставить</button>`;
}

async function revertInvite(id) {
  try {
    await api('/payment', { applicant_id: id, status: 'none', comment: '' });
    $('revert').style.display = 'none';
    msg('⏳ снят');
    await load();
    if ($('tab-payments').classList.contains('active')) renderPayments();
  } catch (e) { msg(e.message, 'error'); }
}

function renderPayments() {
  const sectionLabel = s => (s === 'waitlist' ? 'Лист ожидания' : s === 'winner' ? 'Победитель' : '');
  $('payments').innerHTML = ['men', 'women', 'relay'].map(c =>
    `<h3>${catLabel(c)}</h3><table class="pay-table"><tr><th>№</th><th>Участник</th><th>Раздел</th><th>Статус и комментарий</th><th>Изменён</th></tr>` +
    S.lists[c].map(r => {
      const a = S.applicants.find(x => x.id === r.applicant_id);
      return `<tr class="${r.section === 'waitlist' ? 'wait' : ''}"><td>${r.position}</td>` +
        `<td><a href="#" onclick="openSummary(${a.id});return false">${esc(fio(a))}</a>${a.is_wildcard ? ' <span class="wc">WC</span>' : ''}</td>` +
        `<td>${sectionLabel(r.section)}</td><td>${payEditor(a, 'payt')}</td>` +
        `<td>${(a.payment_updated_at || '').replace('T', ' ').slice(0, 16)}</td></tr>`;
    }).join('') + '</table>').join('');
}

// ── Настройки ──
function renderConfig() {
  $('config-form').innerHTML = CFG_FIELDS.map(([k, l]) => `<label>${l}<input type="number" min="0" id="cfg-${k}" value="${S.config[k] ?? ''}"></label>`).join('') +
    `<label>Автопередача ⏳ до (не включая)<input type="date" id="cfg-auto_invite_until" value="${S.config.auto_invite_until ?? ''}"></label>`;
  $('import-info').textContent = S.config.imported_at
    ? `Таблица загружена ${S.config.imported_at.replace('T', ' ').slice(0, 16)}, заявок: ${S.applicants.length}`
    : 'Таблица ещё не загружена';
}

async function saveConfig() {
  const body = {};
  CFG_FIELDS.forEach(([k]) => { const v = $(`cfg-${k}`).value; body[k] = v === '' ? null : Number(v); });
  body.auto_invite_until = $('cfg-auto_invite_until').value || null;
  try { await api('/config', body); msg('Настройки сохранены'); await load(); renderConfig(); }
  catch (e) { msg(e.message, 'error'); }
}

function reportHtml(d) {
  const rows = Object.entries(d.report.groups).map(([k, g]) => `<tr><td>${GROUP_LABELS[k] || k}</td><td>${g.people}</td><td>${g.balls}</td></tr>`).join('');
  const errs = d.errors.length ? `<div class="msg msg-error" style="display:block">${d.errors.map(esc).join('<br>')}</div>` : '';
  const note = d.written ? 'Записано.' : (d.errors.length ? 'Есть ошибки — запись невозможна.' : 'Проверка без записи. Если всё верно — «Загрузить».');
  return `${errs}<table class="pay-table"><tr><th>Группа</th><th>Людей</th><th>Шариков</th></tr>${rows}<tr><td><b>Всего</b></td><td><b>${d.report.total}</b></td><td></td></tr></table><p>${note}</p>`;
}

async function importTable(dryRun) {
  const f = $('import-file').files[0];
  if (!f) { msg('Выберите файл', 'error'); return; }
  const fd = new FormData();
  fd.append('file', f);
  fd.append('dry_run', dryRun ? 'true' : 'false');
  const r = await fetch(`${API}/import`, { method: 'POST', body: fd });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { msg(d.detail || `HTTP ${r.status}`, 'error'); return; }
  $('import-report').innerHTML = reportHtml(d);
  if (d.written) { msg('Таблица загружена'); await load(); renderConfig(); }
}

async function resetDraw() {
  try {
    await api('/reset', { confirm: $('reset-confirm').value });
    $('reset-confirm').value = '';
    msg('Журнал очищен');
    await load();
  } catch (e) { msg(e.message, 'error'); }
}

// ── Вкладки и запуск ──
function switchTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.toggle('active', el.id === `tab-${name}`));
  document.querySelectorAll('.admin-tab').forEach(b => b.classList.toggle('admin-tab--active', b === btn));
  if (!S) return;
  if (name === 'payments') renderPayments();
  if (name === 'settings') renderConfig();
}

const search = $('search');
search.addEventListener('input', () => { highlight = 0; renderSearch(); });
search.addEventListener('keydown', e => {
  const selectable = candidates().filter(x => !x.reason);
  if (e.key === 'ArrowDown') { highlight = Math.min(highlight + 1, Math.max(selectable.length - 1, 0)); renderSearch(); e.preventDefault(); }
  else if (e.key === 'ArrowUp') { highlight = Math.max(highlight - 1, 0); renderSearch(); e.preventDefault(); }
  else if (e.key === 'Enter' && selectable[highlight]) { choose(selectable[highlight].a.id); }
  else if (e.key === 'Escape') { search.value = ''; cancelReplace(); }
});

load();
// Оператор видит изменения директора (оплаты) и второй вкладки; другие вкладки не перерисовываем,
// чтобы не затирать ввод.
setInterval(() => { if ($('tab-operator').classList.contains('active') && !busy) load(); }, 3000);
