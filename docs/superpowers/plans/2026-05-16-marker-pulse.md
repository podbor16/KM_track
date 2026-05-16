# Marker Pulse & Selected Highlight — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "breathe" scale-pulse to all running markers and a scale-up + halo effect to the selected (active) marker.

**Architecture:** CSS keyframes drive all animation; `buildMarkerIcon()` stamps the correct CSS classes and a negative `animation-delay` (phase sync) onto each rebuilt icon so the 1500 ms icon-rebuild cycle never resets the visual rhythm.

**Tech Stack:** Vanilla CSS animations, Leaflet divIcon, JavaScript template strings.

---

## Files

| File | Change |
|------|--------|
| `static/css/tracker.css` | Add 4 keyframes + 5 CSS rules after line 643 |
| `static/js/tracker-map.js` | Modify `buildMarkerIcon()` (lines 159–193) |

---

## Task 1 — Add CSS keyframes and rules to `tracker.css`

**Files:**
- Modify: `static/css/tracker.css` (append after line 643)

- [ ] **Step 1.1 — Append keyframes and rules**

Open `static/css/tracker.css`. After the last line of the `/* Marker animations */` block (currently line 643: `.moving-marker { ... }`), add:

```css

/* ── Breathe pulse (running markers) ──────────────── */
@keyframes runner-breathe {
    0%, 100% { transform: scale(1); }
    50%       { transform: scale(1.12); }
}

@keyframes runner-trail-breathe-1 {
    0%, 100% { transform: translate(-50%, -50%) scale(1);    opacity: .55; }
    50%       { transform: translate(-50%, -50%) scale(1.18); opacity: .80; }
}

@keyframes runner-trail-breathe-2 {
    0%, 100% { transform: translate(-50%, -50%) scale(1);    opacity: .35; }
    50%       { transform: translate(-50%, -50%) scale(1.25); opacity: .60; }
}

/* ── Selected marker (scale-up + halo) ────────────── */
@keyframes runner-sel-scale {
    0%, 100% { transform: scale(1.25); box-shadow: 0 2px 8px rgba(0,0,0,.3), 0 0 0 0   rgba(238,45,98,.5); }
    60%       { transform: scale(1.25); box-shadow: 0 2px 8px rgba(0,0,0,.3), 0 0 0 14px rgba(238,45,98,0); }
}

.runner-marker.running .runner-circle  { animation: runner-breathe         2.2s ease-in-out infinite; }
.runner-marker.running .runner-trail-1 { animation: runner-trail-breathe-1 2.2s ease-in-out infinite; }
.runner-marker.running .runner-trail-2 { animation: runner-trail-breathe-2 2.2s ease-in-out infinite; }

.runner-marker--active                 { overflow: visible !important; }
.runner-marker--active .runner-circle  { animation: runner-sel-scale 2s ease-out infinite !important; }
```

- [ ] **Step 1.2 — Commit**

```bash
git add static/css/tracker.css
git commit -m "feat: add runner breathe-pulse and selected-marker keyframes"
```

---

## Task 2 — Update `buildMarkerIcon()` in `tracker-map.js`

**Files:**
- Modify: `static/js/tracker-map.js` — function `buildMarkerIcon(runner)` (lines 159–193)

The function currently returns a `L.divIcon` with `className: \`runner-marker runner-${runnerId}\`` and all-inline-styled inner HTML. We need to:

1. Compute status/active CSS classes.
2. Compute animation-delay values for phase sync (so icon rebuilds don't reset the animation phase).
3. Add class `runner-circle` to the inner circle div + its `animation-delay`.
4. Add classes `runner-trail-1`/`runner-trail-2` to trail dots + their `animation-delay` values.

- [ ] **Step 2.1 — Replace `buildMarkerIcon` body**

Replace the entire function with the version below. The diff from the original:
- New: `statusClass`, `activeClass`, `isActive`, `BREATHE_MS`, `SEL_MS`, phase-delay constants.
- Changed: `className` on `divIcon` now includes status + active classes.
- Changed: inner circle `<div>` gains `class="runner-circle"` and `animation-delay`.
- Changed: trail divs gain `class="runner-trail-1"` / `class="runner-trail-2"` and `animation-delay`.

```javascript
function buildMarkerIcon(runner) {
    const runnerId = String(runner.id);
    const color = getStatusColor(runner.status, runner.lap ?? 0);
    const fontSize = String(runner.start_number).length >= 3 ? '11px' : '13px';

    const anim = runnerAnimations[runnerId];
    const isActive = runnerId === activeRunnerId;
    const statusClass = anim?.status === 'running' ? 'running'
                      : anim?.status === 'finished' ? 'finished' : '';
    const activeClass = isActive ? ' runner-marker--active' : '';

    // Phase-sync: negative delay places animation at the correct point in the
    // global clock so icon rebuilds (every 1500 ms) don't reset the rhythm.
    const BREATHE_MS = 2200;
    const SEL_MS     = 2000;
    const now        = Date.now();
    const breatheDelay = -(now % BREATHE_MS);
    const trail1Delay  = breatheDelay + 150;  // trail follows circle by 150 ms
    const trail2Delay  = breatheDelay + 300;
    const selDelay     = -(now % SEL_MS);
    const circleDelay  = isActive ? selDelay : breatheDelay;

    let trailHtml = '';
    if (anim && anim.status === 'running' && anim.bearing != null) {
        const rad = anim.bearing * Math.PI / 180;
        const dx1 = -Math.sin(rad) * 26, dy1 = Math.cos(rad) * 26;
        const dx2 = -Math.sin(rad) * 44, dy2 = Math.cos(rad) * 44;
        trailHtml = `
            <div class="runner-trail-1" style="position:absolute;top:${26+dy1}px;left:${26+dx1}px;width:20px;height:20px;border-radius:50%;background:${color};opacity:0.55;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.25);transform:translate(-50%,-50%);pointer-events:none;animation-delay:${trail1Delay}ms;"></div>
            <div class="runner-trail-2" style="position:absolute;top:${26+dy2}px;left:${26+dx2}px;width:13px;height:13px;border-radius:50%;background:${color};opacity:0.35;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.2);transform:translate(-50%,-50%);pointer-events:none;animation-delay:${trail2Delay}ms;"></div>`;
    }

    return L.divIcon({
        className: `runner-marker runner-${runnerId} ${statusClass}${activeClass}`,
        html: `<div style="position:relative;width:52px;height:52px;overflow:visible;">
            ${trailHtml}
            <div class="runner-circle" style="
                position:absolute;top:0;left:0;
                background:${color};color:white;
                width:52px;height:52px;border-radius:50%;
                display:flex;align-items:center;justify-content:center;
                font-weight:bold;font-size:${fontSize};
                border:2px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.3);
                box-sizing:border-box;text-align:center;line-height:1;overflow:hidden;
                animation-delay:${circleDelay}ms;
            ">${runner.start_number}</div>
        </div>`,
        iconSize: [52, 52],
        iconAnchor: [26, 26],
        popupAnchor: [0, -28]
    });
}
```

- [ ] **Step 2.2 — Verify no syntax errors**

```powershell
node -e "const fs=require('fs'); new Function(fs.readFileSync('static/js/tracker-map.js','utf8')); console.log('OK')"
```

Expected: `OK` (no exception).

- [ ] **Step 2.3 — Commit**

```bash
git add static/js/tracker-map.js
git commit -m "feat: breathe pulse + active highlight in buildMarkerIcon"
```

---

## Task 3 — Manual verification

- [ ] **Step 3.1 — Start dev server**

```powershell
conda run -n base uvicorn src.main:app --reload --port 8000
```

- [ ] **Step 3.2 — Open tracker and check breathe**

Open `http://localhost:8000/tracker?event_id=104` in browser.
Add 2+ running markers. Observe:
- All running markers gently scale in/out (~2.2 s cycle).
- Trail dots pulse slightly in sync (with 150/300 ms cascade delay).
- No flicker or animation reset every 1.5 s.

- [ ] **Step 3.3 — Check selected highlight**

Click a marker. Observe:
- Clicked marker: visibly larger (1.25×) + pulsing pink halo shadow.
- Info panel opens.
- Other markers: continue normal breathe.

- [ ] **Step 3.4 — Check deselect**

Click the map background or a different marker. Observe:
- Previous active marker: returns to normal breathe size.
- New active marker (if clicked): shows highlight.

- [ ] **Step 3.5 — Check finished and notstarted markers**

Finished markers: no animation (static).
Not-started markers: no animation (static).

- [ ] **Step 3.6 — Check position-lerp regression**

Wait for a data refresh (~5 s). Confirm markers still glide smoothly to new positions — no regression from the lerp changes made previously.
