// Демо «Повтор гонки»: виртуальные часы + подмена сетевых запросов страницы.
// Подключается в <head> ДО скриптов страницы. Режимы (data-mode):
//   tracker (по умолчанию) — трекер Жары: fetch /api/event-results + EventSource /api/sse/tracker;
//   poll — live-результаты Siberman: fetch /api/siberman/results, часы по «времени без ночей»;
//   poll + data-format="ep" — Триатлет/Дуатлон: эндпоинты из data-endpoints, часы от выстрела.
(function () {
    'use strict';
    const me = document.currentScript;
    const BASE = me.dataset.base;        // '/race-tracker-demo/'
    const RACE = me.dataset.race;        // 'zhara_21' | 'siberman_2026'
    const MODE = me.dataset.mode || 'tracker';
    const RealDate = Date;
    const realFetch = window.fetch.bind(window);
    const whenBody = () => document.body ? Promise.resolve()
        : new Promise(r => document.addEventListener('DOMContentLoaded', r));

    // ---------- виртуальные часы ----------
    // clock.v — момент на шкале режима (мс): tracker — unix ms, poll — «время без ночей».
    // Date.now() = toAbs(шкала): tracker — тождественно, poll — compactToAbs.
    const clock = { v: RealDate.now(), r: performance.now(), speed: 1 };
    const vline = () => clock.v + (performance.now() - clock.r) * clock.speed;
    let toAbs = v => v;
    const vnow = () => toAbs(vline());
    function setClock(v, speed) {
        clock.v = v; clock.r = performance.now();
        if (speed !== undefined) clock.speed = speed;
    }
    class VDate extends RealDate {
        constructor(...a) { if (a.length === 0) super(vnow()); else super(...a); }
        static now() { return vnow(); }
    }
    window.Date = VDate;

    // Аниматор Chart.js считает прогресс по Date.now(); на паузе виртуальное время стоит —
    // анимация замирает на первом кадре. Отключаем анимации при определении window.Chart.
    (function patchChart() {
        let impl = window.Chart;
        const off = C => { if (C && C.defaults) { C.defaults.animation = false; C.defaults.transitions = {}; } };
        off(impl);
        Object.defineProperty(window, 'Chart', {
            configurable: true, enumerable: true,
            get: () => impl,
            set: v => { impl = v; off(v); },
        });
    })();

    function parseT(v) {
        if (!v) return null;
        const m = /^(\d+)(s|m)?$/.exec(v);
        return m ? Number(m[1]) * (m[2] === 'm' ? 60 : 1) : null;
    }
    const SPEEDS = [1, 2, 5, 10];
    const parseSpeed = v => SPEEDS.includes(Number(v)) ? Number(v) : null;
    const q0 = new URLSearchParams(location.search);

    const json = obj => new Response(JSON.stringify(obj), { headers: { 'Content-Type': 'application/json' } });
    let rec = null;
    const el = {};
    const curSpeed = () => clock.speed > 0 ? clock.speed : (el.lastSpeed || 1);
    // Перезагрузка на момент t (назад/круг): параметры страницы сохраняются, t/speed — наши.
    function reloadAt(t) {
        const q = new URLSearchParams(location.search);
        q.set('t', Math.round(t)); q.set('speed', curSpeed());
        location.replace(`${location.pathname}?${q}`);
    }
    const fmt = s => {
        const sign = s < 0 ? '−' : ''; s = Math.abs(Math.floor(s));
        return `${sign}${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    };

    // ---------- режимы ----------
    // Интерфейс: tNow() — секунды на шкале; ready() — запись загружена; fetch(u) — ответ или null;
    // seekForward(t); step(t) — раз в 250 мс; panel() — {min, max, marks:[{t,label}]}; fmt(t); loop() — {start, end}.
    function trackerMode() {
        const RealES = window.EventSource;
        // Часы выставляются синхронно, до любого кода трекера (иначе его метки времени окажутся «в будущем»).
        const GUN_MS = Number(me.dataset.gunMs);
        const T0 = parseT(q0.get('t')) ?? Number(me.dataset.startS);
        setClock(GUN_MS + T0 * 1000, parseSpeed(q0.get('speed')) ?? 1);

        const tRace = () => (vnow() - rec.meta.gun_unix_ms) / 1000;
        const st = { byId: new Map(), cursor: 0, lastStep: null, sentDist: new Map() };

        function preselect(meta) {
            try {
                const key = meta.current_event.storage_key;
                if (key && !localStorage.getItem(key) && meta.preselect) {
                    localStorage.setItem(key, JSON.stringify(meta.preselect));
                }
            } catch (e) { /* localStorage недоступен */ }
        }
        function distAt(id, t) {
            const s = rec.distance[id];
            if (!s) return st.byId.get(id).current_distance || 0;
            if (t <= s[0][0]) return s[0][1];
            for (let i = 1; i < s.length; i++) {
                if (t <= s[i][0]) {
                    const [t0, d0] = s[i - 1], [t1, d1] = s[i];
                    return d0 + (d1 - d0) * (t - t0) / (t1 - t0);
                }
            }
            return s[s.length - 1][1];
        }
        function advanceTo(t) {
            const changed = new Set();
            const ch = rec.changes;
            while (st.cursor < ch.length && ch[st.cursor].t_s <= t) {
                for (const r of ch[st.cursor].results) {
                    const id = String(r.id);
                    st.byId.set(id, Object.assign({}, st.byId.get(id), r));
                    changed.add(id);
                }
                st.cursor++;
            }
            return changed;
        }
        function resetTo(t) {
            st.byId = new Map(rec.initial.results.map(r => [String(r.id), Object.assign({}, r)]));
            st.cursor = 0;
            st.sentDist = new Map();
            advanceTo(t);
        }
        function withDist(id, t) {
            const d = Math.round(distAt(id, t) * 1000) / 1000;
            st.sentDist.set(id, d);
            return Object.assign({}, st.byId.get(id), { current_distance: d });
        }
        function payload(results, initial) {
            const p = {
                server_time_unix: Math.round(vnow()),
                race_gun_unix_ms: initial === false ? null : rec.meta.gun_unix_ms,
                total_distance_km: initial === false ? null : rec.initial.total_distance_km,
                total_results: rec.initial.total_results,
                results,
            };
            if (initial !== undefined) p.initial = initial;
            return p;
        }
        function snapshot(initial) {
            const t = tRace();
            return payload([...st.byId.keys()].map(id => withDist(id, t)), initial);
        }
        function delta(t) {
            const ids = advanceTo(t);
            for (const id of st.byId.keys()) {
                const d = Math.round(distAt(id, t) * 1000) / 1000;
                if (st.sentDist.get(id) !== d) ids.add(id);
            }
            return payload([...ids].map(id => withDist(id, t)), false);
        }

        // ---------- подмена EventSource ----------
        const sources = new Set();
        class FakeEventSource {
            constructor(url) {
                this.url = url; this.readyState = 0; this.onmessage = null; this.onerror = null; this.onopen = null;
                this._listeners = [];
                sources.add(this);
                recReady.then(() => { this.readyState = 1; if (this.onopen) this.onopen(); this._send(snapshot(true)); });
            }
            addEventListener(type, fn) { if (type === 'message') this._listeners.push(fn); }
            removeEventListener(type, fn) { this._listeners = this._listeners.filter(f => f !== fn); }
            close() { this.readyState = 2; sources.delete(this); }
            _send(obj) {
                const ev = { data: JSON.stringify(obj) };
                if (this.onmessage) this.onmessage(ev);
                this._listeners.forEach(fn => fn(ev));
            }
        }
        window.EventSource = function (url, opts) {
            return String(url).includes('/api/sse/tracker') ? new FakeEventSource(url) : new RealES(url, opts);
        };

        return {
            tNow: tRace,
            ready() {
                preselect(rec.meta);
                const t0 = tRace();
                resetTo(t0);
                st.lastStep = Math.floor(t0 / rec.meta.step_s);
            },
            fetch(u) {
                if (u.pathname === '/api/current-event') return recReady.then(r => json(r.meta.current_event));
                if (u.pathname === '/api/event-results') return recReady.then(() => json(snapshot(undefined)));
                return null;
            },
            seekForward(t) {
                setClock(rec.meta.gun_unix_ms + t * 1000);
                resetTo(t);
                st.lastStep = Math.floor(t / rec.meta.step_s);
                sources.forEach(s => s._send(snapshot(true)));
            },
            step(t) {
                const step = Math.floor(t / rec.meta.step_s);
                if (step !== st.lastStep) {
                    st.lastStep = step;
                    const d = delta(t);
                    if (d.results.length) sources.forEach(s => s._send(d));
                }
            },
            panel: () => ({ min: rec.meta.t_from, max: rec.meta.t_to,
                            marks: rec.meta.marks.map(k => ({ t: k.t_s, label: k.label })) }),
            fmt,
            loop: () => ({ start: rec.meta.loop_start_s, end: rec.meta.loop_end_s }),
        };
    }

    // ---------- общее для poll ----------
    const KRSK_MS = 7 * 3600 * 1000;
    const HOLD_S = 600;                         // сколько держать итоговый протокол до нового круга
    const hhmm = ms => new RealDate(ms + KRSK_MS).toISOString().slice(11, 16);

    // Момент вкладки t (сек на шкале режима): ?t= → сохранённый в sessionStorage → defT.
    // ?t= страница затирает (syncUrlFromState собирает query с нуля), поэтому URL-параметр —
    // разовая команда: читаем, убираем из URL, текущий момент кладём в sessionStorage при уходе.
    // Часы: clock.v = t·1000.
    function restoreMoment(defT, clamp = t => t) {
        const KEY = `demo_t:${location.pathname}`;
        let saved = null;
        try { saved = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (e) { /* нет sessionStorage */ }
        const urlT = parseT(q0.get('t'));
        const T0 = urlT ?? (saved && Number.isFinite(saved.t) ? saved.t : defT);
        const SPEED0 = (urlT !== null ? parseSpeed(q0.get('speed')) : saved && parseSpeed(saved.speed)) ?? 1;
        setClock(clamp(T0) * 1000, SPEED0);
        if (q0.has('t') || q0.has('speed')) {
            const q = new URLSearchParams(location.search);
            q.delete('t'); q.delete('speed');
            const qs = q.toString();
            history.replaceState(history.state, '', location.pathname + (qs ? `?${qs}` : '') + location.hash);
        }
        window.addEventListener('pagehide', () => {
            try { sessionStorage.setItem(KEY, JSON.stringify({ t: Math.round(vline() / 1000), speed: curSpeed() })); }
            catch (e) { /* нет sessionStorage */ }
        });
    }

    // Состояние ответа на момент t: initial + changes с t_s ≤ t; курсор идёт вперёд, назад — пересборка.
    function cursorState(init, apply) {
        const st = { state: null, cursor: 0 };
        return function stateAt(t) {
            const ch = rec.changes;
            if (!st.state || (st.cursor > 0 && ch[st.cursor - 1].t_s > t)) { st.state = init(); st.cursor = 0; }
            while (st.cursor < ch.length && ch[st.cursor].t_s <= t) st.state = apply(st.state, ch[st.cursor++]);
            return st.state;
        };
    }

    // Перемотка вперёд: страница сама опрашивает API — дёргаем её функции обновления (data-refresh);
    // их нет (карточка грузит данные один раз) — перезагрузка на новый момент.
    function refreshAt(t) {
        const fns = (me.dataset.refresh || 'refreshData').split(',')
            .map(n => window[n.trim()]).filter(f => typeof f === 'function');
        if (!fns.length) { reloadAt(t); return; }
        setClock(t * 1000);
        fns.forEach(f => f());
    }

    // Переходы к карточке участника и обратно к результатам — с текущим моментом.
    // Прод-пути: data-participant-path (шаблон с {n}), data-results-path; демо: SITE и SITE/participant/<n>/.
    function linkAdapter(tNow) {
        const SITE = `${BASE}${me.dataset.slug}/`;
        const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const reCard = new RegExp(`^${esc(me.dataset.participantPath || '/participant/{n}').replace('\\{n\\}', '([^/]+)')}/?$`);
        const res = (me.dataset.resultsPath || '/').replace(/\/$/, '');
        const roots = new Set([res || '/', `${res}/`, SITE, `${SITE}index.html`]);
        function demoUrl(href) {
            let u;
            try { u = new URL(href, location.href); } catch (e) { return null; }
            if (u.origin !== location.origin) return null;
            const p = u.pathname;
            const m = reCard.exec(p)
                || (p.startsWith(`${SITE}participant/`) && /^([^/]+)\/?$/.exec(p.slice(SITE.length + 12)));
            let path;
            if (m) path = `${SITE}participant/${encodeURIComponent(decodeURIComponent(m[1]))}/`;
            else if (roots.has(p)) path = SITE;
            else return null;
            return `${path}?t=${Math.round(tNow())}&speed=${curSpeed()}`;
        }
        const realOpen = window.open.bind(window);
        window.open = function (url, ...rest) {
            const d = url == null ? null : demoUrl(String(url));
            return realOpen(d || url, ...rest);
        };
        const fixLink = e => {
            const a = e.target.closest && e.target.closest('a[href]');
            if (!a) return;
            const d = demoUrl(a.getAttribute('href'));
            if (d) a.href = d;
        };
        ['pointerdown', 'click', 'auxclick', 'contextmenu'].forEach(type => document.addEventListener(type, fixLink, true));
        return demoUrl;
    }

    // poll, формат Siberman (tools/demo/siberman/record.py): fetch /api/siberman/results, «время без ночей».
    function pollMode() {
        const DAYS = JSON.parse(me.dataset.days || '[]');
        if (!DAYS.length) throw new Error('[demo] нет data-days');
        const LISTS = ['individual', 'relay'];
        const offs = [];
        let total = 0;
        for (const d of DAYS) { offs.push(total); total += (d.end_ms - d.start_ms) / 1000; }
        const pyRound = x => {                  // round() Python: половины — к чётному
            const f = Math.floor(x), r = x - f;
            return r > 0.5 ? f + 1 : r < 0.5 ? f : (f % 2 === 0 ? f : f + 1);
        };
        const dayIndex = t => { let i = 0; while (i + 1 < offs.length && offs[i + 1] <= t) i++; return i; };
        // 1-в-1 tools/demo/siberman/timeline.py: compact_to_abs
        function compactToAbs(t) {
            if (t <= 0) return DAYS[0].start_ms;
            if (t >= total) return DAYS[DAYS.length - 1].end_ms;
            const i = dayIndex(t);
            return DAYS[i].start_ms + pyRound((t - offs[i]) * 1000);
        }
        toAbs = v => compactToAbs(v / 1000);
        restoreMoment(Number(me.dataset.startS));

        // 1-в-1 tools/demo/siberman/record.py: apply_change/state_at
        function applyChange(state, ch) {
            const out = Object.assign({}, state);
            for (const key of LISTS) {
                const byBib = new Map((state[key] || []).map(r => [r.bib, r]));
                for (const b of (ch.removed && ch.removed[key]) || []) byBib.delete(b);
                for (const r of ch[key] || []) byBib.set(r.bib, r);
                const o = ch.order && ch.order[key];
                const order = o && o.length ? o : (state[key] || []).map(r => r.bib).filter(b => byBib.has(b));
                out[key] = order.map(b => byBib.get(b));
            }
            Object.assign(out, ch.top || {});
            for (const k of ch.top_removed || []) delete out[k];
            return out;
        }
        const stateAt = cursorState(() => JSON.parse(JSON.stringify(rec.initial)), applyChange);
        const tNow = () => vline() / 1000;
        const demoUrl = linkAdapter(tNow);

        return {
            tNow,
            ready() { stateAt(tNow()); },
            fetch(u) {
                if (u.pathname === '/api/siberman/results') return recReady.then(() => json(stateAt(tNow())));
                return null;
            },
            seekForward: refreshAt,
            step() {},
            panel: () => ({ min: 0, max: rec.meta.total_s,
                            marks: rec.meta.days.map(d => ({ t: d.start_s + 600, label: d.label }))
                                .concat([{ t: rec.meta.total_s, label: 'Финиш' }]) }),
            fmt(t) {
                const day = rec.meta.days[dayIndex(t)].label.split(' · ')[0];
                return `${day}, ${hhmm(compactToAbs(t))}`;
            },
            loop: () => ({ start: rec.meta.loop_start_s ?? Number(me.dataset.startS),
                           end: rec.meta.loop_end_s ?? rec.meta.total_s + HOLD_S }),
        };
    }

    // poll, формат tools/demo/replay_poll.py (data-format="ep"): несколько эндпоинтов, одно окно,
    // шкала — секунды от выстрела: Date.now() = gun_ms + t·1000.
    function epMode() {
        const GUN_MS = Number(me.dataset.gunMs);
        const T_FROM = Number(me.dataset.tFrom), T_TO = Number(me.dataset.tTo);
        // [{re, ep, q?}]: путь ~ re → ключ записи ep ($1… из re); q — параметры query, дописываемые к ключу.
        const RULES = JSON.parse(me.dataset.endpoints || '[]').map(r => Object.assign({}, r, { rx: new RegExp(r.re) }));
        toAbs = v => GUN_MS + v;
        restoreMoment(Number(me.dataset.startS), t => Math.min(Math.max(t, T_FROM), T_TO + HOLD_S));

        // 1-в-1 tools/demo/replay_poll.py: item_key/apply_change/state_at
        const itemKey = (r, fields) => fields.map(f => String(r[f])).join(':');
        function applyNode(value, node, spec) {
            if ('=' in node) return node['='];
            if ('key' in spec) {
                const fields = spec.key, itemSpec = spec.item;
                const byKey = new Map(value.map(r => [itemKey(r, fields), r]));
                for (const k of node.x || []) byKey.delete(k);
                for (const [k, sub] of Object.entries(node.u || {})) byKey.set(k, applyNode(byKey.get(k), sub, itemSpec));
                const order = value.map(r => itemKey(r, fields)).filter(k => byKey.has(k));
                for (const r of node.a || []) { const k = itemKey(r, fields); byKey.set(k, r); order.push(k); }
                return (node.o && node.o.length ? node.o : order).map(k => byKey.get(k));
            }
            const sub = spec.fields;
            const out = Object.assign({}, value);
            for (const k of node.x || []) delete out[k];
            for (const [k, ch] of Object.entries(node.f || {})) out[k] = applyNode(out[k], ch, sub[k]);
            return out;
        }
        const stateAt = cursorState(() => Object.assign({}, rec.initial), (state, ch) => {
            const out = Object.assign({}, state);
            for (const [ep, node] of Object.entries(ch.ep)) out[ep] = applyNode(state[ep], node, rec.meta.spec[ep]);
            return out;
        });
        const tNow = () => vline() / 1000;
        const demoUrl = linkAdapter(tNow);
        function epOf(u) {
            for (const r of RULES) {
                if (!r.rx.test(u.pathname)) continue;
                const q = new URLSearchParams();
                for (const n of r.q || []) if (u.searchParams.get(n)) q.set(n, u.searchParams.get(n));
                const qs = q.toString();
                return u.pathname.replace(r.rx, r.ep) + (qs ? `?${qs}` : '');
            }
            return null;
        }

        return {
            tNow,
            ready() { stateAt(tNow()); },
            fetch(u) {
                const ep = epOf(u);
                if (ep === null) return null;
                return recReady.then(() => {
                    const s = stateAt(tNow());
                    if (ep in s) return json(s[ep]);
                    console.warn('[demo] нет в записи', ep);
                    return new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } });
                });
            },
            seekForward: refreshAt,
            step() {},
            panel: () => ({ min: rec.meta.t_from, max: rec.meta.t_to,
                            marks: rec.meta.marks.filter(k => k.t_s != null).map(k => ({ t: k.t_s, label: k.label })) }),
            fmt(t) {
                const m = Math.floor(Math.abs(t) / 60);
                const rel = t < 0 ? `до старта ${Math.ceil(-t / 60)} мин`
                    : `${Math.floor(m / 60)} ч ${String(m % 60).padStart(2, '0')} мин от старта`;
                return `${hhmm(GUN_MS + t * 1000)} · ${rel}`;
            },
            loop: () => ({ start: rec.meta.loop_start_s, end: rec.meta.t_to + HOLD_S }),
        };
    }

    const M = MODE !== 'poll' ? trackerMode() : me.dataset.format === 'ep' ? epMode() : pollMode();

    // ---------- запись ----------
    const recReady = realFetch(`${BASE}data/${RACE}.json.gz`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r; })
        .then(r => new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json())
        .then(j => { rec = j; M.ready(); start(); return j; });
    recReady.catch(showError);

    // ---------- подмена fetch ----------
    window.fetch = function (input, init) {
        const u = new URL(typeof input === 'string' ? input : input.url, location.href);
        if (u.origin === location.origin) {
            const res = M.fetch(u);
            if (res) return res;
            if (u.pathname.startsWith('/static/')) return realFetch(BASE + u.pathname.slice(1) + u.search, init);
            if (u.pathname.startsWith('/api/')) {
                console.warn('[demo] неперехваченный запрос', u.pathname);
                return Promise.resolve(new Response('{}', { status: 404 }));
            }
        }
        return realFetch(input, init);
    };

    // ---------- управление ----------
    function seek(t) {
        // Назад: кеши страницы (метки времени) остались бы «в будущем» — перезагружаем страницу.
        if (t < M.tNow()) { reloadAt(t); return; }
        M.seekForward(t);
        renderPanel();
    }
    function start() {
        whenBody().then(buildPanel);
        setInterval(tick, 250);
    }
    function tick() {
        const t = M.tNow();
        const loop = M.loop();
        if (clock.speed > 0 && t >= loop.end) { seek(loop.start); return; }
        M.step(t);
        renderPanel();
    }

    // ---------- панель ----------
    function buildPanel() {
        const m = rec.meta;
        const pn = M.panel();
        const p = document.createElement('div');
        p.className = 'demo-panel';
        p.innerHTML = `
            <button class="demo-panel__toggle" type="button"></button>
            <div class="demo-panel__body">
              <div class="demo-panel__caption">${m.caption || ''}</div>
              <div class="demo-panel__row">
                <button class="demo-panel__play" type="button"></button>
                <span class="demo-panel__time"></span>
                <div class="demo-panel__speeds">${SPEEDS.map(s => `<button type="button" data-speed="${s}">${s}×</button>`).join('')}</div>
              </div>
              <input class="demo-panel__range" type="range" min="${pn.min}" max="${pn.max}" step="1">
              <div class="demo-panel__marks">${pn.marks.map(k => `<button type="button" data-t="${k.t}">${k.label}</button>`).join('')}</div>
            </div>`;
        document.body.appendChild(p);
        el.panel = p;
        el.play = p.querySelector('.demo-panel__play');
        el.time = p.querySelector('.demo-panel__time');
        el.range = p.querySelector('.demo-panel__range');
        el.speeds = [...p.querySelectorAll('[data-speed]')];
        el.lastSpeed = clock.speed || 1;
        const toggle = p.querySelector('.demo-panel__toggle');
        const KEY = 'demo_panel_collapsed';
        let collapsed = window.matchMedia('(max-width: 600px)').matches;
        try { const s = localStorage.getItem(KEY); if (s === '1' || s === '0') collapsed = s === '1'; } catch (e) { /* нет localStorage */ }
        const applyCollapsed = () => {
            p.classList.toggle('demo-panel--collapsed', collapsed);
            toggle.textContent = collapsed ? '⏱' : '—';
            toggle.setAttribute('aria-label', collapsed ? 'Развернуть панель повтора' : 'Свернуть панель');
        };
        applyCollapsed();
        toggle.onclick = () => {
            collapsed = !collapsed;
            try { localStorage.setItem(KEY, collapsed ? '1' : '0'); } catch (e) { /* нет localStorage */ }
            applyCollapsed();
        };
        el.play.onclick = () => {
            if (clock.speed > 0) { el.lastSpeed = clock.speed; setClock(vline(), 0); }
            else setClock(vline(), el.lastSpeed);
            renderPanel();
        };
        el.speeds.forEach(b => b.onclick = () => { setClock(vline(), Number(b.dataset.speed)); renderPanel(); });
        el.range.oninput = () => { el.dragging = true; el.time.textContent = M.fmt(Number(el.range.value)); };
        el.range.onchange = () => { el.dragging = false; seek(Number(el.range.value)); };
        p.querySelectorAll('[data-t]').forEach(b => b.onclick = () => seek(Number(b.dataset.t)));
        renderPanel();
    }
    function renderPanel() {
        if (!el.panel) return;
        const t = M.tNow();
        el.play.textContent = clock.speed > 0 ? '⏸' : '▶';
        el.speeds.forEach(b => b.classList.toggle('active', Number(b.dataset.speed) === clock.speed));
        if (!el.dragging) { el.range.value = Math.round(t); el.time.textContent = M.fmt(t); }
    }
    function showError() {
        const box = document.createElement('div');
        box.className = 'demo-error';
        box.innerHTML = 'Не удалось загрузить запись гонки <button type="button">Повторить</button>';
        box.querySelector('button').onclick = () => location.reload();
        whenBody().then(() => document.body.appendChild(box));
    }
})();
