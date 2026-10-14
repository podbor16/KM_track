# Жеребьёвка Siberman 2028 — вставка в Тильду (siberman515.com/draw2028)

Два отдельных HTML-блока **T123** («Другое → HTML-код»), по порядку на странице:
сначала «Победители», затем «Аквариум». Каждый блок самодостаточен — iframe, якорь и
скрипт автовысоты (наша страница сообщает высоту через `postMessage`, скрипт выставляет
её iframe; если скрипт есть в обоих блоках — это не мешает).

Якорные ссылки в меню/кнопках Тильды: `#draw-winners` и `#draw-aquarium`.

## Блок 1 — «Победители» (зачёты и листы ожидания)

```html
<a id="draw-winners" name="draw-winners"></a>
<iframe class="sbm-draw" src="https://live.siberman515.com/draw/2028/results" style="width:100%;border:0;height:900px" title="Жеребьёвка Siberman 2028 — победители"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanDrawHeight) return;
  document.querySelectorAll('iframe.sbm-draw').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanDrawHeight + 'px';
  });
});
</script>
```

## Блок 2 — «Аквариум»

```html
<a id="draw-aquarium" name="draw-aquarium"></a>
<iframe class="sbm-draw" src="https://live.siberman515.com/draw/2028/aquarium" style="width:100%;border:0;height:900px" title="Жеребьёвка Siberman 2028 — аквариум"></iframe>
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
