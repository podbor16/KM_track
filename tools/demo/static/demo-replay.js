// Демо «Повтор гонки»: виртуальные часы + подмена fetch/EventSource поверх tracker-*.js.
// Подключается в <head> ДО скриптов трекера (через демо-версию krasmarafon/analytics.html).
(function () {
    'use strict';
    const me = document.currentScript;
    const BASE = me.dataset.base;        // '/race-tracker-demo/'
    const RACE = me.dataset.race;        // 'zhara_21'
    const RealDate = Date;
    const realFetch = window.fetch.bind(window);
    const RealES = window.EventSource;
    const whenBody = () => document.body ? Promise.resolve()
        : new Promise(r => document.addEventListener('DOMContentLoaded', r));

    // ---------- виртуальные часы ----------
    const clock = { v: RealDate.now(), r: performance.now(), speed: 1 };
    const vnow = () => clock.v + (performance.now() - clock.r) * clock.speed;
    function setClock(v, speed) {
        clock.v = v; clock.r = performance.now();
        if (speed !== undefined) clock.speed = speed;
    }
    class VDate extends RealDate {
        constructor(...a) { if (a.length === 0) super(vnow()); else super(...a); }
        static now() { return vnow(); }
    }
    window.Date = VDate;

    // ---------- запись ----------
    let rec = null;
    const recReady = realFetch(`${BASE}data/${RACE}.json.gz`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r; })
        .then(r => new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json())
        .then(j => { rec = j; start(); return j; });
    recReady.catch(showError);

    const tRace = () => (vnow() - rec.meta.gun_unix_ms) / 1000;
    const st = { byId: new Map(), cursor: 0, lastStep: null, sentDist: new Map() };

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

    // ---------- подмена fetch ----------
    const json = obj => new Response(JSON.stringify(obj), { headers: { 'Content-Type': 'application/json' } });
    window.fetch = function (input, init) {
        const u = new URL(typeof input === 'string' ? input : input.url, location.href);
        if (u.origin === location.origin) {
            if (u.pathname === '/api/current-event') return recReady.then(r => json(r.meta.current_event));
            if (u.pathname === '/api/event-results') return recReady.then(() => json(snapshot(undefined)));
            if (u.pathname.startsWith('/static/')) return realFetch(BASE + u.pathname.slice(1) + u.search, init);
            if (u.pathname.startsWith('/api/')) {
                console.warn('[demo] неперехваченный запрос', u.pathname);
                return Promise.resolve(new Response('{}', { status: 404 }));
            }
        }
        return realFetch(input, init);
    };

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

    // ---------- управление ----------
    function seek(t) {
        setClock(rec.meta.gun_unix_ms + t * 1000);
        resetTo(t);
        st.lastStep = Math.floor(t / rec.meta.step_s);
        sources.forEach(s => s._send(snapshot(true)));
        renderPanel();
    }
    function parseT(v) {
        if (!v) return null;
        const m = /^(\d+)(m?)$/.exec(v);
        return m ? Number(m[1]) * (m[2] ? 60 : 1) : null;
    }
    function start() {
        const q = new URLSearchParams(location.search);
        const t0 = parseT(q.get('t')) ?? rec.meta.loop_start_s;
        const speed = [1, 2, 5, 10].includes(Number(q.get('speed'))) ? Number(q.get('speed')) : 1;
        setClock(rec.meta.gun_unix_ms + t0 * 1000, speed);
        resetTo(t0);
        st.lastStep = Math.floor(t0 / rec.meta.step_s);
        whenBody().then(buildPanel);
        setInterval(tick, 250);
    }
    function tick() {
        const t = tRace();
        if (clock.speed > 0 && t >= rec.meta.loop_end_s) { seek(rec.meta.loop_start_s); return; }
        const step = Math.floor(t / rec.meta.step_s);
        if (step !== st.lastStep) {
            st.lastStep = step;
            const d = delta(t);
            if (d.results.length) sources.forEach(s => s._send(d));
        }
        renderPanel();
    }

    // ---------- панель ----------
    const el = {};
    const fmt = s => {
        const sign = s < 0 ? '−' : ''; s = Math.abs(Math.floor(s));
        return `${sign}${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    };
    function buildPanel() {
        const m = rec.meta;
        const p = document.createElement('div');
        p.className = 'demo-panel';
        p.innerHTML = `
            <button class="demo-panel__toggle" type="button" aria-label="Панель повтора">⏱</button>
            <div class="demo-panel__body">
              <div class="demo-panel__caption">${m.caption}</div>
              <div class="demo-panel__row">
                <button class="demo-panel__play" type="button"></button>
                <span class="demo-panel__time"></span>
                <div class="demo-panel__speeds">${[1, 2, 5, 10].map(s => `<button type="button" data-speed="${s}">${s}×</button>`).join('')}</div>
              </div>
              <input class="demo-panel__range" type="range" min="${m.t_from}" max="${m.t_to}" step="1">
              <div class="demo-panel__marks">${m.marks.map(k => `<button type="button" data-t="${k.t_s}">${k.label}</button>`).join('')}</div>
            </div>`;
        document.body.appendChild(p);
        el.panel = p;
        el.play = p.querySelector('.demo-panel__play');
        el.time = p.querySelector('.demo-panel__time');
        el.range = p.querySelector('.demo-panel__range');
        el.speeds = [...p.querySelectorAll('[data-speed]')];
        el.lastSpeed = clock.speed || 1;
        p.querySelector('.demo-panel__toggle').onclick = () => p.classList.toggle('demo-panel--open');
        el.play.onclick = () => {
            if (clock.speed > 0) { el.lastSpeed = clock.speed; setClock(vnow(), 0); }
            else setClock(vnow(), el.lastSpeed);
            renderPanel();
        };
        el.speeds.forEach(b => b.onclick = () => { setClock(vnow(), Number(b.dataset.speed)); renderPanel(); });
        el.range.oninput = () => { el.dragging = true; el.time.textContent = fmt(Number(el.range.value)); };
        el.range.onchange = () => { el.dragging = false; seek(Number(el.range.value)); };
        p.querySelectorAll('[data-t]').forEach(b => b.onclick = () => seek(Number(b.dataset.t)));
        renderPanel();
    }
    function renderPanel() {
        if (!el.panel) return;
        const t = tRace();
        el.play.textContent = clock.speed > 0 ? '⏸' : '▶';
        el.speeds.forEach(b => b.classList.toggle('active', Number(b.dataset.speed) === clock.speed));
        if (!el.dragging) { el.range.value = Math.round(t); el.time.textContent = fmt(t); }
    }
    function showError() {
        const box = document.createElement('div');
        box.className = 'demo-error';
        box.innerHTML = 'Не удалось загрузить запись гонки <button type="button">Повторить</button>';
        box.querySelector('button').onclick = () => location.reload();
        whenBody().then(() => document.body.appendChild(box));
    }
})();
