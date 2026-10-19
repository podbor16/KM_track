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
  ['quota_repeat', 'Повторных всего (М+Ж, вкл. wild card)'], ['quota_novice', 'Новичков всего (М+Ж, вкл. wild card)'],
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
let armed = null;      // взведённое подтверждение {key, until}; переживает перерисовку кнопок
let armedTimer = null;
let loadSeq = 0;       // номер последнего запроса /state — устаревшие ответы не применяем
let lastStateText = null;
let expiredShown = false;

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const norm = s => String(s ?? '').toLowerCase().replace(/ё/g, 'е');
const fio = a => `${a.surname} ${a.name}`.trim();
const catLabel = c => S.category_labels[c];

function detailText(data, status) {
  const d = data && data.detail;
  if (Array.isArray(d)) {
    const label = loc => (CFG_FIELDS.find(([k]) => k === loc[loc.length - 1]) || [])[1];
    return `проверьте значения: ${d.map(x => (label(x.loc || []) ? `${label(x.loc)} — ` : '') + (x.msg || 'неверное значение')).join('; ')}`;
  }
  return d || `HTTP ${status}`;
}

function sessionExpired() {
  const el = $('msg');
  el.className = 'msg msg-error';
  el.textContent = 'Сессия закончилась — войдите заново ';
  const a = document.createElement('a');
  a.href = '/login';
  a.textContent = 'войти';
  el.appendChild(a);
  el.style.display = 'block';
  expiredShown = true;
}

async function request(url, opt) {
  const r = await fetch(url, opt);
  if (r.status === 401) { sessionExpired(); const e = new Error('нужно войти'); e.expired = true; throw e; }
  const text = await r.text();
  let data = {};
  try { data = JSON.parse(text); } catch (e) { /* не JSON */ }
  if (!r.ok) throw new Error(detailText(data, r.status));
  return { text, data };
}

async function api(path, body) {
  const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  return (await request(API + path, opt)).data;
}

function msg(text, kind = 'ok') {
  const el = $('msg');
  expiredShown = false;
  el.className = `msg msg-${kind}`;
  el.textContent = text;
  el.style.display = text ? 'block' : 'none';
}

function fail(e) { if (!e.expired) msg(e.message, 'error'); }

const isArmed = key => armed !== null && armed.key === key && armed.until > Date.now();

function confirmClick(btn, key, action) {
  clearTimeout(armedTimer);
  if (isArmed(key)) { armed = null; renderArmed(); action(); return; }
  armed = { key, until: Date.now() + 4000 };
  renderArmed();
  armedTimer = setTimeout(() => { armed = null; renderArmed(); }, 4000);
}

// Всё, где показывается «Точно?»: раунды, журнал, список участников
function renderArmed() { renderRounds(); renderJournal(); renderSearch(); }

// Без force перерисовываем только при изменении ответа — иначе опрос пересоздаёт кнопки и сбивает ввод.
async function load(force = false) {
  const seq = ++loadSeq;
  try {
    const { text } = await request(API + '/state');
    if (seq !== loadSeq) return; // пришёл более свежий запрос
    if (expiredShown) msg('');
    if (!force && text === lastStateText) return;
    lastStateText = text;
    S = JSON.parse(text);
    render();
  } catch (e) { if (!e.expired && seq === loadSeq) msg(`Ошибка загрузки: ${e.message}`, 'error'); }
}

function render() { renderRounds(); renderCounters(); renderSearch(); renderJournal(); renderLists(); }

// ── Раунды и счётчики ──
function renderRounds() {
  $('rounds').innerHTML = Object.entries(S.round_labels).map(([n, label]) => {
    const active = Number(n) === S.config.current_round;
    const prefix = n === '0' ? '' : `Р${n} `;
    return `<button class="round-btn ${ROUND_COLORS[n]} ${active ? 'active' : ''}" onclick="setRound(${n}, this)">${isArmed('round:' + n) ? 'Точно?' : `● ${prefix}${esc(label)}`}</button>`;
  }).join('');
}

function setRound(n, btn) {
  if (n === S.config.current_round) return;
  confirmClick(btn, `round:${n}`, async () => {
    try { await api('/round', { round: n }); replacing = null; await load(true); $('search').focus(); }
    catch (e) { fail(e); }
  });
}

function renderCounters() {
  const c = S.counters, cfg = S.config, k = c.kinds, q = v => v ?? '?';
  $('counters').innerHTML =
    `Мужчины <b>${c.categories.men}/${q(cfg.capacity_men)}</b> · Женщины <b>${c.categories.women}/${q(cfg.capacity_women)}</b> · Эстафеты <b>${c.categories.relay}/${q(cfg.capacity_relay)}</b><br>` +
    `Повторные (победители, М+Ж) <b>${k.repeat}/${q(cfg.quota_repeat)}</b> · Новички <b>${k.novice}/${q(cfg.quota_novice)}</b> · ` +
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

const query = () => norm($('search').value.trim());

// Пустой поиск — весь список участников раунда (при исправлении — раунда и зачёта исправляемой
// записи), сначала доступные; набран текст — найденные среди всех заявок.
function candidates() {
  const q = query();
  const rnd = replacing ? replacing.round : S.config.current_round;
  const list = q
    ? S.applicants.filter(a => norm(fio(a)).startsWith(q))
    : S.applicants.filter(a => inRound(a, rnd) && (!replacing || a.category === replacing.category));
  const sorted = list
    .map(a => ({ a, reason: reasonFor(a) }))
    .sort((x, y) => (x.reason ? 1 : 0) - (y.reason ? 1 : 0) || fio(x.a).localeCompare(fio(y.a), 'ru'));
  return q ? sorted.slice(0, 12) : sorted;
}

// Выбор мышью — вторым кликом (длинный список, промах в эфире недопустим)
function pickFromList(id, btn) { confirmClick(btn, `pick:${id}`, () => choose(id)); }

function renderSearch() {
  const list = candidates();
  const selectable = list.filter(x => !x.reason);
  if (highlight >= selectable.length) highlight = 0;
  const banner = $('replace-banner');
  banner.style.display = replacing ? 'block' : 'none';
  if (replacing) {
    banner.innerHTML = `Исправление: вместо <b>${esc(replacing.name)}</b> (${catLabel(replacing.category)} №${replacing.position}) выберите правильного участника. <button class="btn-link" onclick="cancelReplace()">Отмена</button>`;
  }
  const typed = query() !== '';
  const head = typed ? '' : `<div class="res-head">Участники раунда: доступно ${selectable.length} из ${list.length} — дважды нажмите на строку, чтобы вытянуть</div>`;
  $('results').innerHTML = head + list.map(x => {
    const a = x.a, idx = selectable.indexOf(x);
    const isArmedRow = isArmed(`pick:${a.id}`);
    const cls = x.reason ? 'res disabled' : isArmedRow ? 'res armed' : (typed && idx === highlight ? 'res hl' : 'res');
    const wc = a.is_wildcard ? ' <span class="wc">WC</span>' : '';
    const click = x.reason ? '' : `onclick="pickFromList(${a.id}, this)"`;
    const hint = isArmedRow ? ' — <b>нажмите ещё раз, чтобы вытянуть</b>' : '';
    return `<div class="${cls}" ${click}><b>${esc(fio(a))}</b>${wc} · ${esc(a.city)} · ${a.chances} шанс. · ${catLabel(a.category)}${x.reason ? ` — <i>${esc(x.reason)}</i>` : ''}${hint}</div>`;
  }).join('');
}

async function choose(id) {
  if (busy) return;
  busy = true;
  const a = S.applicants.find(x => x.id === id);
  const typed = $('search').value;
  try {
    if (replacing) {
      await api(`/picks/${replacing.pick_id}/replace`, { applicant_id: id });
      msg(`Исправлено: ${fio(a)} → ${catLabel(replacing.category)} №${replacing.position}`);
      replacing = null;
    } else {
      const r = await api('/pick', { applicant_id: id });
      msg(`${fio(a)} → ${catLabel(r.category)} №${r.position}`);
    }
    if ($('search').value === typed) { $('search').value = ''; highlight = 0; } // уже набранное для следующего не стираем
  } catch (e) {
    fail(e);
  } finally {
    busy = false;
    await load(true);
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
      `<button class="btn-small danger" onclick="confirmClick(this, 'cancel:${j.pick_id}', () => cancelPick(${j.pick_id}))">${isArmed('cancel:' + j.pick_id) ? 'Точно?' : 'Отменить'}</button>`;
    return `<div class="jrow ${j.cancelled_at ? 'cancelled' : ''}">${t} · ${esc(S.round_labels[j.round])} · <b>${esc(j.surname + ' ' + j.name)}</b> → ${where} ${btns}</div>`;
  }).join('') || '<div class="jrow muted">Пока пусто</div>';
}

async function cancelPick(pickId) {
  try { await api(`/picks/${pickId}/cancel`, {}); msg('Запись отменена'); await load(true); }
  catch (e) { fail(e); }
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
  } catch (e) { fail(e); }
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
    if (r.already_invited) text += ` ⏳ уже стоит у ${r.already_invited.surname} ${r.already_invited.name} — второго не зовём.`;
    if (r.waitlist_empty) text += ' Лист ожидания пуст.';
    msg(text, r.waitlist_empty ? 'warn' : 'ok');
    if (r.suggest_revert) showRevert(r.suggest_revert);
    await load(true);
    if ($('tab-payments').classList.contains('active')) renderPayments();
  } catch (e) { fail(e); }
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
    const cur = S.applicants.find(x => x.id === id);
    await api('/payment', { applicant_id: id, status: 'none', comment: cur ? cur.payment_comment || '' : '' });
    $('revert').style.display = 'none';
    msg('⏳ снят');
    await load(true);
    if ($('tab-payments').classList.contains('active')) renderPayments();
  } catch (e) { fail(e); }
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
  const hostUrl = location.origin + S.host_link;
  $('host-link').innerHTML = `<a href="${esc(hostUrl)}" target="_blank" rel="noopener">Открыть</a>
    <button type="button" class="btn" onclick="navigator.clipboard.writeText('${esc(hostUrl)}').then(() => msg('Ссылка скопирована'))">Скопировать ссылку</button>`;
  $('import-info').textContent = S.config.imported_at
    ? `Таблица загружена ${S.config.imported_at.replace('T', ' ').slice(0, 16)}, заявок: ${S.applicants.length}`
    : 'Таблица ещё не загружена';
}

async function saveConfig() {
  const body = {};
  CFG_FIELDS.forEach(([k]) => { const v = $(`cfg-${k}`).value; body[k] = v === '' ? null : Number(v); });
  body.auto_invite_until = $('cfg-auto_invite_until').value || null;
  try { await api('/config', body); msg('Настройки сохранены'); await load(true); renderConfig(); }
  catch (e) { fail(e); }
}

const DIFF_LABELS = {
  gender: 'пол', city: 'город', pool: 'пул', is_wildcard: 'wild card', chances: 'шансов',
  starts_individual: 'старты лично', starts_relay: 'старты в эстафете', draw_accumulated: 'накопленные',
  is_local: 'местный', duathlon_222: '222 Дуатлон', race_24h: '24 часа', tattoo: 'тату',
  relay_swim: 'плавание', relay_bike: 'вело', relay_run: 'бег',
};

// Сравнение с загруженной таблицей: организаторы меняют шансы до самой жеребьёвки.
function diffHtml(df) {
  if (!df) return '<p class="muted">Сравнивать не с чем — таблица ещё не загружалась.</p>';
  if (!df.added.length && !df.removed.length && !df.changed.length) {
    return `<p>По сравнению с загруженной таблицей изменений нет (шариков ${df.balls.new}).</p>`;
  }
  const who = x => `${esc(x.fio)}${x.format === 'relay' ? ' <span class="muted">(эстафета)</span>' : ''}`;
  const val = (f, v) => (f === 'is_wildcard' ? (v ? 'да' : 'нет') : v === null || v === '' ? '—' : esc(String(v)));
  const changes = x => x.changes.map(c => `${DIFF_LABELS[c.field] || esc(c.field)}: ${val(c.field, c.old)} → <b>${val(c.field, c.new)}</b>`).join('; ');
  const part = (title, rows) => (rows.length ? `<p><b>${title} (${rows.length})</b></p><table class="pay-table">${rows.join('')}</table>` : '');
  return `<p><b>Что изменится</b> · шариков ${df.balls.old} → <b>${df.balls.new}</b></p>`
    + part('Изменены', df.changed.map(x => `<tr><td>${who(x)}</td><td>${changes(x)}</td></tr>`))
    + part('Добавлены', df.added.map(x => `<tr><td>${who(x)}</td><td>шансов: ${x.chances}</td></tr>`))
    + part('Убраны', df.removed.map(x => `<tr><td>${who(x)}</td><td>шансов было: ${x.chances}</td></tr>`));
}

function reportHtml(d) {
  const rows = Object.entries(d.report.groups).map(([k, g]) => `<tr><td>${GROUP_LABELS[k] || k}</td><td>${g.people}</td><td>${g.balls}</td></tr>`).join('');
  const errs = d.errors.length ? `<div class="msg msg-error" style="display:block">${d.errors.map(esc).join('<br>')}</div>` : '';
  const blocked = d.blocked && !d.written
    ? '<div class="msg msg-error" style="display:block">В журнале уже есть вытянутые — загрузка запрещена. Сначала «Очистить журнал».</div>' : '';
  const note = d.written ? 'Записано.' : (d.errors.length ? 'Есть ошибки — запись невозможна.' : 'Проверка без записи. Если всё верно — «Загрузить».');
  return `${errs}${blocked}<table class="pay-table"><tr><th>Группа</th><th>Людей</th><th>Шариков</th></tr>${rows}<tr><td><b>Всего</b></td><td><b>${d.report.total}</b></td><td></td></tr></table>`
    + `${d.errors.length ? '' : diffHtml(d.diff)}<p>${note}</p>`;
}

function renderContactsInfo() {
  $('contacts-info').textContent = S.contacts_count ? `Загружено контактов: ${S.contacts_count}` : 'Контакты ещё не загружены';
}

async function uploadContacts() {
  const f = $('contacts-file').files[0];
  if (!f) { msg('Выберите CSV-выгрузку заявок Тильды', 'error'); return; }
  const fd = new FormData();
  fd.append('file', f);
  try {
    const d = (await request(`${API}/contacts`, { method: 'POST', body: fd })).data;
    const miss = d.missing.length
      ? `<div class="msg msg-error" style="display:block">Нет контакта у ${d.missing.length}: ${d.missing.map(esc).join(', ')}</div>` : '';
    $('contacts-report').innerHTML = `${miss}<p>Строк в файле: ${d.rows}, людей: ${d.people} (повторных заявок: ${d.duplicates}`
      + `${d.bad_format ? `, без формата: ${d.bad_format}` : ''}). Найдено в жеребьёвке: ${d.matched} из ${d.applicants}.</p>`;
    msg('Контакты загружены');
    await load(true);
    renderContactsInfo();
  } catch (e) { fail(e); }
}

async function importTable(dryRun) {
  const f = $('import-file').files[0];
  if (!f) { msg('Выберите файл', 'error'); return; }
  const fd = new FormData();
  fd.append('file', f);
  fd.append('dry_run', dryRun ? 'true' : 'false');
  try {
    const d = (await request(`${API}/import`, { method: 'POST', body: fd })).data;
    $('import-report').innerHTML = reportHtml(d);
    if (d.written) { msg('Таблица загружена'); await load(true); renderConfig(); }
  } catch (e) { fail(e); }
}

async function resetDraw() {
  try {
    await api('/reset', { confirm: $('reset-confirm').value });
    $('reset-confirm').value = '';
    msg('Журнал очищен');
    await load(true);
  } catch (e) { fail(e); }
}

// ── Вкладки и запуск ──
function switchTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.toggle('active', el.id === `tab-${name}`));
  document.querySelectorAll('.admin-tab').forEach(b => b.classList.toggle('admin-tab--active', b === btn));
  if (!S) return;
  if (name === 'payments') { renderPayments(); renderContactsInfo(); }
  if (name === 'settings') renderConfig();
}

const search = $('search');
search.addEventListener('input', () => { highlight = 0; renderSearch(); });
search.addEventListener('keydown', e => {
  if (!query()) return; // стрелки и Enter — только по найденным: Enter на пустом поле не вытягивает первого в списке
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
