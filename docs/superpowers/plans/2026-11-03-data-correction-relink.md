# Перепривязка заявки/результата после исправления данных — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** после исправления ФИ/ДР заявки или результата строка оказывается на верной карточке — во всех путях правки (стартовый список, импорт Tilda, загрузчик Copernico), с журналом и отменой.

**Architecture:** одна функция `dq_actions.relink_row()` выбирает действие по правилу (ничего / переезд на существующую / переименование карточки / новая карточка) и выполняет его существующими отменяемыми операциями (`move_row`, `edit_record('clients')`); чистая функция `plan_relink()` (без записи) — для предпросмотра в админке и тестов. Вызывается из `update_lead`, `bulk_import_leads`, `load_race_results._update_existing`. Расхождение заявки с исправленным протоколом — находка «Качества данных» с кнопкой.

**Tech Stack:** FastAPI, mysql-connector (пул autocommit=True), pytest; фронт админки — `templates/krasmarafon/admin.html` + `static/js/*`.

**Спецификация (читать целиком):** `docs/superpowers/specs/2026-11-03-data-correction-relink-design.md`.

**Окружение:**
- Worktree `C:\Users\podbo\Работа\КРАСМАРАФОН\KM_track\.worktrees\slot-transfer`, ветка `feature/slot-transfer`. `.env.local` — скопировать из основного репозитория, если нет (не коммитить, не выводить). Локальная БД — MySQL80:3308.
- Python: `C:/Users/podbo/miniconda3/python.exe` (`conda run` может зависать). Скрипты — файлами в scratchpad `C:\Users\podbo\AppData\Local\Temp\claude\c--Users-podbo--------------------KM-track\b438ba73-a6e9-4baa-84c7-4f6dd0d0a921\scratchpad\`.
- **Тесты на общей локальной БД:** любые UPDATE/DELETE — только по тестовым данным (своё тестовое событие `event_name = 'Тест перепривязка'` 2099, почты `*@relink-test.local`, id созданных строк). Перед первым прогоном нового UPDATE — `SELECT COUNT(*)` с тем же WHERE. Фикстура чистит до и после (порядок: results → leads → events → clients; `dq_actions` по `done_by`). Образец — `tests/integration/test_athlete_claims.py` (фикстуры `db`, `add_lead`; триггеры `leads` сами создают карточку/событие).
- Не трогать данные почты `podbor250718@yandex.ru`. Не выводить `.env*` и ПД. Не пушить. Коммит на задачу + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Существующие тесты «Качества данных» и кабинета — зелёные: `tests/integration/test_admin_data_quality.py test_dq_cases_db.py test_data_quality_undo.py test_athlete_claims.py test_athlete_claims_dq.py test_admin_leads_import.py`, `tests/unit/`.

---

## Файлы

| Файл | Что |
|------|-----|
| `src/analytics/dq_actions.py` | `plan_relink`, `relink_row`; действие «Исправить заявку по протоколу» |
| `src/analytics/dq_checks.py` (+ `dq_cases.py` при необходимости) | находка «заявка и результат №N расходятся» |
| `src/analytics/db_results.py` | `update_lead`: `event_id` при смене дистанции + `relink_row`; `bulk_import_leads`: `relink_row` + отчёт + журнал удалений |
| `src/krasmarafon/routers/admin.py` | предпросмотр перепривязки для «Изменить» |
| `templates/krasmarafon/admin.html` / `static/js/…start-list…` | предупреждение перед сохранением |
| `load_race_results.py` | `_update_existing`: `relink_row` для результата |
| `src/krasmarafon/routers/data_quality.py` + UI «Качества данных» | кнопка «Исправить заявку по протоколу» |
| `tests/unit/test_relink_plan.py`, `tests/integration/test_relink.py` | тесты |

---

### Task 1: `plan_relink` и `relink_row`

Прочитать: `dq_actions.move_row` (сигнатура `move_row(conn, table, row_id, user, key="", to_client_id=None, new_card=None, align=False)`, `MOVABLE`, удаление опустевшей карточки, журнал `move_result`), `edit_record(conn, table, row_id, fields, user, key="")` для `clients` (проверка «такие ФИ+ДР уже у другой карточки»), `normalize_person_name`, триггер `trg_leads_before_insert` (`SHOW CREATE TRIGGER`) — как он сравнивает ФИ+ДР (нормализация, ё→е).

```python
NO_BD = (None, "1900-01-01")

def plan_relink(conn, table, row_id) -> dict:
    """Что сделает relink_row, без записи. -> {"action": "none"|"move"|"rename"|"new_card"|"skip",
    "from_card": id, "to_card": id|None, "card": {"id","surname","name","birthday","leads","results"}|None,
    "new": {"surname","name","birthday"}, "reason": str}
    skip — ДР строки заглушка/пусто. Сравнение ФИ+ДР — как uk_client (нормализованные, ё→е)."""

def relink_row(conn, table, row_id, user, source) -> dict:
    """Выполняет план: move → move_row(to_client_id=…); rename → edit_record('clients', from_card,
    {surname,name,birthday}); new_card → move_row(new_card=…). source ∈ {'admin','import','loader','dq'} —
    в key журнала (например f"relink:{source}"). -> план с action_id."""
```

Правило — таблица из спецификации. «Других строк нет» = у карточки нет других заявок и результатов (`COUNT` по `leads`/`results` без этой строки).

- [ ] Unit-тесты выбора действия — вынести решение в чистую функцию `_decide(row, card, other_rows, match)` и покрыть 4 случая + заглушку (`tests/unit/test_relink_plan.py`).
- [ ] Интеграционные (`tests/integration/test_relink.py`): для заявки и для результата — каждый из 4 случаев (создать данные: две карточки, заявка на «маминой» карточке с её ФИ+ДР → исправить ФИ+ДР на «дочь» (нет карточки) → `new_card`; исправить на существующую → `move`; фантомная карточка с единственной заявкой → `rename`; совпадает → `none`); отмена каждого через `undo_action` возвращает как было; привязка кабинета (`athlete_claims`) — общее правило не нарушено (смоук).
- [ ] Commit `feat(dq): перепривязка строки к верной карточке после исправления ФИ/ДР`.

### Task 2: «Изменить» в стартовом списке

- `db_results.update_lead` (стр. ~1900): при смене дистанции — `event_id` и дубли как в `dq_actions.edit_record` (переиспользовать `_lead_event_id` и `recompute_duplicates`, без копипаста); после сохранения, если менялись ФИ или ДР, — `relink_row(conn, 'leads', id, user, 'admin')` (нужен `user` — посмотреть, как `patch_lead` в `admin.py:455` получает пользователя, и пробросить).
- Новый эндпоинт предпросмотра `POST /api/admin/leads/{lead_id}/relink-preview` (тело — те же поля `LeadPatch`; `api_require_auth`) → `plan_relink` по **будущим** значениям без записи (сделать `plan_relink` способным принять «будущие» ФИ/ДР: параметр `new=None`).
- Фронт «Изменить»: перед сохранением, если меняются ФИ/ДР, — запрос предпросмотра; при `move`/`rename`/`new_card` — `confirm()` с текстом из спецификации («Заявка переедет на карточку №1234 — Иванов Иван, 12.03.1990, 5 заявок, 3 результата. Сохранить?» / «Будет создана новая карточка …» / «Карточка №… будет переименована …»); отмена — не сохранять. Найти код формы: `templates/krasmarafon/admin.html` (~1230-1268) и связанный JS.
- [ ] Тесты: предпросмотр не меняет БД; PATCH с исправлением ДР → заявка на верной карточке; смена дистанции → новый `event_id`; без входа — 401.
- [ ] Скриншот confirm-сценария не обязателен; проверить в браузере (agent-browser) на тестовых данных, что диалог появляется (вход в админку — cookie `km_session` через `src.core.auth.create_session_cookie` в браузере агента; учётные данные не выводить).
- [ ] Commit `feat(admin): «Изменить» заявку перепривязывает карточку с предупреждением`.

### Task 3: Импорт Excel Tilda

- `bulk_import_leads` (стр. ~2247): после обновления совпавшей по `order_id` строки, если изменились ФИ/ДР, — `relink_row(..., 'import')`; в результат импорта — счётчик `relinked` и список `order_id`; показать в отчёте импорта в админке («перенесено на другую карточку: N»). Найти, где отчёт рендерится.
- Удаления «файл — источник истины» (~2425-2432): писать каждую удалённую строку в журнал `dq_actions` так же, как `delete_lead()` (снимок строки).
- [ ] Тесты (`tests/integration/test_admin_leads_import.py` — посмотреть, как там строят файл): исправленная ДР по тому же `order_id` → переезд + `relinked`; удаление → запись в журнале.
- [ ] Commit `feat(import): импорт Tilda перепривязывает исправленные заявки, удаления — в журнал`.

### Task 4: Загрузчик результатов

- `load_race_results.py::_update_existing` (стр. ~955, UPDATE ~1161-1172): если по номеру пришли другие ФИ или ДР — после UPDATE `relink_row(conn, 'results', id, 'loader', 'loader')`; в лог загрузчика — строка о переезде. Посмотреть, как загрузчик получает соединение (не пул?), транзакции и commit — вызов `relink_row` не должен ломать его пакетную логику; при исключении в перепривязке — лог и продолжение загрузки (не ронять загрузку протокола).
- [ ] Тест: вызвать `_update_existing` на тестовом событии (посмотреть, как его можно вызвать изолированно — есть ли тесты загрузчика в `tests/`) с новыми ФИ для номера → результат на верной карточке.
- [ ] Commit `feat(loader): исправленные в протоколе ФИ/ДР перепривязывают результат`.

### Task 5: Находка «заявка и результат расходятся» + кнопка

- Изучить `dq_checks.check_lead_on_other_card` и прочие проверки, где результат и заявка одного номера на разных карточках (`R-LEAD`, `R-CARD`): какие находки и какие действия они предлагают. Цель: при «результат исправлен и переехал, заявка того же события и номера — со старыми ФИ/ДР на другой карточке» — находка «Заявка и результат №N расходятся» с действием **«Исправить заявку по протоколу»** (а не склейка). Если подходящая проверка есть — дать ей это действие; если нет — добавить, не дублируя.
- Действие: ФИ+ДР заявки := из результата (`edit_record('leads', …)`), затем `relink_row(..., 'dq')`. Эндпоинт в `routers/data_quality.py` рядом с `move`/`edit`; кнопка в UI «Качества данных» (найти, где рисуются действия находок — `static/js/admin-dq-cases.js`).
- [x] Тесты: находка появляется; действие переносит заявку за результатом; отмена.
- [x] Commit `feat(dq): «Исправить заявку по протоколу» для расходящихся заявки и результата`.

### Task 6: Полный прогон и передача пользователю

- [ ] `tests/unit/` и интеграционные из «Окружения» + новые — зелёные.
- [ ] Чек-лист для пользователя (локальный сервер — запустить из этого worktree `dev.ps1`, если :8000 занят другим worktree — согласовать с координатором): правка ДР заявки в стартовом списке → предупреждение → заявка на верной карточке; отмена в журнале «Качества данных».
- [ ] Obsidian «текущие приоритеты» — статус. Выкладка — после «да».
