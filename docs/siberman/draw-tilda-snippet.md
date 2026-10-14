# Жеребьёвка Siberman 2028 — вставка в Тильду (siberman515.com/draw2028)

Каждый блок — отдельный HTML-блок **T123** («Другое → HTML-код»). Высота подстраивается
сама: наша страница сообщает её через `postMessage`, скрипт ниже выставляет iframe.

## Блок «Аквариум»

```html
<iframe class="sbm-draw" src="https://live.siberman515.com/draw/2028/aquarium" style="width:100%;border:0;height:900px" loading="lazy" title="Жеребьёвка Siberman 2028 — аквариум"></iframe>
```

## Блок «Зачёты»

```html
<iframe class="sbm-draw" src="https://live.siberman515.com/draw/2028/results" style="width:100%;border:0;height:900px" loading="lazy" title="Жеребьёвка Siberman 2028 — зачёты"></iframe>
```

## Скрипт автовысоты — один раз на странице (в любом из двух блоков)

```html
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanDrawHeight) return;
  document.querySelectorAll('iframe.sbm-draw').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanDrawHeight + 'px';
  });
});
</script>
```

## Ссылки для vMix (режиссёр, опрос раз в 3 с)

- `https://live.siberman515.com/api/siberman/draw/2028/feed/men.json` (или `.csv`)
- `…/feed/women.json`, `…/feed/relay.json` — №, ФИ, город, раздел, статус оплаты; пустые строки до числа мест
- `…/feed/wildcard.json` — wild card в порядке объявления
- `…/feed/last.json` — последний вытянутый
