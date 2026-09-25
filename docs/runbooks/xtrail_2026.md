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
- [ ] Время старта `gun_time` (по Красноярску) в `x_trail.yaml`
- [ ] Промежуточные КТ: дистанции и координаты → `checkpoint_distances`/`checkpoints` в YAML, поля в пресете (`checkpoint_fields`), КТ в `events.checkpoint_distances` для 117
- [ ] Участники загружены в Copernico → `--inspect`, затем `--init`

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
sudo systemctl start km_race_loader@xtrail_5km
journalctl -u km_race_loader@xtrail_5km -f
```

Проверить `/tracker`, `/results` (5 км), кнопку диплома в результатах после финиша. После гонки — `systemctl stop km_race_loader@xtrail_5km` (или остановить из админки).
