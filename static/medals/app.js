import { createCrop, constrainCrop, zoomCrop, renderCertificate } from './composition.js?v=2';
import { attachPhotoGestures } from './gestures.js?v=3';
import { attachFramePicker } from './frame-picker.js?v=5';

const $ = (id) => document.getElementById(id);
const ui = Object.fromEntries(['photo-input', 'choose-button', 'choose-text', 'selected-photo', 'thumbnail', 'filename', 'quality-note', 'error-message', 'error-text', 'retry-template', 'live-status', 'preview', 'certificate-frame', 'empty-preview', 'preview-state', 'preview-badge', 'crop-controls', 'zoom', 'reset-button', 'download-button', 'download-text', 'save-description', 'export-format', 'download-result', 'open-image', 'share-button', 'edit-toggle', 'edit-toggle-text', 'save-hint', 'result-where'].map(id => [id, $(id)]));
let config;
let overlay = null;
let photo = null;
let crop = null;
let reading = false;
let exporting = false;
let selectionId = 0;
let templateId = 0;
let selectedTemplate = 0;
let templateLoading = false;
let pendingTemplateImage = null;
let revision = 0;
let animationFrame = 0;
let shareTimer;
let shareFile = null;
let downloadUrl = null;
let filename = '';
let editing = false;
// On touch screens the certificate would otherwise trap every swipe, so the photo
// moves only in an explicit edit mode and the page scrolls normally the rest of the time.
const coarsePointer = matchMedia('(pointer: coarse)');
const isIOS = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const isAndroid = /Android/i.test(navigator.userAgent);
// iOS saves downloads to «Файлы»; the share sheet's «Сохранить изображение» puts the file into «Фото».
const savesToPhotos = isIOS && typeof navigator.share === 'function' && typeof navigator.canShare === 'function';
const canEdit = () => Boolean(photo && overlay && !reading && !exporting);
const photoMovable = () => canEdit() && (editing || !coarsePointer.matches);
const gestures = attachPhotoGestures(ui.preview, {
  getCrop: () => crop,
  enabled: photoMovable,
  onChange: cropChanged,
});
const framePicker = attachFramePicker({
  track: $('frame-options'), previous: $('previous-frame'), next: $('next-frame'), counter: $('frame-counter'),
  onSelect: index => loadTemplate(index), isDisabled: () => reading || exporting,
});

function setStatus(message = '') { ui['live-status'].textContent = message; }
function clearError() { ui['error-message'].hidden = true; ui['retry-template'].hidden = true; }
function showError(message, retry = false, nearSave = false) {
  const anchor = nearSave ? ui['export-format'] : ui['quality-note'];
  anchor.insertAdjacentElement('afterend', ui['error-message']);
  ui['error-text'].textContent = message;
  ui['error-message'].hidden = false;
  ui['retry-template'].hidden = !retry;
}

function saveLabel() {
  if (exporting) return coarsePointer.matches ? 'Готовим…' : 'Готовим сертификат…';
  if (savesToPhotos) return 'Сохранить в Фото';
  return coarsePointer.matches ? 'Сохранить' : 'Скачать сертификат';
}

function updateUI() {
  const ready = canEdit();
  if (!ready) editing = false;
  const gated = coarsePointer.matches;
  const movable = photoMovable();
  document.body.classList.toggle('uses-edit-mode', gated);
  document.body.classList.toggle('is-editing', editing);
  ui['edit-toggle'].hidden = !(ready && gated);
  ui['edit-toggle'].setAttribute('aria-pressed', String(editing));
  ui['edit-toggle-text'].textContent = editing ? 'Готово' : 'Подвинуть фото';
  ui['choose-button'].disabled = reading || exporting;
  ui['choose-text'].textContent = reading ? 'Открываем фото…' : photo ? 'Заменить фото' : 'Выбрать фото';
  ui['choose-button'].classList.toggle('is-selected', Boolean(photo));
  ui['download-button'].disabled = !ready;
  ui['download-text'].textContent = saveLabel();
  ui['save-hint'].hidden = !(savesToPhotos && ready);
  ui['selected-photo'].hidden = !photo;
  ui['empty-preview'].hidden = Boolean(photo);
  ui['crop-controls'].hidden = !photo;
  ui['preview-badge'].hidden = !ready;
  ui['preview-state'].textContent = reading ? 'Открываем фото…' : !overlay ? 'Загружаем оформление…' : photo ? 'С вашим фото' : 'Осталось добавить фото';
  ui['certificate-frame'].setAttribute('aria-busy', String(reading || !overlay));
  ui.preview.classList.toggle('is-editable', movable);
  ui.preview.tabIndex = movable ? 0 : -1;
  ui.preview.setAttribute('role', movable ? 'group' : 'img');
  ui.preview.setAttribute('aria-label', photo ? 'Ваш сертификат. Можно передвинуть фото стрелками или перетаскиванием.' : 'Предпросмотр сертификата. Выберите своё фото.');
  if (photo) ui.preview.setAttribute('aria-describedby', 'keyboard-hint');
  ui.zoom.disabled = !ready;
  ui['reset-button'].disabled = !ready;
  ui['share-button'].disabled = !ready || !shareFile;
  ui['save-description'].textContent = photo ? 'Нравится результат? Скачайте готовое изображение.' : 'Сначала выберите фото — и сертификат будет готов.';
  if (config?.templates) {
    const hint = config.templates[selectedTemplate].placeholder;
    if (hint) {
      for (const [property, value] of Object.entries({ left: hint.x, top: hint.y, width: hint.width, height: hint.height })) {
        ui['certificate-frame'].style.setProperty(`--placeholder-${property}`, `${value * 100}%`);
      }
    }
    ui['certificate-frame'].classList.toggle('is-dark-empty', config.templates[selectedTemplate].emptyTone === 'dark');
    framePicker.update(selectedTemplate, { scroll: false });
    $('frame-status').textContent = templateLoading ? 'Загружаем рамку…' : config.templates[selectedTemplate].label;
    $('frame-picker').classList.toggle('is-disabled', reading || exporting);
    $('frame-picker').setAttribute('aria-disabled', String(reading || exporting));
    $('frame-loading').hidden = Boolean(overlay);
    $('frame-loading-text').textContent = templateLoading ? 'Загружаем рамку…' : 'Рамка не загрузилась. Выберите другую или повторите загрузку.';
  }
}

function draw() {
  animationFrame = 0;
  const dark = config?.templates?.[selectedTemplate]?.emptyTone === 'dark';
  try { renderCertificate(ui.preview, photo, crop, overlay, config?.width, config?.height, dark ? '#2b2d31' : '#f1f2f3'); }
  catch { showError('Не удалось показать сертификат. Попробуйте выбрать фото поменьше.'); }
}

function scheduleDraw() {
  if (!animationFrame) animationFrame = requestAnimationFrame(draw);
}

function invalidateExport() {
  revision += 1;
  shareFile = null;
  ui['share-button'].disabled = true;
  ui['download-result'].hidden = true;
  ui['open-image'].removeAttribute('href');
  if (downloadUrl) { URL.revokeObjectURL(downloadUrl); downloadUrl = null; }
  clearTimeout(shareTimer);
  if (photo && overlay && navigator.canShare && navigator.share) {
    shareTimer = setTimeout(prepareShare, 350);
  }
}

function cropChanged() {
  ui.zoom.value = String(crop.zoom);
  ui.zoom.setAttribute('aria-valuetext', `${Math.round(crop.zoom * 100)} процентов`);
  invalidateExport();
  scheduleDraw();
}

async function loadTemplate(index = selectedTemplate) {
  const id = ++templateId;
  if (pendingTemplateImage) pendingTemplateImage.src = '';
  pendingTemplateImage = null;
  selectedTemplate = Number.isInteger(index) ? index : selectedTemplate;
  templateLoading = true;
  overlay = null;
  gestures.cancel();
  invalidateExport();
  clearError();
  $('frame-error').hidden = true;
  setStatus('Загружаем оформление сертификата…');
  updateUI();
  scheduleDraw();
  try {
    if (!config) {
      const response = await fetch('./certificate.config.json', { cache: 'no-cache' });
      if (!response.ok) throw new Error('config');
      const next = await response.json();
      if (next.width !== 1080 || next.height !== 1920 || !next.overlay || next.maxFileBytes <= 0 || next.maxImageSide <= 0) throw new Error('config');
      config = next;
      if (!Array.isArray(config.templates) || !config.templates.length) {
        config.templates = [{ id: 'medal', label: 'Медаль', src: config.overlay, width: config.width, height: config.height }];
      }
      selectedTemplate = Math.max(0, Math.min(config.templates.length - 1, selectedTemplate));
      $('frame-picker').hidden = false;
      framePicker.init(config.templates);
      updateUI();
    }
    const frame = config.templates[selectedTemplate];
    const image = new Image();
    pendingTemplateImage = image;
    image.src = frame.src;
    await image.decode();
    if (image.naturalWidth !== frame.width || image.naturalHeight !== frame.height) throw new Error('size');
    if (id !== templateId) return;
    overlay = image;
    pendingTemplateImage = null;
    invalidateExport();
    setStatus();
    scheduleDraw();
  } catch {
    if (id !== templateId) return;
    if (config?.templates) $('frame-error').hidden = false;
    else showError('Не удалось загрузить оформление сертификата. Проверьте интернет и попробуйте ещё раз.', true);
    setStatus();
    ui['preview-state'].textContent = 'Оформление не загрузилось';
  } finally {
    if (id === templateId) {
      templateLoading = false;
      updateUI();
      if (!overlay) {
        ui['preview-state'].textContent = 'Оформление не загрузилось';
        ui['certificate-frame'].setAttribute('aria-busy', 'false');
      }
    }
  }
}

async function decodePhoto(file) {
  // Native decoders apply EXIF once; never manually rotate the decoded pixels.
  if (typeof createImageBitmap === 'function') {
    try { return await createImageBitmap(file, { imageOrientation: 'from-image' }); }
    catch { /* Safari may decode HEIC through HTMLImageElement only. */ }
  }
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    return image;
  } finally { URL.revokeObjectURL(url); }
}

function freeCanvas(canvas) {
  if (canvas) { canvas.width = 1; canvas.height = 1; }
}

async function selectPhoto(file) {
  if (!file) return;
  const id = ++selectionId;
  reading = true;
  gestures.cancel();
  clearError();
  setStatus('Открываем ваше фото…');
  shareFile = null;
  clearTimeout(shareTimer);
  updateUI();
  let decoded = null;
  let working = null;
  try {
    const maxBytes = config?.maxFileBytes ?? 30 * 1024 * 1024;
    if (file.size > maxBytes) throw new Error('too-large');
    const knownMime = /^image\/(jpeg|png|webp|heic|heif|heic-sequence|heif-sequence)$/i.test(file.type);
    const knownExtension = /\.(jpe?g|png|webp|heic|heif)$/i.test(file.name);
    if (!knownMime && !knownExtension) throw new Error('format');
    decoded = await decodePhoto(file);
    if (id !== selectionId) return;
    const iw = decoded.naturalWidth || decoded.width;
    const ih = decoded.naturalHeight || decoded.height;
    if (!iw || !ih) throw new Error('decode');
    const ratio = Math.min(1, (config?.maxImageSide ?? 4096) / Math.max(iw, ih));
    working = document.createElement('canvas');
    working.width = Math.max(1, Math.round(iw * ratio));
    working.height = Math.max(1, Math.round(ih * ratio));
    const ctx = working.getContext('2d');
    if (!ctx) throw new Error('memory');
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(decoded, 0, 0, working.width, working.height);
    // Read one pixel to detect browsers returning an unusable canvas under memory pressure.
    ctx.getImageData(0, 0, 1, 1);
    freeCanvas(photo);
    photo = working; working = null;
    filename = file.name;
    crop = createCrop(photo.width, photo.height, config?.width ?? 1080, config?.height ?? 1920);
    ui.filename.textContent = filename;
    ui['quality-note'].hidden = iw >= 1080 && ih >= 1920;
    const thumbnailContext = ui.thumbnail.getContext('2d');
    thumbnailContext.clearRect(0, 0, 112, 112);
    const thumbScale = Math.max(112 / photo.width, 112 / photo.height);
    thumbnailContext.drawImage(photo, (112 - photo.width * thumbScale) / 2, (112 - photo.height * thumbScale) / 2, photo.width * thumbScale, photo.height * thumbScale);
    cropChanged();
    setStatus(overlay ? 'Фото выбрано. Сертификат можно скачать.' : 'Фото выбрано. Дождитесь загрузки оформления.');
  } catch (error) {
    if (id !== selectionId) return;
    const heic = /hei[cf]/i.test(file.type + file.name);
    const message = error.message === 'too-large' ? 'Это фото больше 30 МБ. Выберите файл поменьше.'
      : error.message === 'format' || heic ? 'Не удалось открыть этот формат. Выберите JPG, PNG или WebP.'
      : error.message === 'memory' || error.name === 'QuotaExceededError' ? 'Не хватает памяти для этого фото. Закройте лишние вкладки или выберите фото поменьше.'
      : 'Не удалось открыть фото. Возможно, файл повреждён или слишком большой для устройства. Выберите другое фото.';
    showError(message);
    setStatus();
  } finally {
    decoded?.close?.();
    freeCanvas(working);
    if (id === selectionId) {
      reading = false;
      if (photo && overlay) { clearTimeout(shareTimer); shareTimer = setTimeout(prepareShare, 350); }
      updateUI();
    }
  }
}

async function makeExport() {
  if (!photo || !overlay || !crop || reading) throw new Error('not-ready');
  const canvas = document.createElement('canvas');
  canvas.width = config.width;
  canvas.height = config.height;
  try {
    renderCertificate(canvas, photo, crop, overlay, config.width, config.height);
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob(value => value?.size ? resolve(value) : reject(new Error('empty-blob')), 'image/jpeg', config.quality);
    });
    if (!['image/jpeg', 'image/png'].includes(blob.type)) throw new Error('mime');
    return blob;
  } finally { freeCanvas(canvas); }
}

function fileForBlob(blob) {
  const extension = blob.type === 'image/png' ? 'png' : 'jpg';
  return new File([blob], `${config.filename}.${extension}`, { type: blob.type });
}

async function prepareShare() {
  if (!navigator.canShare || !navigator.share || !photo || !overlay || reading || exporting) return;
  const current = revision;
  try {
    const file = fileForBlob(await makeExport());
    if (current !== revision || reading || exporting) return;
    if (navigator.canShare({ files: [file] })) {
      shareFile = file;
      ui['share-button'].hidden = savesToPhotos;
      updateUI();
    }
  } catch { /* File sharing is optional; ordinary downloading remains available. */ }
}

function showResult(file, where) {
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = URL.createObjectURL(file);
  ui['open-image'].href = downloadUrl;
  ui['export-format'].textContent = `${file.type === 'image/png' ? 'PNG' : 'JPG'} · 1080 × 1920 · бесплатно`;
  ui['result-where'].textContent = where;
  ui['result-where'].hidden = !where;
  ui['download-result'].hidden = false;
}

function startExport() {
  exporting = true;
  gestures.cancel();
  clearTimeout(shareTimer);
  clearError();
  setStatus('Готовим сертификат…');
  updateUI();
}

const exportError = 'Не удалось создать файл. Попробуйте ещё раз. Если ошибка повторяется, выберите фото поменьше.';

async function download() {
  if (!canEdit()) return;
  startExport();
  try {
    const file = fileForBlob(await makeExport());
    showResult(file, isAndroid ? 'Он сохранён в «Загрузки». Его также можно найти в Галерее, в альбоме «Download».' : '');
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = file.name;
    document.body.append(link);
    link.click();
    link.remove();
    setStatus('Сертификат готов. Если скачивание не началось, откройте изображение по ссылке ниже.');
    try {
      if (navigator.canShare?.({ files: [file] })) {
        shareFile = file;
        ui['share-button'].hidden = savesToPhotos;
      }
    } catch { /* Optional sharing must not turn a successful download into an error. */ }
  } catch {
    showError(exportError, false, true);
    setStatus();
  } finally {
    exporting = false;
    updateUI();
  }
}

async function saveToPhotos() {
  if (!canEdit()) return;
  let file = shareFile;
  if (!file) {
    // Usually prepared in advance; otherwise build it now, still within the tap's activation window.
    startExport();
    try { file = fileForBlob(await makeExport()); shareFile = file; }
    catch { showError(exportError, false, true); setStatus(); }
    finally { exporting = false; updateUI(); }
    if (!file) return;
  }
  editing = false;
  updateUI();
  try {
    if (!navigator.canShare({ files: [file] })) throw new Error('unsupported');
    await navigator.share({ files: [file] });
    showResult(file, 'Если вы выбрали «Сохранить изображение», он уже в приложении «Фото».');
    setStatus('Сертификат готов.');
  } catch (error) {
    if (error.name === 'AbortError') return;
    // The share sheet is unavailable (in-app browsers, expired activation): fall back to a file.
    await download();
  }
}

ui['choose-button'].addEventListener('click', () => ui['photo-input'].click());
ui['photo-input'].addEventListener('change', event => {
  const file = event.target.files?.[0];
  event.target.value = '';
  selectPhoto(file);
});
ui['retry-template'].addEventListener('click', loadTemplate);
$('retry-frame').addEventListener('click', () => loadTemplate());
ui.zoom.addEventListener('input', () => {
  if (!crop || reading || exporting) return;
  gestures.cancel();
  zoomCrop(crop, Number(ui.zoom.value)); cropChanged();
});
ui['reset-button'].addEventListener('click', () => {
  if (!photo || reading || exporting) return;
  gestures.cancel();
  crop = createCrop(photo.width, photo.height, config.width, config.height);
  cropChanged(); setStatus('Фото возвращено в центр.');
});
ui.preview.addEventListener('keydown', event => {
  if (!photo || !overlay || reading || exporting) return;
  const moves = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (!moves[event.key]) return;
  event.preventDefault();
  gestures.cancel();
  const step = event.shiftKey ? 60 : 15;
  crop.dx += moves[event.key][0] * step;
  crop.dy += moves[event.key][1] * step;
  constrainCrop(crop); cropChanged();
});
ui['download-button'].addEventListener('click', () => (savesToPhotos ? saveToPhotos() : download()));
ui['edit-toggle'].addEventListener('click', () => {
  if (!canEdit()) return;
  editing = !editing;
  gestures.cancel();
  updateUI();
  setStatus(editing ? 'Двигайте фото пальцем. Нажмите «Готово», когда закончите.' : 'Кадр сохранён.');
});
coarsePointer.addEventListener?.('change', () => { gestures.cancel(); updateUI(); });
ui['share-button'].addEventListener('click', async () => {
  if (!shareFile || exporting || reading) return;
  // Prepare the file earlier so share() runs directly within user activation.
  try { await navigator.share({ files: [shareFile] }); }
  catch (error) {
    if (error.name !== 'AbortError') showError('Не удалось поделиться файлом. Скачайте сертификат и отправьте его из «Загрузок».', false, true);
  }
});

window.addEventListener('pagehide', event => {
  if (event.persisted) return;
  clearTimeout(shareTimer);
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  freeCanvas(photo);
});

draw();
updateUI();
loadTemplate();
