# Рейтинг, рекорды, статистика и география Siberman — вставка в Тильду (siberman515.com/results)

Четыре HTML-блока **T123** («Другое → HTML-код») — вместо ручных таблиц T431: рейтинг — на месте
блоков «Мужчины / Женщины / Эстафетные команды», рекорды — на месте «Рекорды Siberman», статистика —
на месте блока «Siberman в цифрах», география — на месте «География участников». Каждый блок
самодостаточен: iframe, якорь и скрипт автовысоты (страница блока сообщает высоту через
`postMessage`; если скрипт есть в нескольких блоках — это не мешает).

Меню «Результаты»: ссылки «Личное участие» и «Эстафетные команды» → `#hall-rating`,
«Рекорды и итоги» → `#hall-records` (старые якоря `#rec…` принадлежали удаляемым блокам);
статистика и география — якоря `#hall-stats`, `#hall-geo` (если в меню есть отдельные пункты).

## Блок 1 — «Рейтинг»

```html
<a id="hall-rating" name="hall-rating"></a>
<iframe class="sbm-hall" src="https://live.siberman515.com/hall/rating" style="width:100%;border:0;height:1200px" title="Siberman — рейтинг за все годы"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanHallHeight) return;
  document.querySelectorAll('iframe.sbm-hall').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanHallHeight + 'px';
  });
});
</script>
```

## Блок 2 — «Рекорды»

```html
<a id="hall-records" name="hall-records"></a>
<iframe class="sbm-hall" src="https://live.siberman515.com/hall/records" style="width:100%;border:0;height:900px" title="Siberman — рекорды"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanHallHeight) return;
  document.querySelectorAll('iframe.sbm-hall').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanHallHeight + 'px';
  });
});
</script>
```

## Блок 3 — «Статистика»

```html
<a id="hall-stats" name="hall-stats"></a>
<iframe class="sbm-hall" src="https://live.siberman515.com/hall/stats" style="width:100%;border:0;height:900px" title="Siberman в цифрах"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanHallHeight) return;
  document.querySelectorAll('iframe.sbm-hall').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanHallHeight + 'px';
  });
});
</script>
```

## Блок 4 — «География»

```html
<a id="hall-geo" name="hall-geo"></a>
<iframe class="sbm-hall" src="https://live.siberman515.com/hall/geo" style="width:100%;border:0;height:800px" title="Siberman — география участников"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanHallHeight) return;
  document.querySelectorAll('iframe.sbm-hall').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanHallHeight + 'px';
  });
});
</script>
```

Ссылки внутри блоков открываются в новой вкладке: ФИ — страница спортсмена `https://live.siberman515.com/athlete/{личный стартовый номер}` (у тех, кто бегал только в эстафете, — `/athlete/r{id}`) (все годы, медали, рекорды), время и команда — карточка года. Планы 2–4 выкладываются вместе.
Данные обновляются сами: блоки читают БД (снимок на минуту), ручная правка таблиц больше не нужна.
