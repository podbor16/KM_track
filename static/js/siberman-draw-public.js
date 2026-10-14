// Публичные блоки жеребьёвки (iframe в Тильде): опрос состояния и высота для страницы Тильды.
const DRAW_POLL_MS = 3000;

function drawEscape(s) {
  return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function drawPoll(year, render) {
  let lastBody = null;
  async function tick() {
    try {
      const r = await fetch(`/api/siberman/draw/${year}/state`, { cache: 'no-store' });
      if (r.ok) {
        const body = await r.text();
        if (body !== lastBody) { lastBody = body; render(JSON.parse(body)); }
      }
    } catch (e) { /* сеть моргнула — следующий опрос */ }
    setTimeout(tick, DRAW_POLL_MS);
  }
  tick();
}

// Высота содержимого → странице Тильды (скрипт вставки — docs/siberman/draw-tilda-snippet.md)
(function () {
  if (window.parent === window) return;
  const send = () => window.parent.postMessage({ sibermanDrawHeight: document.documentElement.scrollHeight }, '*');
  new ResizeObserver(send).observe(document.body);
  window.addEventListener('load', send);
  // скрипт-слушатель на странице Тильды может подключиться позже iframe — первое сообщение теряется
  setInterval(send, 2000);
})();
