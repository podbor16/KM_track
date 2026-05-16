# Runner Panel Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline-styled runner info panel with a clean, adaptive card-c design showing status pill, 3/4-col stats, last checkpoint block, ranks, and ETA with result emphasis.

**Architecture:** Two files touched — CSS adds `.card-c` component styles, JS replaces `buildPopupContent()` with card-c HTML generator and updates `showRunnerPanel()` to add the desktop modifier class. `#runner-panel` container becomes a transparent animation wrapper.

**Tech Stack:** Vanilla JS, CSS (no build step), Leaflet divIcon pattern already in project.

---

## File Map

| File | Change |
|------|--------|
| `static/css/tracker.css` | Strip visual styles from `#runner-panel`; add `.card-c` block |
| `static/js/tracker-map.js` | Replace `buildPopupContent()` (lines 236–408); update `showRunnerPanel()` (lines 410–426) |

---

### Task 1: CSS — strip `#runner-panel` and add `.card-c`

**Files:**
- Modify: `static/css/tracker.css` (lines 589–626)

No unit tests for CSS — verified visually in Task 3.

- [ ] **Step 1: Open `static/css/tracker.css`, find the `/* ── Runner panel ──` block (line 589) and replace it with the stripped container + full card-c component**

Replace from `/* ── Runner panel` through `.runner-panel__close:hover { color: #555; }` (lines 589–626) with:

```css
/* ── Runner panel ───────────────────────────────── */
#runner-panel {
    position: relative;
    margin-bottom: 14px;
    max-height: 600px;
    overflow: hidden;
    transition: max-height 0.25s ease-out, margin 0.25s ease-out;
}

#runner-panel.runner-panel--hidden {
    max-height: 0;
    margin-bottom: 0;
    overflow: hidden;
}

.runner-panel__close {
    position: absolute;
    top: 10px;
    right: 12px;
    background: none;
    border: none;
    font-size: 18px;
    color: #aaa;
    cursor: pointer;
    line-height: 1;
    padding: 0;
    z-index: 1;
}
.runner-panel__close:hover { color: #555; }

/* ── Card-C: runner panel card ──────────────────── */
.card-c {
    background: #fff;
    border-radius: 14px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.10);
    overflow: hidden;
    font-family: 'HouschkaRoundedAlt', 'Inter', Arial, sans-serif;
    padding: 14px 16px 16px;
}

/* TOP ROW */
.card-c__top {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-bottom: 12px;
    border-bottom: 2px solid #EE2D62;
}
.card-c__circle {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 900;
    color: white;
    box-shadow: 0 2px 8px rgba(238,45,98,0.35);
}
.card-c__title { flex: 1; min-width: 0; }
.card-c__name {
    font-size: 15px;
    font-weight: 700;
    color: #1a1a1a;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.card-c__sub { font-size: 11px; color: #999; margin-top: 2px; }
.card-c__pill {
    font-size: 10px;
    font-weight: 700;
    color: #EE2D62;
    background: #fff0f4;
    border: 1px solid #ffd0dc;
    padding: 3px 10px;
    border-radius: 20px;
    flex-shrink: 0;
    white-space: nowrap;
}

/* STATS GRID */
.card-c__stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    padding: 12px 0;
    gap: 4px;
    border-bottom: 1px solid #f0f0f0;
}
.card-c__stat { text-align: center; }
.card-c__stat-val {
    font-size: 15px;
    font-weight: 800;
    color: #1a1a1a;
    line-height: 1;
}
.card-c__stat-val .unit { font-size: 11px; font-weight: 500; color: #aaa; }
.card-c__stat-lbl {
    font-size: 9px;
    color: #bbb;
    text-transform: uppercase;
    letter-spacing: .5px;
    margin-top: 3px;
}
.card-c__stat--desktop-only { display: none; }

/* BODY */
.card-c__body {
    padding-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

/* KT BLOCK */
.card-c__kt-block {
    background: #fafafa;
    border-radius: 10px;
    padding: 9px 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.card-c__kt-label {
    font-size: 10px;
    color: #bbb;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: .4px;
}
.card-c__kt-name { font-size: 13px; font-weight: 700; color: #333; margin-top: 2px; }
.card-c__kt-right { text-align: right; flex-shrink: 0; }
.card-c__kt-time { font-size: 15px; font-weight: 800; color: #1a1a1a; }
.card-c__kt-pace { font-size: 11px; color: #aaa; margin-top: 2px; }

/* RANKS */
.card-c__ranks-col { display: block; }
.card-c__ranks-row { display: flex; gap: 6px; }
.card-c__rank {
    flex: 1;
    text-align: center;
    background: #f9f9f9;
    border-radius: 8px;
    padding: 7px 4px;
}
.card-c__rank-val { font-size: 12px; font-weight: 700; color: #1a1a1a; }
.card-c__rank-lbl {
    font-size: 9px;
    color: #ccc;
    text-transform: uppercase;
    margin-top: 2px;
    letter-spacing: .4px;
}

/* ETA / RESULT */
.card-c__eta {
    background: #EE2D62;
    border-radius: 10px;
    padding: 10px 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.card-c__eta-lbl { font-size: 11px; color: rgba(255,255,255,0.9); font-weight: 700; }
.card-c__eta-vals { text-align: right; flex-shrink: 0; }
.card-c__eta-val { font-size: 18px; font-weight: 800; color: #fff; line-height: 1; }
.card-c__eta-time { font-size: 11px; font-weight: 500; color: rgba(255,255,255,0.7); margin-top: 3px; }

/* ── DESKTOP modifier (added by JS when window.innerWidth >= 640) ── */
.card-c--desktop .card-c__stats-grid {
    grid-template-columns: repeat(4, 1fr);
}
.card-c--desktop .card-c__stat--desktop-only { display: block; }
.card-c--desktop .card-c__body {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 14px;
}
.card-c--desktop .card-c__ranks-col {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-self: center;
}
.card-c--desktop .card-c__kt-block { margin-bottom: 0; }
.card-c--desktop .card-c__eta {
    grid-column: 1 / -1;
    margin-top: 2px;
}
.card-c--desktop .card-c__name { font-size: 16px; }
```

- [ ] **Step 2: Commit CSS**

```bash
git add static/css/tracker.css
git commit -m "style: add card-c runner panel component, strip #runner-panel visual styles"
```

---

### Task 2: JS — replace `buildPopupContent()` and update `showRunnerPanel()`

**Files:**
- Modify: `static/js/tracker-map.js` (lines 236–426)

- [ ] **Step 1: Replace `buildPopupContent()` (lines 236–408) with the new implementation**

Delete lines 236–408 and insert:

```javascript
function buildPopupContent(runner) {
    const status = (runner.status || '').toLowerCase();
    const isRunning = status.includes('running') || status.includes('started');
    const isFinished = status.includes('finish');

    // Circle badge — same color as map marker
    const circleColor = getStatusColor(runner.status, runner.lap ?? 0);
    const numLen = String(runner.start_number).length;
    const numFontSize = numLen >= 4 ? '10px' : numLen >= 3 ? '11px' : '13px';

    // Start time string
    let startTimeStr = '';
    if (raceGunUnixMs != null) {
        const offset = runner.time_clear_start_s ?? 0;
        const startUnix = raceGunUnixMs + offset * 1000;
        startTimeStr = new Date(startUnix).toLocaleTimeString('ru-RU', {
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
    }

    const pillLabel = isFinished ? 'Финишировал' : isRunning ? 'Бежит' : 'Не стартовал';
    const subParts = [
        runner.category ? KMUtils.normalizeCategory(runner.category) : null,
        startTimeStr ? `Старт ${startTimeStr}` : null
    ].filter(Boolean);

    const topHTML = `
        <div class="card-c__top">
            <div class="card-c__circle" style="background:${circleColor};font-size:${numFontSize}">
                ${runner.start_number}
            </div>
            <div class="card-c__title">
                <div class="card-c__name">${runner.full_name}</div>
                ${subParts.length ? `<div class="card-c__sub">${subParts.join(' · ')}</div>` : ''}
            </div>
            <div class="card-c__pill">${pillLabel}</div>
        </div>`;

    // ── Not started ──────────────────────────────────
    if (!isRunning && !isFinished) {
        return `<div class="card-c">${topHTML}</div>`;
    }

    // ── Finished ─────────────────────────────────────
    if (isFinished) {
        const finishPace = runner.finish_pace_avg_gun || runner.finish_pace_avg_clean || '-';
        const distVal = eventDistance > 0 ? String(eventDistance) : '-';
        const rankAbs = runner.rank_absolute || '-';
        const clearTime = runner.time_clear_finish || '';
        const gunTime = runner.time_gun_finish || '';

        const statsHTML = `
            <div class="card-c__stats-grid">
                <div class="card-c__stat">
                    <div class="card-c__stat-val">${finishPace}</div>
                    <div class="card-c__stat-lbl">Темп</div>
                </div>
                <div class="card-c__stat">
                    <div class="card-c__stat-val">${distVal}<span class="unit"> км</span></div>
                    <div class="card-c__stat-lbl">Дистанция</div>
                </div>
                <div class="card-c__stat">
                    <div class="card-c__stat-val">${rankAbs}</div>
                    <div class="card-c__stat-lbl">Место</div>
                </div>
                <div class="card-c__stat card-c__stat--desktop-only">
                    <div class="card-c__stat-val">${clearTime || gunTime || '-'}</div>
                    <div class="card-c__stat-lbl">Чистое вр.</div>
                </div>
            </div>`;

        let ranksHTML = '';
        if (runner.rank_absolute || runner.rank_sex || runner.rank_category) {
            ranksHTML = `
                <div class="card-c__ranks-col">
                    <div class="card-c__ranks-row">
                        <div class="card-c__rank">
                            <div class="card-c__rank-val">${runner.rank_absolute || '-'}</div>
                            <div class="card-c__rank-lbl">Абсолют</div>
                        </div>
                        <div class="card-c__rank">
                            <div class="card-c__rank-val">${runner.rank_sex || '-'}</div>
                            <div class="card-c__rank-lbl">Пол</div>
                        </div>
                        <div class="card-c__rank">
                            <div class="card-c__rank-val">${runner.rank_category || '-'}</div>
                            <div class="card-c__rank-lbl">Катег.</div>
                        </div>
                    </div>
                </div>`;
        }

        const resultHTML = gunTime ? `
            <div class="card-c__eta" style="grid-column:1/-1">
                <div class="card-c__eta-lbl">Результат</div>
                <div class="card-c__eta-vals">
                    <div class="card-c__eta-val">${gunTime}</div>
                    ${clearTime ? `<div class="card-c__eta-time">чистое ${clearTime}</div>` : ''}
                </div>
            </div>` : '';

        return `<div class="card-c">${topHTML}${statsHTML}<div class="card-c__body">${ranksHTML}${resultHTML}</div></div>`;
    }

    // ── Running ──────────────────────────────────────
    const lastCP = getLastCheckpoint(runner);
    const pace = runner.current_pace || '-';
    const distCurrent = runner.current_distance != null ? Number(runner.current_distance).toFixed(1) : '?';
    const distTotal = eventDistance > 0 ? Number(eventDistance).toFixed(1) : '?';
    const rankAbs = runner.rank_absolute || '-';

    // 4th desktop stat: KT time
    let ktTimeShort = '-';
    let ktDesktopLbl = 'Время КТ';
    if (lastCP) {
        ktTimeShort = parseDuration(lastCP.time);
        ktDesktopLbl = `Время ${lastCP.name}`;
    }

    const statsHTML = `
        <div class="card-c__stats-grid">
            <div class="card-c__stat">
                <div class="card-c__stat-val">${pace}</div>
                <div class="card-c__stat-lbl">Темп</div>
            </div>
            <div class="card-c__stat">
                <div class="card-c__stat-val">${distCurrent}<span class="unit">/${distTotal}</span></div>
                <div class="card-c__stat-lbl">км</div>
            </div>
            <div class="card-c__stat">
                <div class="card-c__stat-val">${rankAbs}</div>
                <div class="card-c__stat-lbl">Место</div>
            </div>
            <div class="card-c__stat card-c__stat--desktop-only">
                <div class="card-c__stat-val">${ktTimeShort}</div>
                <div class="card-c__stat-lbl">${ktDesktopLbl}</div>
            </div>
        </div>`;

    // KT block
    let ktBlockHTML = '';
    if (lastCP) {
        const ktDist = eventCheckpoints[lastCP.cpIdx]?.distance_km ?? 0;
        const ktSecs = durationToSeconds(lastCP.time);
        let ktPaceStr = '';
        if (ktSecs > 0 && ktDist > 0) {
            const spk = ktSecs / ktDist;
            ktPaceStr = `${Math.floor(spk / 60)}:${String(Math.round(spk % 60)).padStart(2, '0')} мин/км`;
        }
        ktBlockHTML = `
            <div class="card-c__kt-block">
                <div class="card-c__kt-left">
                    <div class="card-c__kt-label">Последняя КТ</div>
                    <div class="card-c__kt-name">${lastCP.name}${ktDist > 0 ? ` · ${ktDist} км` : ''}</div>
                </div>
                <div class="card-c__kt-right">
                    <div class="card-c__kt-time">${parseDuration(lastCP.time)}</div>
                    ${ktPaceStr ? `<div class="card-c__kt-pace">${ktPaceStr}</div>` : ''}
                </div>
            </div>`;
    }

    // Ranks on last KT
    let ranksHTML = '';
    if (lastCP) {
        const ranks = getKtRanks(runner, lastCP.code);
        if (ranks) {
            ranksHTML = `
                <div class="card-c__ranks-col">
                    <div class="card-c__ranks-row">
                        <div class="card-c__rank">
                            <div class="card-c__rank-val">${ranks.absolute ?? '-'}</div>
                            <div class="card-c__rank-lbl">Абсолют</div>
                        </div>
                        <div class="card-c__rank">
                            <div class="card-c__rank-val">${ranks.sex ?? '-'}</div>
                            <div class="card-c__rank-lbl">Пол</div>
                        </div>
                        <div class="card-c__rank">
                            <div class="card-c__rank-val">${ranks.category ?? '-'}</div>
                            <div class="card-c__rank-lbl">Катег.</div>
                        </div>
                    </div>
                </div>`;
        }
    }

    // ETA
    let etaHTML = '';
    const hasStarted = runner.status && !['Not started', 'notstarted'].includes(runner.status);
    let finishEtaMs = null;
    if (hasStarted && lastCP && eventDistance > 0) {
        const ktSecs = durationToSeconds(lastCP.time);
        const ktDist = eventCheckpoints[lastCP.cpIdx]?.distance_km ?? 0;
        if (ktDist > 0 && ktSecs > 0) {
            const remaining_km = eventDistance - ktDist;
            if (remaining_km > 0) {
                const secsPerKm = ktSecs / ktDist;
                const baseMs = runner.last_kt_unix_ms || serverTimeUnix;
                finishEtaMs = baseMs + remaining_km * secsPerKm * 1000;
            }
        }
    } else if (hasStarted && runner.speed > 0 && eventDistance > 0 && raceGunUnixMs) {
        const startUnixMs = raceGunUnixMs + (runner.time_clear_start_s ?? 0) * 1000;
        finishEtaMs = startUnixMs + (eventDistance / runner.speed) * 3_600_000;
    }

    if (finishEtaMs) {
        const astroStr = new Date(finishEtaMs).toLocaleTimeString('ru-RU', {
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
        let resultStr = '';
        if (raceGunUnixMs) {
            const res_s = Math.round((finishEtaMs - raceGunUnixMs) / 1000);
            if (res_s > 0) {
                const rh = Math.floor(res_s / 3600);
                const rm = Math.floor((res_s % 3600) / 60);
                const rs = res_s % 60;
                resultStr = rh > 0
                    ? `${rh}:${String(rm).padStart(2,'0')}:${String(rs).padStart(2,'0')}`
                    : `${rm}:${String(rs).padStart(2,'0')}`;
            }
        }
        etaHTML = `
            <div class="card-c__eta" style="grid-column:1/-1">
                <div class="card-c__eta-lbl">Прогноз финиша</div>
                <div class="card-c__eta-vals">
                    <div class="card-c__eta-val">${resultStr || astroStr}</div>
                    ${resultStr ? `<div class="card-c__eta-time">финиш в ${astroStr}</div>` : ''}
                </div>
            </div>`;
    }

    return `<div class="card-c">${topHTML}${statsHTML}<div class="card-c__body">${ktBlockHTML}${ranksHTML}${etaHTML}</div></div>`;
}
```

- [ ] **Step 2: Update `showRunnerPanel()` (lines 410–426) — add desktop modifier class**

Replace the body of `showRunnerPanel()`:

```javascript
function showRunnerPanel(runner) {
    // Reset z-index of previous active marker
    if (activeRunnerId && runnerMarkers[activeRunnerId]) {
        runnerMarkers[activeRunnerId].setZIndexOffset(0);
    }

    const panel = document.getElementById('runner-panel');
    const content = document.getElementById('runner-panel-content');
    content.innerHTML = buildPopupContent(runner);

    // Apply desktop layout modifier
    const card = content.querySelector('.card-c');
    if (card) {
        card.classList.toggle('card-c--desktop', window.innerWidth >= 640);
    }

    panel.classList.remove('runner-panel--hidden');
    activeRunnerId = String(runner.id);
    updateSelectedList();

    // Elevate selected marker
    const marker = runnerMarkers[activeRunnerId];
    if (marker) marker.setZIndexOffset(1000);
}
```

- [ ] **Step 3: Commit JS**

```bash
git add static/js/tracker-map.js
git commit -m "feat: runner panel redesign — card-c layout with adaptive stats, KT block, ranks, ETA"
```

---

### Task 3: Manual verification

**No files to modify — browser testing only.**

- [ ] **Step 1: Start dev server**

```bash
conda run -n base python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Open tracker and test running participant**

Open `http://localhost:8000/tracker?event_id=<real_event_id>`, click a running marker.

Expected:
- White rounded card with pink bottom border on top row
- Circle badge with start number in marker color
- Name + category + start time sub-line + «Бежит» pill
- 3 stats (темп / дистанция XX.X/YY.Y / место)
- КТ block with last checkpoint name, distance, time, pace
- Ranks row (Абсолют / Пол / Катег.)
- Pink ETA strip: result time large, «финиш в HH:MM:SS» small

- [ ] **Step 3: Test desktop layout**

Expand browser to ≥ 640px width. Reclick a running marker.

Expected:
- 4 stats (adds КТ time in 4th cell)
- Body becomes 2 columns: KT block left, ranks right (vertically centered)
- ETA spans full width at bottom

- [ ] **Step 4: Test finished participant**

Click a finished marker.

Expected:
- «Финишировал» pill (gray or pink)
- Stats: финишный темп / дистанция / место абсолют
- Ranks row with finish ranks
- Pink strip labeled «Результат» with `time_gun_finish` large + `time_clear_finish` small

- [ ] **Step 5: Test not-started participant**

Click a not-started marker.

Expected:
- «Не стартовал» pill
- No stats, no KT block, no ranks, no ETA

- [ ] **Step 6: Test mobile layout**

Open DevTools → Toggle device toolbar → iPhone SE (375px). Click any running marker.

Expected:
- 3-col stats (no 4th КТ time cell)
- Single-column body (KT → ranks → ETA stacked)
