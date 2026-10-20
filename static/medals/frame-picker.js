// Native horizontal scrolling provides inertia and scroll snapping on phones.
// Keep this separate from photo gestures: a swipe on the photo still moves it.
export function attachFramePicker({ track, previous, next, counter, onSelect, isDisabled }) {
  let frames = [];
  let selected = 0;
  let scrollTimer;
  let programmaticTarget = null;

  function reveal(index) {
    const button = track.children[index];
    if (!button) return;
    programmaticTarget = index;
    const box = button.getBoundingClientRect();
    const viewport = track.getBoundingClientRect();
    const padding = parseFloat(getComputedStyle(track).paddingLeft) || 0;
    track.scrollTo({ left: track.scrollLeft + box.left - viewport.left - padding, behavior: 'instant' });
  }

  function update(index, { scroll = true } = {}) {
    selected = index;
    [...track.children].forEach((button, i) => {
      button.setAttribute('aria-pressed', String(i === index));
      button.classList.toggle('is-selected', i === index);
      button.disabled = isDisabled();
    });
    counter.textContent = `${index + 1} из ${frames.length}`;
    previous.disabled = isDisabled() || index === 0;
    next.disabled = isDisabled() || index === frames.length - 1;
    if (scroll) reveal(index);
  }

  function select(index, options) {
    if (isDisabled() || index < 0 || index >= frames.length) return;
    if (index !== selected) onSelect(index);
    update(index, options);
  }

  function settled() {
    clearTimeout(scrollTimer);
    if (!frames.length) return;
    const viewport = track.getBoundingClientRect();
    const leading = viewport.left + (parseFloat(getComputedStyle(track).paddingLeft) || 0);
    let closest = 0, distance = Infinity;
    [...track.children].forEach((button, index) => {
      const box = button.getBoundingClientRect();
      const delta = Math.abs(box.left - leading);
      if (delta < distance) { closest = index; distance = delta; }
    });
    if (programmaticTarget !== null) {
      programmaticTarget = null;
      return;
    }
    const maxScroll = track.scrollWidth - track.clientWidth;
    if (maxScroll > 1 && track.scrollLeft >= maxScroll - 2) closest = frames.length - 1;
    select(closest, { scroll: false });
  }

  track.addEventListener('scroll', () => { clearTimeout(scrollTimer); scrollTimer = setTimeout(settled, 160); }, { passive: true });
  track.addEventListener('scrollend', settled);
  track.addEventListener('pointerdown', () => { programmaticTarget = null; });
  track.addEventListener('wheel', () => { programmaticTarget = null; }, { passive: true });
  track.addEventListener('keydown', event => {
    const direction = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0;
    if (!direction) return;
    event.preventDefault();
    const index = Math.max(0, Math.min(frames.length - 1, selected + direction));
    select(index);
    track.children[index]?.focus({ preventScroll: true });
  });
  previous.addEventListener('click', () => select(selected - 1));
  next.addEventListener('click', () => select(selected + 1));
  window.addEventListener('resize', () => reveal(selected));

  return {
    update,
    init(items) {
      frames = items;
      track.replaceChildren(...items.map((frame, index) => {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'frame-option';
        button.setAttribute('aria-label', `Рамка «${frame.label}», ${index + 1} из ${items.length}`);
        const image = document.createElement('img');
        image.src = frame.thumbnail || frame.src; image.alt = ''; image.width = 72; image.height = 128;
        image.loading = 'lazy'; image.draggable = false;
        const label = document.createElement('span'); label.textContent = frame.label;
        button.append(image, label);
        button.addEventListener('click', () => select(index));
        return button;
      }));
      update(0);
    },
  };
}
