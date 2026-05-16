# Spec: Pulse animation & selected-marker highlight

## Context

Runner markers on the Leaflet tracker currently sit static between data refreshes. Two enhancements:
1. **Breathe pulse** — all running markers gently scale in/out to signal live motion.
2. **Selected highlight** — clicking a marker opens the info panel and visually distinguishes that runner with a larger, pulsing-halo version of the marker.

## Constraints

- Icon is rebuilt every 1500 ms (in `updateTrails()`) which resets CSS animations — must compensate with **animation-delay phase sync**.
- No backend changes; frontend only: `static/js/tracker-map.js` + `static/css/tracker.css`.
- Must not break the existing snap-to-checkpoint logic or the smooth-position lerp added previously.

---

## 1. CSS keyframes (`tracker.css`)

Add four new keyframes (keep existing `pulse`/`slow-pulse` intact — they are unused but harmless):

```css
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

/* Active: locked at 1.25× + shadow halo pulse */
@keyframes runner-sel-scale {
  0%, 100% { transform: scale(1.25); box-shadow: 0 2px 8px rgba(0,0,0,.3), 0 0 0 0   rgba(238,45,98,.5); }
  60%       { transform: scale(1.25); box-shadow: 0 2px 8px rgba(0,0,0,.3), 0 0 0 14px rgba(238,45,98,0); }
}
```

Add CSS rules:

```css
/* Breathe for all running markers */
.runner-marker.running .runner-circle   { animation: runner-breathe         2.2s ease-in-out infinite; }
.runner-marker.running .runner-trail-1  { animation: runner-trail-breathe-1 2.2s ease-in-out infinite; }
.runner-marker.running .runner-trail-2  { animation: runner-trail-breathe-2 2.2s ease-in-out infinite; }

/* Selected override — scale(1.25) + halo, no clipping */
.runner-marker--active                  { overflow: visible !important; }
.runner-marker--active .runner-circle   { animation: runner-sel-scale 2s ease-out infinite !important; }
```

---

## 2. `buildMarkerIcon(runner)` changes (`tracker-map.js`)

### 2a. className — add status + active flags

```javascript
const runnerId = String(runner.id);
const anim = runnerAnimations[runnerId];
const statusClass = anim?.status === 'running' ? 'running'
                  : anim?.status === 'finished' ? 'finished' : '';
const activeClass = runnerId === activeRunnerId ? ' runner-marker--active' : '';

// divIcon className:
className: `runner-marker runner-${runnerId} ${statusClass}${activeClass}`
```

### 2b. Animation-delay phase sync

Icon rebuilds every 1500 ms reset CSS animations. Fix by computing negative delay that places the animation at the correct phase in a global clock:

```javascript
const BREATHE_MS = 2200;
const SEL_MS = 2000;
const now = Date.now();
const breatheDelay  = -(now % BREATHE_MS);
const trail1Delay   = breatheDelay + 150;   // trail follows circle by 150 ms
const trail2Delay   = breatheDelay + 300;   // trail-2 follows by 300 ms
const selDelay      = -(now % SEL_MS);
```

### 2c. Add CSS classes + delays to HTML template

**Inner circle** — add class `runner-circle` and inline `animation-delay`:

```html
<div class="runner-circle" style="
    position:absolute;top:0;left:0;
    background:${color};color:white;
    width:52px;height:52px;border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    font-weight:bold;font-size:${fontSize};
    border:2px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.3);
    box-sizing:border-box;text-align:center;line-height:1;overflow:hidden;
    animation-delay:${isActive ? selDelay : breatheDelay}ms;
">${runner.start_number}</div>
```

**Trail dots** — add classes `runner-trail-1`/`runner-trail-2` and their delays:

```html
<div class="runner-trail-1" style="position:absolute;top:${26+dy1}px;left:${26+dx1}px;
    width:20px;height:20px;border-radius:50%;background:${color};
    opacity:0.55;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.25);
    transform:translate(-50%,-50%);pointer-events:none;
    animation-delay:${trail1Delay}ms;"></div>
<div class="runner-trail-2" style="position:absolute;top:${26+dy2}px;left:${26+dx2}px;
    width:13px;height:13px;border-radius:50%;background:${color};
    opacity:0.35;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.2);
    transform:translate(-50%,-50%);pointer-events:none;
    animation-delay:${trail2Delay}ms;"></div>
```

---

## 3. Behaviour summary

| State | Effect |
|-------|--------|
| `notstarted` | No animation |
| `running` | Breathe: scale 1→1.12→1 @ 2.2s; trails scale+opacity in cascade |
| `finished` | No animation |
| `running` + selected | Breathe replaced by scale(1.25) + halo pulse @ 2s; z-index 1000 (existing) |

---

## Verification

1. Run dev server: `uvicorn src.main:app --reload`
2. Open tracker, add 2+ running markers
3. All running markers breathe in sync (same phase, no flicker on 1.5s rebuild cycle)
4. Click a marker → info panel opens + marker visibly larger with pulsing halo
5. Click another marker (or map) → previous marker returns to normal breathe
6. Finished markers: no animation
7. Confirm no position-lerp regression (markers still glide smoothly on data refresh)
