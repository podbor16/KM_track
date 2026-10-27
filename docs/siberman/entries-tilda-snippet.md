# Список заявок Siberman — вставка в Тильду (siberman515.com/{год}_applications)

1. Скопировать страницу `2028_applications` → `2029_applications` (шапка, меню, заголовок «Siberman 2029»).
2. Удалить блоки «Список заявок обновляется каждый понедельник», «Последнее обновление…», легенду и таблицу.
3. На их место — HTML-блок **T123** («Другое → HTML-код»):

```html
<iframe class="sbm-hall" src="https://live.siberman515.com/entries/2029" style="width:100%;border:0;height:1500px" title="Siberman 2029 — заявки"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanHallHeight) return;
  document.querySelectorAll('iframe.sbm-hall').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanHallHeight + 'px';
  });
});
</script>
```

## Вебхук в форме заявок

Тильда → настройки сайта → Формы → «Webhook» → адрес из админки (`/admin/draw?year=2029` → «Заявки» →
«Скопировать адрес вебхука»). Отметить «Отправлять данные …» в формате по умолчанию (x-www-form-urlencoded).
В настройках блока формы на странице заявки включить этот приёмник рядом с Tilda CRM. При подключении Тильда
шлёт тестовый запрос — сервер отвечает «ok», заявка не создаётся. Проверка: отправить тестовую заявку с
сайта → она появилась во вкладке «Заявки» со статусом ⌛️ → поставить ❌ и комментарий «тест».
