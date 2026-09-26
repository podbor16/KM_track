# Runbook: Забег Икс 2026 — 27 сентября 2026

**Дистанции:** 5 км (хронометраж, `db_event_id=117`), 2 км (без хронометража, `db_event_id=118`)
**Конфиг:** `config/events/x_trail.yaml` (в БД событие называется «Х Трейл», на сайте — «Забег Икс»)
**Copernico:** `race_id=--2026-13854`, событие `5km`, пресет `km_xtrail_5km_2026`
**Пресет в репо:** `config/copernico/km_xtrail_5km_2026.yaml`
**Лоадер:** `config/loader/xtrail_5km.env` → systemd `km_race_loader@xtrail_5km`
**Маршрут:** круг по Гриве, `static/map/2026/xtrail_griva.gpx` (5.18 км по GPX), старт = финиш (56.007746, 92.72311)

## Статус подготовки

- [x] race_id, событие и пресет прописаны в конфиге, дата 27.09.2026 (2026-09-25)
- [x] В БД для события 117 исправлены дистанция 10 → 5 км и КТ `[0, 5.0]`
- [x] Заявки загружены, стартовые номера из файла организатора, дипломы 5 и 2 км настроены
- [x] Пресет `km_xtrail_5km_2026` создан в Copernico (2026-09-25), отвечает пустым списком — участников ещё нет
- [x] Время старта 11:00 по Красноярску (`gunTime` в Copernico 04:00 UTC) — `gun_time` в YAML
- [x] Промежуточных КТ не будет — только старт/финиш (подтверждено 2026-09-25)
- [x] Участники загружены в Copernico (671), `--inspect` пройден: dorsal, surname, name, gender, status, category, club, start/finish (official)
- [x] Поле `birthdate` добавлено в пресет Copernico (2026-09-25), prerace_check: 6 OK, 0 FAIL
- [x] `--init` сделан пользователем через админку: в results 671 участник, номера у всех, дублей нет
- [x] Предстартовая проверка 26.09 вечером: `prerace_check --server` — 9 OK, 0 FAIL; сайт/трекер/результаты/диплом 2 км — 200
- [x] 26.09 20:30 сервис сайта перезапущен (пул соединений одного воркера был исчерпан 16:02–18:52, память 0.5 → 1.75 ГБ свободно)
- [x] Трекер без промежуточных КТ: загружены результаты X Trail 2025 (10 км, event 95, 758 строк, `scripts/import_results_xlsx.py --event-id 95`), категории 2026 сопоставлены с 2025 (`_CAT_MAP`). Темп маркеров: личный 2025 — 207 (30,8%), категория 2025 — 452 (67,4%), 6:00 — 12 (1,8%). Темп 10 км чуть медленнее 5 км — маркер может отставать и перескочить на финиш с приходом результата
- Номера в заявках расходятся с Copernico у 9 человек + Тымко Олег без номера — по решению пользователя не меняем (результаты идут по Copernico). Нет в Copernico: Овсянникова Маргарита (5 км, №672), Рязанцева Ирина (2 и 5 км без номера); Тарабанько Анна — заявка 2 км, в Copernico 5 км №532

## Когда пресет создан и в Copernico есть участники

```bash
python scripts/prerace_check.py --config config/events/x_trail.yaml --distance "5 км" --inspect
```

По выводу проверить/поправить `time_fields` и `checkpoint_fields` в пресете, затем:

```bash
python scripts/prerace_check.py --config config/events/x_trail.yaml --distance "5 км"
python load_race_results.py --config config/events/x_trail.yaml --distance "5 км" --init
```

Ожидание от `prerace_check`: все блоки OK, кроме `[E] API` (SKIP без `--server`).

## День старта

```bash
# утром, до 10:30 — чистый пул соединений и память
sudo systemctl restart km_track
# лоадер
sudo systemctl start km_race_loader@xtrail_5km
journalctl -u km_race_loader@xtrail_5km -f
# во время гонки: если счётчик растёт — sudo systemctl restart km_track (2–3 с простоя, лоадер не затрагивается)
journalctl -u km_track --since "-5 min" | grep -c "пул\|Failed getting"
```

Проверить `/tracker`, `/results` (5 км), кнопку диплома в результатах после финиша. После гонки — `systemctl stop km_race_loader@xtrail_5km` (или остановить из админки).
