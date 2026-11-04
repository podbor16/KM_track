# Личный кабинет Б2: представители — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** аккаунт становится представителем карточки (ребёнок/родитель/подопечный) по заявке на своей почте и ДР и видит её историю; владелец видит и убирает представителей.

**Architecture:** таблица `athlete_reps(email, client_id, birthday)`; сервис `athlete_reps.py` по образцу `athlete_claims.py` (общее правило действительности, лимит, журнал, уведомление в фоне); склейка/отмена — вместе с привязками в `client_merge.apply` / `dq_actions._restore_claims`; страница подопечного переиспользует `me-history.html`.

**Tech Stack:** FastAPI, Jinja2, mysql-connector (пул autocommit=True), pytest.

**Спецификация (читать целиком):** `docs/superpowers/specs/2026-11-04-athlete-reps-design.md`; контекст — `docs/superpowers/specs/2026-11-03-athlete-cards-history-design.md`.

**Окружение:**
- Worktree `C:\Users\podbo\Работа\КРАСМАРАФОН\KM_track\.worktrees\slot-transfer`, ветка `feature/athlete-reps` (от main). Локальный сервер :8000 запущен из этого worktree с `--reload`. Кабинет локально включён (`config/athlete_cabinet_enabled.local`).
- Python `C:/Users/podbo/miniconda3/python.exe`. Скрипты — в scratchpad `C:\Users\podbo\AppData\Local\Temp\claude\c--Users-podbo--------------------KM-track\b438ba73-a6e9-4baa-84c7-4f6dd0d0a921\scratchpad\`. Локальная БД MySQL80:3308.
- **Не использовать `git stash`.** Не пушить. Коммит на задачу + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Тесты: только тестовые данные (событие «Тест представители» 2099, фамилии `Тестпред…`, почты `*@reps-test.local`), все UPDATE/DELETE — только по ним, перед новым UPDATE — `SELECT COUNT(*)`. Образец фикстур — `tests/integration/test_athlete_claims.py` (`db`, `cards`, `mail`, `web`, `login`). Не трогать данные почт `podbor250718@yandex.ru`, `ivanpodborskii0801@gmail.com`. Не выводить `.env*`, ПД.
- Прогоны: `tests/unit/ -q -p no:warnings`; `tests/integration/test_athlete_reps.py tests/integration/test_athlete_claims.py tests/integration/test_athlete_claims_dq.py tests/integration/test_athlete_routes.py tests/integration/test_admin_data_quality.py tests/integration/test_data_quality_undo.py -q -p no:warnings`.

---

### Task 1: Миграция и сервис

- [ ] `migrations/athlete_reps.sql` — DDL из спецификации; **в комментариях без «;»** (скрипт применения режет по «;»). Применить к локальной БД (скрипт в scratchpad, `CREATE TABLE` из файла), проверить `SHOW TABLES LIKE 'athlete_reps'`.
- [ ] `src/krasmarafon/services/athlete_reps.py`:
  - `class RepResult(str, Enum)`: `OK, ALREADY, OWN, NO_BIRTHDAY, LIMIT, MISMATCH` (+ `ValueError` → not_yours, как в `athlete_claims.claim`).
  - `become_rep(email, client_id, birthday: date) -> RepResult` — порядок: заявка этого человека на почте (переиспользовать функцию проверки из `athlete_claims`; вынести общую, если она приватная) → `OWN` (аккаунт заявил эту карточку «Это я», действующая привязка) → `ALREADY` → `NO_BIRTHDAY` → `LIMIT` (общая таблица `athlete_claim_attempts`, тот же `CLAIM_ATTEMPTS_PER_DAY`) → сверка ДР (`MISMATCH` + попытка) → INSERT (`ER_DUP_ENTRY` → `ALREADY`) + журнал `athlete_rep`. Транзакция с `SELECT … FOR UPDATE` по карточке, как в `claim`.
  - `rep_cards(email) -> tuple[list[int], list[int]]` — общее правило (карточка есть и `clients.birthday = athlete_reps.birthday`), снятие недействительных с журналом `athlete_unrep` (`card_deleted`/`birthday_changed`, `done_by='system'`).
  - `remove_rep(email, client_id)` (`user`), `reps_of(owner_email) -> list[{"id","client_id","email_masked","created_at"}]` (действующие представители действующих привязок владельца), `remove_rep_by_owner(owner_email, rep_id)` (только своих карточек, `owner_removed`).
  - `notify_rep(client_id, account_email)` — текст из спецификации, адресаты — `athlete_claims.notify_recipients`; ошибки в лог.
  - Без копипаста: общие хелперы (`_conn`, журнал, `same_person`, лимит, `mask_email`) — из существующих модулей.
- [ ] Тесты `tests/integration/test_athlete_reps.py` (сначала красные): все результаты `become_rep`, несколько представителей одной карточки, лимит, общее правило (правка ДР / удаление карточки), `reps_of` + `remove_rep_by_owner` (чужого представителя убрать нельзя), `remove_rep`, уведомление (адресаты без почты аккаунта).
- [ ] Commit `feat(auth): представители — таблица и сервис`.

### Task 2: Склейка и отмена

- [ ] `src/analytics/client_merge.py`: перенос `athlete_reps` удаляемых карточек на итоговую рядом с `move_athlete_claims` (дубль `(email, итоговая)` — снять, журнал `athlete_unrep`/`merged`); в `claims_out` (или отдельный список) — записи для журнала склейки. Таблицы нет (1146) — no-op.
- [ ] `dq_actions._restore_claims` (или рядом): отмена склейки возвращает перенесённые/снятые доступы (как привязки; не возвращать, если уже есть такой же).
- [ ] Тесты в `tests/integration/test_athlete_reps.py`: склейка переносит доступ, дубль снимается, отмена возвращает; существующие тесты склейки зелёные.
- [ ] Commit `feat(auth): склейка и отмена учитывают доступы представителей`.

### Task 3: Интерфейс

- [ ] Роутер `src/krasmarafon/routers/athlete.py` (под тем же переключателем, Origin-проверка на POST как у остальных): `POST /me/rep` (`client_id`, `birthday`; ошибки → `/me?rep={id}&r={код}`; OK → фон `notify_rep`), `POST /me/unrep`, `POST /me/rep/remove` (`rep_id`), `GET /me/athlete/{client_id}` (действующий доступ → история одной карточки через `history_rows`/`build_history` и тот же шаблон; своя заявленная → редирект `/me/history`; иначе 404). `/me`: действующие доступы (`rep_cards`) → плашка «Вы представитель · История →»; снятые → пояснение; тексты ошибок формы представителя. `/me/history`: блок «Доступ к вашей истории» (`reps_of`). Текст `OTHER_PERSON` — из спецификации.
- [ ] Шаблоны: `me.html` — вторая кнопка «Я представитель» (`<details>`, без JS), плашка; `me-history.html` — флаг «история подопечного» (низ: «Сообщить об ошибке» + «Отказаться от доступа» с `confirm()`; без «отвязать»), блок представителей у владельца (почта маской, дата, «Убрать» с `confirm()`). Стили — `static/css/me.css`.
- [ ] Тесты (web, через фикстуры Б1): кнопки на `/me`, стать представителем → плашка, ошибки у формы, `/me/athlete/{id}` (доступ / нет → 404 / своя → редирект / кабинет выключен → 404), отказ, владелец видит и убирает, после правки ДР — пояснение.
- [ ] Скриншоты (agent-browser, 1280 и 390): `/me` с двумя кнопками и плашкой, `/me/athlete/{id}`, блок представителей у владельца — посмотреть самому; тестовые данные удалить; код входа — лог сервера (`tasks\bdwgn8b1z.output` в каталоге задач сессии, строка `MAIL (log) to=` с маской).
- [ ] Commit `feat(auth): «Я представитель», история подопечного, список представителей у владельца`.

### Task 4: Прогон и передача

- [ ] Полный прогон из «Окружения» + `test_relink*.py`, `test_dq_cases_db.py`, `test_lead_pd_refused.py`.
- [ ] Чек-лист пользователю; Obsidian «текущие приоритеты». Выкладка — миграция `athlete_reps.sql` + push, только после «да».
