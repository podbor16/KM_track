// Публичные блоки жеребьёвки (iframe в Тильде): опрос состояния и высота для страницы Тильды.
const DRAW_POLL_MS = 3000;
const DRAW_FETCH_TIMEOUT_MS = 10000;

function drawEscape(s) {
  return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function drawPoll(year, render) {
  let lastBody = null;
  async function tick() {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), DRAW_FETCH_TIMEOUT_MS); // зависший запрос не должен останавливать опрос
    try {
      const r = await fetch(`/api/siberman/draw/${year}/state`, { cache: 'no-store', signal: ctl.signal });
      if (r.ok) {
        const body = await r.text();
        if (body !== lastBody) { lastBody = body; render(JSON.parse(body)); }
      }
    } catch (e) { /* сеть моргнула или таймаут — следующий опрос */ }
    clearTimeout(timer);
    setTimeout(tick, DRAW_POLL_MS);
  }
  tick();
}

// Высота содержимого → странице Тильды (скрипт вставки — docs/siberman/draw-tilda-snippet.md)
(function () {
  if (window.parent === window) return;
  // documentElement.scrollHeight не меньше высоты окна iframe — iframe не сжимался бы; меряем сам контент
  const box = document.querySelector('.draw') || document.body;
  const height = () => (box === document.body ? document.body.scrollHeight : Math.ceil(box.getBoundingClientRect().height));
  const send = () => window.parent.postMessage({ sibermanDrawHeight: height() }, '*');
  new ResizeObserver(send).observe(box);
  window.addEventListener('load', send);
  // скрипт-слушатель на странице Тильды может подключиться позже iframe — первое сообщение теряется
  setInterval(send, 2000);
})();
