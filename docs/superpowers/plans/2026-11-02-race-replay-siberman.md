# Демо «Повтор гонки» — часть 2: Siberman 2026 — план

> Выполнение: superpowers:subagent-driven-development, по задаче на субагента. Спека: `docs/superpowers/specs/2026-11-02-race-replay-siberman-design.md`. Часть 1 (образец): `tools/demo/` + `tools/demo/README.md`.

**Отличие от плана части 1:** прод-код Siberman не меняется, а точная форма его данных выясняется по ходу, поэтому план задаёт интерфейсы, тесты и критерии приёмки; тела функций исполнитель пишет, читая указанный прод-код. Код части 1 — образец стиля.

**Окружение:** ветка `feature/race-replay-siberman`, worktree `.worktrees/race-replay-siberman` (скопировать `.env`, `.env.local`, `static/lib/`). Python: `C:/Users/podbo/miniconda3/python.exe` (не `conda run`). Unit: `… -m pytest tests/unit/ -q -p no:cacheprovider`. Только локальная БД :3308. ФИО/пароли не выводить.

## Структура

| Файл | Ответственность |
|---|---|
| `tools/demo/siberman/__init__.py` | пакет |
| `tools/demo/siberman/sandbox.py` | пересоздание `siberman_demo` из `siberman` (только таблицы результатов) |
| `tools/demo/siberman/anonymize.py` | обезличивание песочницы (все годы, согласованно с рекордами/persons) |
| `tools/demo/siberman/timeline.py` | абсолютные моменты отметок, окна дней, «время без ночей» ↔ абсолютное |
| `tools/demo/siberman/record.py` | проигрывание в песочнице через прод-функции → запись; `state_at` |
| `tools/demo/siberman/source.py` | `build_siberman(key) -> (rec, real_pii)` — оркестрация + meta |
| `tools/demo/static/demo-replay.js` | обобщение: режимы `tracker`/`poll`, дни, перехват ссылок участника |
| `tools/demo/site.py`, `build.py`, `checks.py`, `races.py` | страницы Siberman, карточка в витрине, проверки |
| `tests/unit/test_demo_siberman_*.py`, `tests/integration/test_demo_siberman.py` | тесты |

---

### Task S1: песочница + обезличивание

**Прочитать:** `src/siberman/db.py` (подключение: `SIBERMAN_DB_NAME`), миграции `src/siberman/migrations/001,004,006,008,014*.sql` (поля таблиц), `tools/demo/anonymize.py` (словари имён — переиспользовать).

**Интерфейсы:**
- `sandbox.recreate(src='siberman', dst='siberman_demo') -> None` — DROP/CREATE dst, `CREATE TABLE dst.t LIKE src.t` + `INSERT … SELECT` для: participants, checkpoints, checkpoint_times, transitions, stage_totals, overall_results, race_config, siberman_records, siberman_persons, siberman_person_links. Защита: только 127.0.0.1/localhost:3308.
- `anonymize.anonymize_sandbox(conn, seed:int, race_year:int) -> dict` — по месту в `siberman_demo`:
  - ключ человека: `person_id` из `siberman_person_links`, если есть, иначе нормализованные (strip, upper, ё→е) фамилия+имя; ключ → фейковые (фамилия, имя) с учётом пола (фамилии/имена — из `tools/demo/anonymize.py`, женская форма фамилии +«а»; если пар не хватает — добавить словарь, не ронять);
  - participants (все годы): surname/name → фейк; city, country → NULL; relay_team_name → «Команда N» (N — порядковый в пределах года);
  - siberman_records: holder_name → фейк по тому же ключу (holder_name сопоставлять с «Фамилия Имя» участников; не найден — сгенерировать новый фейк и запомнить); holder_team → по сопоставлению команд года, иначе NULL;
  - siberman_persons: ФИО → фейк того же человека; остальные персональные колонки (прочитать миграцию 014: ДР, телефоны, email, город…) → NULL;
  - номера `race_year`: перестановка значений bib (детерминированно от seed); участники с одинаковым bib (эстафета) получают одинаковый новый bib.
  - возвращает `{'real_surnames': set, 'real_names_full': set, 'real_teams': set, 'real_cities': set}` — для проверки ПДн (в файл не пишется).

**Тесты** (`tests/unit/test_demo_siberman_anonymize.py`) — функции, не требующие БД, вынести в чистые: `build_person_map(rows, seed)`, `remap_bibs(rows, seed)`; проверить: один человек в разных годах → одно фейковое имя; пол сохранён; фейк не совпадает с реальными фамилиями; эстафета — общий новый bib; перестановка без повторов; детерминизм.
**Интеграционный** (`tests/integration/test_demo_siberman.py::test_sandbox_anonymized`, skip без локальной БД): после recreate+anonymize в `siberman_demo` нет ни одной реальной фамилии (≥4 букв, не из словарей генератора), города, названия команды; записей участников столько же, сколько в `siberman`.
**Коммит:** `feat(demo/siberman): песочница и обезличивание`.

### Task S2: время гонки

**Прочитать:** `service.py:133-206` (`convert_bike_times_to_elapsed`, гандикап дня 2), `copernico_run.py:118-134`, `static/js/siberman-common.js:988-994` (`bike2StartEpoch`), `db.get_race_start/get_stage_starts`.

**Интерфейсы (чистые, `timeline.py`):**
- `abs_ms(stage, cumulative_s, *, race_start, bike2_day_midnight, handicap_s, run_start) -> int` (unix ms; datetime — naive Красноярск → явный `+07:00`);
- `day_windows(marks_by_day, starts) -> list[{label, start_ms, end_ms}]` — окна [старт − 5 мин; последняя отметка + 5 мин];
- `compact_to_abs(t_s, windows) -> int` и `abs_to_compact(ms, windows) -> float` — «время без ночей» (секунды от начала окна дня 1, окна склеены) ↔ абсолютное.
**Тесты:** моменты для каждого этапа (вкл. гандикап), склейка окон, взаимная обратимость, граница окна.
**Коммит:** `feat(demo/siberman): время гонки, окна дней`.

### Task S3: проигрывание и запись

**Прочитать:** `service.recompute_totals_ranks_records` (398-509: что нужно в `participants`/`pid_cp_times`), `_recompute_records`, `db.upsert_checkpoint_time`, `db.update_participant_status`, `db.get_results_for_year`, `db.get_all_records`, `router.api_results` (сериализация ответа), `copernico_run.py` (как live-путь пишет отметки — повторить его последовательность).

**Интерфейсы (`record.py`):**
- `replay(conn, race_year, final, windows, step_s=20) -> rec` — `final`: итоговые участники и `pid_cp_times` (прочитаны ДО очистки); очищает результаты года в песочнице; по шагам compact-времени: upsert наступивших отметок → `recompute_totals_ranks_records` → `get_results_for_year`+`get_all_records` → `serialize()` (как `router.api_results`, даты с `+07:00`); гандикап виден после окна дня 1, финальные статусы — после окна дня 3. `persons_service.sync_safe` → no-op на время replay.
- `diff(prev, cur) -> dict|None` и `state_at(rec, t)` — запись `{meta, initial, changes:[{t_s, individual:[…], relay:[…], top:{…}}], days}` (элементы по `bib`, `top` — изменившиеся общие поля целиком).
**Тесты (unit):** `diff`/`state_at` обратимы на синтетических ответах (добавление/изменение/удаление поля, records). **Интеграционный:** полный replay 2026 в песочнице: число шагов, время; финальное состояние == ответ прод-кода по итоговым данным (сравнить `get_results_for_year` после полной загрузки финала в песочницу с `state_at(rec, конец)`) — по всем полям; размер записи gzip (ориентир ≤ 2 МБ).
**Коммит:** `feat(demo/siberman): проигрывание через прод-путь и запись`.

### Task S4: `demo-replay.js` — режим poll и дни

**Прочитать:** `templates/siberman/results.html` (fetch 3187-3233, `_lastDataJson`, `syncUrlFromState` 3127-3141, ссылки `/participant/` 688-690 и др.), `templates/siberman/participant.html` (какие запросы), текущий `tools/demo/static/demo-replay.js`.
**Сделать:**
- режим из `data-mode` (`tracker` по умолчанию): общие части (часы с первой строки, панель, перемотка назад перезагрузкой, сворачивание, ошибки) — без изменений; `tracker`-специфика (SSE, дистанция, preselect, current-event) — только в своём режиме;
- `poll`: `fetch('/api/siberman/results…')` → `state_at(t)` (JS-эквивалент Python `state_at`); часы — «время без ночей»: `Date.now()` = `compact_to_abs(t)`; на переходе окна часы прыгают ВПЕРЁД; ползунок/кнопки — по `days` + «Финиш»;
- перехват кликов/`window.open` по `/participant/<bib>` → `${BASE}${slug}/participant/<bib>/?t=…&speed=…`;
- `?t=` переживает `history.replaceState` страницы (часы держатся в памяти; при перезагрузке t берём из своего параметра — если страница его затирает, хранить в `sessionStorage` на время перезагрузки).
**Проверка:** node-сверка `state_at` JS ↔ Python на синтетике (как в части 1); `node --check`.
**Коммит:** `feat(demo): режим poll и дни для Siberman`.

### Task S5: сайт, витрина, сборка, проверки

- `races.py`: `siberman_2026` (`kind: 'poll'`, slug `siberman-2026`, title «Siberman 2026», caption «Siberman, 06–08.08.2026 — запись реальной гонки», `loop_start` — середина дня 1).
- `site.py`: рендер `siberman/results.html` и `siberman/participant.html` (на каждый bib) с `v='demo'`; вставка `<script demo-replay data-mode="poll" …>` в `<head>` до скриптов страницы и полосы «← Все демо · caption» в начало `<body>` (шаблоны не менять — вставка в отрендеренный HTML); `og:url/og:image` → демо; статика Siberman (`static/lib/chart4`, `static/js/siberman-common.js`, `static/fonts/siberman/`, логотипы/favicon/`star.png` — список по `check_links`).
- `build.py`: ключ `siberman_2026` → `tools.demo.siberman.source.build_siberman`; в процессе — `SIBERMAN_DB_NAME=siberman_demo`.
- `checks.py`: `_ALLOWED_API` + `/api/siberman/results`; ПДн — плюс реальные города, команды, «Фамилия Имя» участников и рекордсменов (из `real_pii`).
- витрина: третья карточка.
**Проверка:** сборка трёх гонок «Готово»; smoke 200 по страницам.
**Коммит:** `feat(demo): Siberman в сборке и витрине`.

### Task S6: браузер, публикация

- Браузер (agent-browser, чистый профиль): витрина — 3 карточки; Siberman — данные меняются со временем, таймеры этапов идут, кнопки дней перескакивают ночь вперёд, «Финиш» = протокол, перемотка назад — перезагрузка с правильным t, карточка участника открывается на том же моменте, мобильный 390×844, нет ошибок консоли и `/api/`; Жара 21,1/5 — без регрессий (маркеры, хвосты, перемотка).
- После подтверждения пользователя — `publish.py`, проверка живого сайта.
- README: раздел «Siberman».
- todo.md: ревью.
