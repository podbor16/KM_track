import { clamp, constrainCrop } from './composition.js?v=2';

function metrics(points) {
  const [a, b] = points;
  if (!a) return null;
  return b ? { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, distance: Math.hypot(b.x - a.x, b.y - a.y) }
    : { x: a.x, y: a.y, distance: 0 };
}

export function startGesture(crop, points) {
  const center = metrics(points);
  return center ? { ...center, dx: crop.dx, dy: crop.dy, zoom: crop.zoom } : null;
}

export function applyGesture(crop, start, points) {
  const center = metrics(points);
  if (!start || !center) return false;
  // Recompute from the gesture's initial frame, not the previously clamped frame.
  // This keeps the photo point under the fingers stable regardless of event order.
  const zoom = start.distance > 0 && center.distance > 0
    ? clamp(start.zoom * center.distance / start.distance, 1, 4) : start.zoom;
  const ratio = zoom / start.zoom;
  crop.zoom = zoom;
  crop.dx = center.x - (start.x - start.dx) * ratio;
  crop.dy = center.y - (start.y - start.dy) * ratio;
  constrainCrop(crop);
  return true;
}

export function attachPhotoGestures(element, { getCrop, enabled, onChange }) {
  const pointers = new Map();
  let start = null;
  let pointerType = null;
  const options = { passive: false };

  function point(event) {
    const rect = element.getBoundingClientRect();
    const crop = getCrop();
    return { x: (event.clientX - rect.left) * crop.width / rect.width,
      y: (event.clientY - rect.top) * crop.height / rect.height };
  }

  function rebase() {
    start = startGesture(getCrop(), [...pointers.values()]);
    element.classList.toggle('is-dragging', pointers.size > 0);
    if (!pointers.size) pointerType = null;
  }

  function release(id) {
    // Some WebViews can drop capture before we get the corresponding event.
    try { if (element.hasPointerCapture(id)) element.releasePointerCapture(id); }
    catch { /* Window listeners still guarantee cleanup. */ }
  }

  function cancel() {
    const ids = [...pointers.keys()];
    pointers.clear(); start = null; pointerType = null;
    element.classList.remove('is-dragging');
    ids.forEach(release);
  }

  function down(event) {
    if (!enabled() || pointers.size >= 2 || (pointerType && pointerType !== event.pointerType)
      || (event.pointerType === 'mouse' && event.button !== 0)) return;
    if (event.cancelable) event.preventDefault();
    pointerType = event.pointerType;
    pointers.set(event.pointerId, point(event));
    try { element.setPointerCapture(event.pointerId); }
    catch { /* A window listener handles browsers that refuse pointer capture. */ }
    rebase();
  }

  function move(event) {
    if (!pointers.has(event.pointerId)) return;
    if (!enabled()) { cancel(); return; }
    if (event.pointerType === 'mouse' && !event.buttons) { end(event); return; }
    if (event.cancelable) event.preventDefault();
    pointers.set(event.pointerId, point(event));
    const points = [...pointers.values()];
    if (applyGesture(getCrop(), start, points)) onChange();
    // Coincident fingers do not provide a scale; establish it once they separate.
    if (points.length === 2 && start?.distance === 0) rebase();
  }

  function end(event) {
    if (!pointers.delete(event.pointerId)) return;
    release(event.pointerId);
    rebase();
  }

  function visibility() { if (document.hidden) cancel(); }
  function suppressContextMenu(event) { if (enabled()) event.preventDefault(); }
  element.addEventListener('pointerdown', down, options);
  // Window handlers continue dragging outside the canvas, including capture failure.
  window.addEventListener('pointermove', move, options);
  window.addEventListener('pointerup', end);
  window.addEventListener('pointercancel', end);
  element.addEventListener('lostpointercapture', end);
  element.addEventListener('contextmenu', suppressContextMenu);
  window.addEventListener('blur', cancel);
  window.addEventListener('resize', cancel);
  window.addEventListener('pagehide', cancel);
  document.addEventListener('visibilitychange', visibility);
  return { cancel };
}
