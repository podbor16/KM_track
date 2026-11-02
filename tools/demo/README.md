# Демо «Повтор гонки»

Статический сайт https://podbor16.github.io/race-tracker-demo/ — прошедшая гонка
проигрывается в настоящем трекере Красмарафона так, будто идёт сейчас. Спека:
`docs/superpowers/specs/2026-11-01-race-replay-demo-design.md`.

## Собрать

```
python tools/demo/build.py zhara_21 zhara_5
python -m http.server -d dist 8765   # → http://localhost:8765/race-tracker-demo/
```

- Только локальная БД (`.env.local`, MySQL80 :3308, снимок прода) — сборка
  откажется работать с другой.
- Нужен `static/lib/leaflet-1.9.4` (не в git: `deploy/download_static_libs.py`).
- ~5 мин на гонку. Сборка падает, если в результате нашлись реальные фамилии,
  битые ссылки или неперехваченные `/api/`.

## Опубликовать

```
python tools/demo/publish.py
```

Коммитит `dist/race-tracker-demo/` в `podbor16/race-tracker-demo` (ветка `main`,
GitHub Pages обновляется за 1–2 мин).

## Добавить гонку Красмарафона

1. Итоговые результаты гонки есть в локальной БД (обновить снимок — см. память
   `reference-local-db`).
2. Запись в `tools/demo/races.py`: `slug`, `config_code` (YAML в `config/events/`),
   `db_event_id`, `title`, `caption`, `kind`, при необходимости `loop_start_s`
   (момент начала повтора — раньше первого финиша).
3. Пересобрать со всеми гонками и опубликовать.

## Как устроено

- `source.py` берёт результаты из БД, `anonymize.py` заменяет ФИО, удаляет ДР и
  перемешивает номера. `timeline.py` строит строки «как в момент T», `record.py`
  шагом 5 с прогоняет их через прод-функцию `assemble_event_results` и пишет
  запись: начальный снимок + изменения + ломаная пройденной дистанции.
- `site.py` рендерит прод-шаблон `tracker.html`, подменяя шапку, Метрику и футер
  шаблонами из `tools/demo/templates/`.
- `static/demo-replay.js` подменяет в браузере `Date` (время гонки задаётся
  в странице до кода трекера), `fetch` и `EventSource`, рисует панель
  повтора. Перемотка назад и новый круг — перезагрузкой страницы с `?t=`.
- Ссылка на момент: `…/zhara-21/?t=45m&speed=5`.
