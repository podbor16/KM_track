# Демо «Повтор гонки» — части 3–4: Триатлет 24 ч и Дуатлон 222 — план

> Выполнение: superpowers:subagent-driven-development. Спека: `docs/superpowers/specs/2026-11-02-race-replay-triatleta-design.md`. Образцы: `tools/demo/siberman/` (песочница, запись, источник), `tools/demo/static/demo-replay.js` (режим poll), `tools/demo/{site,build,checks,races}.py`.

Как и в части 2: план задаёт интерфейсы, тесты и критерии; тела функций исполнитель пишет по прод-коду. Ветка `feature/race-replay-triatleta`, worktree `.worktrees/race-replay-triatleta` (скопировать `.env`, `.env.local`, `static/lib/`). Python `C:/Users/podbo/miniconda3/python.exe` (не conda run). Только локальная БД :3308. Прод-код не менять. ПДн/пароли не выводить. Прогон > 15 мин — стоп.

## Структура

| Файл | Ответственность |
|---|---|
| `tools/demo/sandbox.py` | общий `recreate(src, dst, tables=None)` + `assert_local` (вынести из `siberman/sandbox.py`, Siberman — через него) |
| `tools/demo/replay_poll.py` | общий формат записи для poll-продуктов: `diff`/`apply_change`/`state_at` по набору эндпоинтов (обобщение `siberman/record.py`; Siberman переводится на него, если это не ломает его тесты — иначе оставить как есть) |
| `tools/demo/triatleta/{__init__,anonymize,record,source}.py` | Триатлет |
| `tools/demo/duathlon/{__init__,anonymize,record,source}.py` | Дуатлон |
| `tools/demo/static/demo-replay.js` | poll: одно окно, карта эндпоинтов, адаптер ссылок, refresh-функции |
| `tools/demo/{site,build,checks,races}.py`, `templates/` | страницы, витрина, проверки |

### Task T1: песочницы + обезличивание (оба продукта)
- Общий `tools/demo/sandbox.py` (перенести из siberman, siberman импортирует оттуда; его тесты зелёные).
- `triatleta/anonymize.py::anonymize_sandbox(conn, seed) -> real_pii`; `duathlon/anonymize.py::anonymize_sandbox(conn, seed) -> real_pii` — по спеке п.2 (схему смотреть `SHOW CREATE TABLE` в локальных БД).
- Подмена подключения: контекст-менеджер `use_sandbox(module_service, attr, dbname)` — подменяет `service.get_*_connection` функцией, открывающей только `*_demo` (assert), и восстанавливает.
- Тесты: unit (чистые функции маппинга, команды/mixed), интеграционный (skip без БД): после recreate+anonymize в песочницах нет реальных фамилий (≥4 букв, не из словарей), команд, городов; число участников то же; прод-`get_standings` через `use_sandbox` возвращает обезличенные данные.
- Коммит `feat(demo/triatleta): песочницы и обезличивание Триатлета и Дуатлона`.

### Task T2: проигрывание и запись (оба продукта)
- Прочитать: `src/race_triatleta/service.py` (`get_standings`, `get_all_laps`), роутер (сериализация); `src/duathlon222/service.py` (`get_standings`, `get_participant`, смысл колонок этапов и `checkpoints`), роутер; загрузчики `load_tri_results.py`, `load_duathlon_results.py` (что и когда пишется: `lap_ms`, статусы, транзиты).
- `tools/demo/replay_poll.py`: формат `{meta, initial: {key: ответ}, changes: [{t_s, key: изменение}]}`; изменение ответа-объекта/списка — diff по ключу элемента + порядок; Python `state_at(rec, t) -> {key: ответ}`.
- `triatleta/record.py`, `duathlon/record.py`: `load_final`, `clear_results`, `replay(conn, final, step_s=30) -> rec` по спеке п.3 (статусы: finished с финиша, DNF/DSQ с последней отметки).
- Тесты: unit — diff/state_at на синтетике; интеграционные — `state_at(rec, конец)` == ответы прод-кода по полным данным для ВСЕХ ключей (Дуатлон: 3 standings + участники); числа: шаги, время, размер gzip.
- Коммит `feat(demo/triatleta): проигрывание Триатлета и Дуатлона`.

### Task T3: `demo-replay.js` — обобщение poll
- `data-days` с одним окном; `data-endpoints` (или в meta записи): правило URL → ключ записи (Триатлет: `/api/tri/standings` → `standings`, `/api/tri/laps` → `laps`; Дуатлон: `/api/duathlon222_2026/standings[?gender=M|F]` → `standings`, `standings?gender=M`…, `/api/duathlon222_2026/participant/<n>` → `participant/<n>`); для Siberman — существующее поведение (обратная совместимость: старый формат записи Siberman продолжает работать либо Siberman переводится на новый формат вместе с T2).
- Адаптер ссылок карточки: из data-атрибута шаблон пути (`/participant/<bib>` у Siberman, `/duathlon222_2026/participant/<n>` у Дуатлона).
- Перемотка вперёд: вызвать глобальные функции обновления, перечисленные в data-атрибуте (`refreshData` / `loadStandings,loadLaps` / `load`), иначе перезагрузка.
- Отметки ползунка из `meta.marks` (если есть), иначе дни.
- node-сверки: `state_at` JS ↔ Python на синтетике; Siberman и трекер — регрессия (скрипты в scratchpad).
- Коммит `feat(demo): poll — эндпоинты, одно окно, адаптер ссылок`.

### Task T4: сайт, сборка, проверки
- `races.py`: `triatleta_24h` (slug `triatleta-24h`, title «Триатлет 24 ч 2026», caption «Триатлет 24 ч, 25–26.06.2026 — запись реальной гонки», kind «Live-результаты · 24 ч»), `duathlon222_2026` (slug `duathlon222-2026`, title «Дуатлон 222 · 2026», caption «Дуатлон 222, 05.09.2026 — запись реальной гонки», kind «Live-результаты»); marks/loop_start — по спеке п.4.
- `site.py`: рендер шаблонов (переменные как в прод-роутерах: `event_id`, `year`, `start_number`, `v`), Метрика Дуатлона → пустой шаблон через ChoiceLoader, вставка демо-скрипта и полосы (как `render_siberman` — переиспользовать `inject_demo`), карточки Дуатлона на каждый номер, статика (`static/css/tri_results.css`, иконки, `static/js/duathlon222-chart.js`, chart4; Google Fonts Onest — внешний, ок).
- `build.py`/`checks.py`: новые ключи, `_ALLOWED_API` + `/api/tri/`, `/api/duathlon222_2026/`; ПДн — команды, города.
- Сборка всех пяти гонок «Готово»; smoke 200.
- Коммит `feat(demo): Триатлет и Дуатлон в сборке и витрине`.

### Task T5: браузер, публикация
- Проверка по спеке п.5 (включая паузу и «Финиш» для графиков, фильтр М/Ж, карточку на том же моменте, мобильный, регрессии Жары и Siberman).
- После подтверждения пользователя — публикация, merge в main, ревью в todo.md.
