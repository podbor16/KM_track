'use strict';
// Страница ведущих жеребьёвки (/draw/{год}/host/{ключ}): три колонки зачётов, карточка участника.
// Новый вытянутый — карточка сама переключается на него; клик по строке — карточка этого участника.
// Данные — /api/siberman/draw/{год}/host/{ключ}/state раз в 2 с (ответ из кэша, пересчёт при изменении).

const root = document.getElementById('host');
const API = `/api/siberman/draw/${root.dataset.year}/host/${root.dataset.token}/state`;
const CATS = ['men', 'women', 'relay'];
const POOL = { wildcard: 'wild card', relay: 'эстафета', repeat: 'повторный', novice: 'новичок' };
const EXTRA = [['starts_individual', 'старты лично'], ['starts_relay', 'старты в эстафете'],
  ['draw_accumulated', 'накопленные за жеребьёвки'], ['is_local', 'местный'], ['duathlon_222', 'Дуатлон 222'],
  ['race_24h', '24 часа'], ['tattoo', 'тату Siberman']];
let st = null, selected = null, lastSeen, tab = 'men';

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fio = a => `${a.surname} ${a.name}`.trim();
const years = arr => (arr && arr.length ? arr.join(', ') : '—');

function hms(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}`;
}

function rowOf(id) {
  for (const c of CATS) {
    const r = st.lists[c].find(x => x.applicant_id === id);
    if (r) return { cat: c, ...r };
  }
  return null;
}

function athleteHtml(ath) {
  if (!ath) return '';
  const s = ath.summary, b = ath.best_race, lines = [
    `Финишей лично: <b>${s.finishes}</b> · эстафет: <b>${s.relays}</b> · рекордов сейчас: <b>${s.records}</b>`];
  if (b) lines.push(`Лучший результат: <b>${hms(b.time_s)}</b> (${b.year}${b.place ? `, ${b.place} место` : ''})`);
  if (ath.rating) lines.push(`Рейтинг «лучший на человека»: <b>${ath.rating.position}</b> из ${ath.rating.total}`);
  lines.push(`<a href="/athlete/${encodeURIComponent(ath.slug)}" target="_blank" rel="noopener">Страница спортсмена →</a>`);
  return lines.map(l => `<div>${l}</div>`).join('');
}

function renderCard() {
  const box = document.getElementById('card');
  const a = selected != null ? st.people[selected] : null, r = selected != null ? rowOf(selected) : null;
  if (!a || !r) { box.innerHTML = '<div class="state-msg">Пока никого не вытянули</div>'; return; }
  const who = a.format === 'relay' ? 'эстафета (капитан)' : (a.gender === 'F' ? 'женщина' : 'мужчина');
  const extra = EXTRA.filter(([k]) => a[k]).map(([k, l]) => `<span class="chip">${l}: ${a[k]}</span>`).join('');
  const h = a.history;
  box.innerHTML = `
    <div class="host-where">${esc(st.category_labels[r.cat])} №${r.position} · ${esc(st.round_labels[r.round] || '')}
      <span class="badge ${r.section === 'waitlist' ? 'wait' : 'win'}">${r.section === 'waitlist' ? 'лист ожидания' : 'победитель'}</span>
      ${selected !== st.last ? '<button type="button" class="to-last" id="to-last">← К последнему</button>' : '<span class="badge last">последний</span>'}</div>
    <h1>${esc(fio(a))}${a.is_wildcard ? ' <span class="wc">WC</span>' : ''}</h1>
    <div class="host-meta">${esc(a.city)} · ${who} · ${esc(POOL[a.pool] || '')}</div>
    <div class="host-chances"><b>${a.chances}</b> ${a.chances === 1 ? 'шанс' : a.chances < 5 ? 'шанса' : 'шансов'}
      <span class="chips">${extra}</span></div>
    <h3>Siberman</h3>
    <div>Старты лично: ${years(h.individual)}</div><div>Финиши лично: ${years(h.finished)}</div>
    <div>Старты в эстафете: ${years(h.relay)}</div>
    ${athleteHtml(a.athlete)}
    ${a.format === 'relay' ? `<h3>Состав</h3><div>Плавание: ${esc(a.relay_swim) || '—'}</div>
      <div>Вело: ${esc(a.relay_bike) || '—'}</div><div>Бег: ${esc(a.relay_run) || '—'}</div>` : ''}
    ${a.wildcard_reason ? `<h3>${a.is_wildcard ? 'Почему wild card' : 'Просил wild card'}</h3>
      <div class="text">${esc(a.wildcard_reason)}</div>` : ''}
    ${a.results_text ? `<h3>О результатах</h3><div class="text">${esc(a.results_text)}</div>` : ''}`;
  const back = document.getElementById('to-last');
  if (back) back.onclick = () => { selected = st.last; render(); };
}

function renderCols() {
  document.getElementById('cols').innerHTML = CATS.map(c => {
    const rows = st.lists[c];
    const wins = rows.filter(r => r.section !== 'waitlist').length;
    let wait = false;
    const items = rows.map(r => {
      const a = st.people[r.applicant_id];
      const sep = r.section === 'waitlist' && !wait ? (wait = true, '<div class="host-sep">Лист ожидания</div>') : '';
      const cls = [r.applicant_id === st.last ? 'last' : '', r.applicant_id === selected ? 'sel' : '',
        r.section === 'waitlist' ? 'wait' : ''].join(' ');
      return `${sep}<button type="button" class="host-row ${cls}" data-id="${r.applicant_id}">
        <span class="n">${r.position}</span>${esc(fio(a))}${r.is_wildcard ? ' <span class="wc">WC</span>' : ''}</button>`;
    }).join('') || '<div class="state-msg">—</div>';
    return `<div class="host-col ${c === tab ? 'active' : ''}" data-cat="${c}">
      <h2>${esc(st.category_labels[c])} <span class="muted">${wins}</span></h2>${items}</div>`;
  }).join('');
}

function render() {
  document.getElementById('round').textContent = `Раунд: ${st.round_labels[st.current_round] || ''}`;
  renderCard();
  renderCols();
}

async function poll() {
  try {
    const r = await fetch(API, { cache: 'no-store' });
    if (!r.ok) throw new Error(r.status);
    st = await r.json();
    if (st.last !== lastSeen) { lastSeen = st.last; selected = st.last; }       // новый вытянутый — на него
    if (selected != null && !st.people[selected]) selected = st.last;          // отменили — к последнему
    render();
    document.getElementById('status').textContent = '';
  } catch (e) {
    document.getElementById('status').textContent = 'нет связи — повтор…';
  } finally {
    setTimeout(poll, 2000);
  }
}

document.getElementById('cols').addEventListener('click', e => {
  const b = e.target.closest('.host-row');
  if (b) { selected = +b.dataset.id; render(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
});
document.getElementById('tabs').addEventListener('click', e => {
  const b = e.target.closest('.tab');
  if (!b) return;
  tab = b.dataset.cat;
  document.querySelectorAll('#tabs .tab').forEach(x => x.classList.toggle('active', x === b));
  if (st) renderCols();
});
poll();
