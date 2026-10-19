export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function createCrop(iw, ih, width, height) {
  const base = Math.max(width / iw, height / ih);
  return { iw, ih, width, height, base, zoom: 1,
    dx: (width - iw * base) / 2, dy: (height - ih * base) / 2 };
}

export function constrainCrop(crop) {
  crop.dx = clamp(crop.dx, crop.width - crop.iw * crop.base * crop.zoom, 0);
  crop.dy = clamp(crop.dy, crop.height - crop.ih * crop.base * crop.zoom, 0);
  return crop;
}

export function zoomCrop(crop, zoom, anchorX = crop.width / 2, anchorY = crop.height / 2) {
  const next = clamp(zoom, 1, 4);
  const ratio = next / crop.zoom;
  crop.dx = anchorX - (anchorX - crop.dx) * ratio;
  crop.dy = anchorY - (anchorY - crop.dy) * ratio;
  crop.zoom = next;
  return constrainCrop(crop);
}

// One composition for both the reduced preview and the full-size export.
export function renderCertificate(canvas, photo, crop, overlay, width = 1080, height = 1920) {
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas недоступен');
  ctx.save();
  ctx.setTransform(canvas.width / width, 0, 0, canvas.height / height, 0, 0);
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, width, height);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  if (photo && crop) {
    const scale = crop.base * crop.zoom;
    ctx.drawImage(photo, crop.dx, crop.dy, crop.iw * scale, crop.ih * scale);
  } else {
    ctx.fillStyle = '#f1f2f3';
    ctx.fillRect(0, 0, width, height);
  }
  if (overlay) ctx.drawImage(overlay, 0, 0, width, height);
  ctx.restore();
}
