# Рейтинг и рекорды Siberman — вставка в Тильду (siberman515.com/results)

Два HTML-блока **T123** («Другое → HTML-код») — вместо ручных таблиц T431: рейтинг — на месте
блоков «Мужчины / Женщины / Эстафетные команды», рекорды — на месте «Рекорды Siberman». Каждый блок
самодостаточен: iframe, якорь и скрипт автовысоты (страница блока сообщает высоту через
`postMessage`; если скрипт есть в обоих блоках — это не мешает).

Меню «Результаты»: ссылки «Личное участие» и «Эстафетные команды» → `#hall-rating`,
«Рекорды и итоги» → `#hall-records` (старые якоря `#rec…` принадлежали удаляемым блокам).

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

Ссылки внутри блоков (страница спортсмена, карточка года) открываются в новой вкладке.
Выкладывать только вместе с планом 4 (страница спортсмена `/athlete/{id}` и `athlete/` в nginx) — иначе ссылки ФИ ведут на 404.
Данные обновляются сами: блоки читают БД (снимок на минуту), ручная правка таблиц больше не нужна.
