# Личный кабинет Б1: «Это я» и история спортсмена — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** аккаунт заявляет свою карточку (`clients.id`) подтверждением ДР и видит объединённую историю на `/me/history`.

**Architecture:** привязки — таблица `athlete_claims` (+ попытки — `athlete_claim_attempts`); правило действительности (карточка существует и ДР = подтверждённой) проверяется лениво в `claimed_cards()`; единственный хук в «Качество данных» — перенос привязки при склейке. Итоги истории — чистые функции над строками (`athlete_history.py`). Страницы — серверный рендер Jinja + Chart.js для динамики.

**Tech Stack:** FastAPI, Jinja2, mysql-connector (пул `src/analytics/db_pool.get_pooled_connection`, **autocommit=True**), pytest, Chart.js (`/static/lib/chart4/chart.umd.min.js`).

**Спецификация (читать целиком):** `docs/superpowers/specs/2026-11-03-athlete-cards-history-design.md`. Этап А (контекст, стиль кода): `docs/superpowers/specs/2026-11-03-athlete-login-design.md`, код — `src/krasmarafon/services/athlete_auth.py`, `athlete_cabinet.py`, `src/krasmarafon/routers/athlete.py`, `templates/krasmarafon/me.html`, `me-login.html`, `static/css/me.css`, тесты `tests/integration/test_athlete_*.py`.

**Окружение:**
- Worktree `C:\Users\podbo\Работа\КРАСМАРАФОН\KM_track\.worktrees\pd-consent`, ветка `feature/athlete-cards`.
- Тесты: `conda run -n base python -m pytest <путь> -q -p no:warnings`; результат — по итоговой строке/коду возврата.
- Локальная БД — MySQL80:3308 (`.env.local`, уже есть в worktree). Свои скрипты: `load_dotenv(".env.local", override=True)` до импорта `src.*`; держать ссылку на соединение в переменной. Многострочный `conda run python -c` зависает — скрипты файлами в scratchpad `C:\Users\podbo\AppData\Local\Temp\claude\c--Users-podbo--------------------KM-track\b438ba73-a6e9-4baa-84c7-4f6dd0d0a921\scratchpad\`.
- Не выводить содержимое `.env*`, пароли, персональные данные из БД (в отчётах — только числа).
- **Не пушить, не трогать прод.** Коммит на задачу, в конце сообщения `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Пул — autocommit: транзакция для нескольких запросов — `conn.start_transaction()` … `commit()`/`rollback()`.
- Тестовые данные интеграционных тестов — почты `*@athlete-test.local`, события `event_name = 'Тест кабинет Б1'` 2099 года, карточки, созданные тестом; фикстура чистит до и после (образец — `tests/integration/test_lead_pd_refused.py`: порядок удаления results → leads → events → clients, и `dq_actions` по `finding_key`). Включение кабинета в тестах — фикстура `cabinet_enabled` из `tests/integration/test_athlete_routes.py` (подмена `_ATHLETE_CABINET_FILE`).

---

## Файлы

| Файл | Что |
|------|-----|
| `migrations/athlete_claims.sql` (новый) | `athlete_claims`, `athlete_claim_attempts` |
| `src/krasmarafon/services/athlete_history.py` (новый) | чистые функции: строки результатов/заявок → итоги и лента |
| `src/krasmarafon/services/athlete_claims.py` (новый) | привязки: проверка, заявление, отвязка, лимит, уведомление, выборка строк истории, дубли для админки |
| `src/analytics/dq_actions.py` | `merge_cards`: перенос привязок |
| `src/krasmarafon/services/athlete_cabinet.py` | группа-человек получает `client_id` (для кнопки «Это я») |
| `src/krasmarafon/routers/athlete.py` | `POST /me/claim`, `POST /me/unclaim`, `GET /me/history`; `/me` — статусы привязки |
| `src/krasmarafon/routers/admin.py`, `templates/krasmarafon/admin.html` | блок «Кабинет: возможные дубли» |
| `templates/krasmarafon/me.html`, `me-history.html` (новый), `static/css/me.css` | интерфейс |
| `tests/unit/test_athlete_history.py`, `tests/integration/test_athlete_claims.py` | тесты |

---

### Task 1: Миграция

- [ ] Создать `migrations/athlete_claims.sql`:

```sql
-- Личный кабинет Б1 (2026-11-03): привязка карточки спортсмена к аккаунту-почте («Это я»).
-- birthday — ДР, подтверждённая человеком; привязка действует, пока clients.birthday совпадает.
-- Идемпотентно.

CREATE TABLE IF NOT EXISTS athlete_claims (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  client_id INT NOT NULL,
  birthday DATE NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ac_client (client_id),
  KEY idx_ac_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS athlete_claim_attempts (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  client_id INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_aca (email, client_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] Применить к локальной БД скриптом в scratchpad (выполнить каждый `CREATE TABLE`), вывести `SHOW TABLES LIKE 'athlete_claim%'` → 2 таблицы; повторный запуск без ошибок.
- [ ] Commit `feat(auth): таблицы привязки карточек к кабинету`.

---

### Task 2: Итоги и лента истории (чистые функции, TDD)

`src/krasmarafon/services/athlete_history.py`. Вход — списки dict-строк (как вернёт SQL из Task 3), выход — dict для шаблона. Никакой БД.

Строка результата (`results` + `events`): `id, client_id, event_id, start_number, event_name, event_year, event_date, event_distance (Decimal км), race_status, time_clear_finish, time_gun_finish (timedelta|None), rank_category, rank_category_clean`.
Строка заявки (`leads` + `events`): `id, client_id, event_id, start_number, event_name, event_year, event_date, event_distance (Decimal|None, из events), refund`.

```python
def build_history(results: list[dict], leads: list[dict], today: date, codes: dict, diploma_ids: set) -> dict:
    """-> {"since": год первого старта | None,
           "tiles": {"starts", "finishes", "km", "pace"},          # pace — "м:сс" | None
           "records": [{"distance", "time", "pace", "event_name", "year"}],   # по убыванию дистанции
           "dynamics": {"default": "21.1", "series": {"21.1": [[год, секунды], ...]}},  # пусто — {}
           "years": [{"year", "items": [entry, ...]}]}             # новые сверху"""
```

Правила (спецификация, «Страница истории»):
- время результата — `time_clear_finish`, иначе `time_gun_finish`; место — `rank_category_clean` при чистом времени, иначе `rank_category`;
- **финиш** = `race_status == 'Finished'` и есть время; **старт** = результат со статусом ≠ `'Not started'`;
- км = сумма `event_distance` финишей, `round()` до целого; темп = Σвремя / Σкм только по дистанциям ≥ 1 км, формат `м:сс`; темп строки = время / дистанция;
- рекорды: по каждой дистанции с финишем — минимальное время (с темпом, событием, годом); сортировка по убыванию дистанции;
- динамика: дистанции с финишами в ≥ 2 разных `event_year`; ряд — лучшее время за год, по возрастанию года; `default` — дистанция с наибольшим числом финишей (при равенстве — бо́льшая); нет таких дистанций → `{}`;
- лента: заявка, у которой есть результат с тем же `event_id + start_number`, не выводится отдельно (её показывает результат). Остальные заявки: предстоящая (дата ≥ сегодня, либо даты нет и год ≥ текущего) → `kind="ticket"`; прошедшая → `kind="result"` со статусом «не стартовал» (или «возврат», если `refund`). Результаты → `kind="result"`, статус: `Finished`+время → время/место/темп; `Not started` → «не стартовал»; `DNF`/`Withdrawn` → «сошёл»; `DSQ` → «дисквалифицирован»; прочее без времени → «нет результата»;
- entry: `kind, date, year, event_name, distance (строка «21,1 км» — запятая), start_number, time, place, pace, status, refund, protocol_url (athlete_cabinet.protocol_url при финише), diploma_url ("/diploma/{event_id}/{start_number}" при финише и event_id ∈ diploma_ids)`;
- годы — по `event_year` (иначе год даты), новые сверху; внутри года — по дате, новые сверху (предстоящие — ближайшие сверху, над прошедшими);
- `since` — минимальный `event_year` среди стартов (иначе среди заявок).

Переиспользовать из `athlete_cabinet.py`: `_fmt` (время), `protocol_url`. Если нужно — вынести общий хелпер, не дублировать.

- [ ] Тесты `tests/unit/test_athlete_history.py` (сначала красные), минимум: плитки (старты без Not started, финиши, км, темп без дистанций < 1 км); рекорд — лучшее из двух; динамика: дистанция в одном году не попадает, в двух — попадает, default; заявка с результатом — одна строка; предстоящая заявка → ticket; статусы DNF/Withdrawn/DSQ/Not started/прошедшая заявка/возврат; сортировка лет и внутри года; пустые входы → нули/None/пустые списки без исключений.
- [ ] Реализация → зелёные. Commit `feat(auth): расчёт итогов и ленты истории спортсмена`.

---

### Task 3: Сервис привязок

`src/krasmarafon/services/athlete_claims.py`. Стиль — как `athlete_auth.py` (`_conn()` с `RuntimeError("БД недоступна")` если пул вернул None — переиспользовать из `athlete_auth`, `finally: conn.close()`).

```python
CLAIM_ATTEMPTS_PER_DAY = 5
NOTIFY_MAX = 10
NO_BIRTHDAY = (None, date(1900, 1, 1))

class ClaimResult(str, Enum):
    OK = "ok"; ALREADY_MINE = "already_mine"; TAKEN = "taken"; NO_BIRTHDAY = "no_birthday"
    LIMIT = "limit"; MISMATCH = "mismatch"

def claimed_cards(email) -> tuple[list[int], list[int]]:
    """(действующие client_id аккаунта, client_id снятых сейчас привязок). Снимает недействительные:
    карточки нет (card_deleted) или clients.birthday <> athlete_claims.birthday (birthday_changed) —
    DELETE + журнал dq_actions (action='athlete_unclaim', finding_key='client:{id}',
    details={"email", "reason"}, done_by='system')."""

def claim(email, client_id, birthday: date) -> ClaimResult:
    """Порядок проверок — спецификация «Заявление карточки», п. 1–6. п.1 (карточки нет в заявках почты)
    — ValueError (роутер → 404). Попытка — INSERT в athlete_claim_attempts только при MISMATCH.
    OK: INSERT athlete_claims (IntegrityError по uq_ac_client → TAKEN), журнал action='athlete_claim'
    (done_by=email), затем уведомление (ошибки отправки — logger.exception, результат всё равно OK)."""

def unclaim(email, client_id) -> None:
    """DELETE привязки этого аккаунта (чужую не трогает), журнал action='athlete_unclaim', reason='user'."""

def notify_recipients(client_id, account_email) -> list[str]:
    """Различные непустые leads.email/ma_email карточки (lower, strip), без account_email, не больше NOTIFY_MAX."""

def mask_email(email) -> str:   # "petr@mail.ru" -> "p***@mail.ru"

def history_rows(client_ids) -> tuple[list[dict], list[dict]]:
    """(результаты, заявки) карточек для build_history — поля из Task 2; заявки is_duplicate = 0;
    события — LEFT JOIN events; без фильтра «Без ПД»."""

def history_title(client_ids) -> str:   # ФИ самой новой (max created_at привязки) заявленной карточки из clients

def duplicate_accounts() -> list[dict]:
    """Для админки: аккаунты с ≥ 2 действующими привязками: [{"email", "cards": [{"id","surname","name","birthday"}]}]."""
```

Проверка «карточка в заявках почты» (п.1): `SELECT 1 FROM leads WHERE client_id = %s AND (LOWER(email) = %s OR LOWER(ma_email) = %s) LIMIT 1`.
Сравнение ДР: `clients.birthday` (date) с введённой (date).
Уведомление — `send_mail` из `src.core.mailer` (как в `athlete_auth`), тема и текст — дословно из спецификации, `{ФИ карточки}` — `clients.surname name`, маска — `mask_email(account_email)`. HTML-версия — простой абзац (экранировать ФИ через `html.escape`).

- [ ] Интеграционные тесты `tests/integration/test_athlete_claims.py` (сначала красные). Фикстура создаёт событие «Тест кабинет Б1» 2099, 2 карточки `clients` (ДР 1986-05-01 и 2018-03-02) и заявки на почту `me@athlete-test.local` (+ одна заявка карточки 1 с почты `other@athlete-test.local` и `ma_email` `kab@athlete-test.local` — для адресатов уведомления); результат на карточку 1. Тесты: верная ДР → OK + привязка + журнал + уведомление адресатам `other@…`, `kab@…` (не `me@…`); неверная → MISMATCH и попытка; 5 неверных → LIMIT (и верная тоже LIMIT в тот же день); повтор → ALREADY_MINE; другой аккаунт → TAKEN; карточка без ДР (1900-01-01) → NO_BIRTHDAY; карточка не из заявок почты → ValueError; две карточки одним аккаунтом → обе в `claimed_cards`; `unclaim`; правка `clients.birthday` → `claimed_cards` снимает (reason birthday_changed, журнал); удаление карточки → снимает (card_deleted); `history_rows` возвращает строки обеих карточек; `duplicate_accounts`. Как создавать карточки — посмотреть, что требует таблица `clients` и триггеры `leads` (`SHOW CREATE TABLE`, `SHOW TRIGGERS`); при вставке заявки триггер может сам выставить `client_id` — после вставки явно `UPDATE leads SET client_id = …`.
- [ ] Реализация → зелёные. Commit `feat(auth): привязка карточки к кабинету по ДР`.

---

### Task 4: Перенос привязки при склейке

`src/analytics/dq_actions.py::merge_cards` — перед `_log_action(cur, "merge", …)` (та же транзакция, курсор `cur = conn.cursor()`), для удаляемых карточек `merged_into` (`{удаляемая: итоговая}`):

```python
    # Привязки к личному кабинету (athlete_claims) — на итоговую карточку, если её никто не заявил;
    # иначе привязка удаляемой снимается. Совпадение ДР проверит claimed_cards() при открытии кабинета.
    moved_claims = _move_athlete_claims(cur, merged_into)
```

`_move_athlete_claims(cur, merged_into) -> list[dict]` — для каждой удаляемой с привязкой: если у итоговой привязки нет — `UPDATE athlete_claims SET client_id = итоговая WHERE client_id = удаляемая` (только для первой такой; остальные удаляемые с привязками — снимаются); иначе `DELETE` + запись `{"client_id", "email", "moved_to" | "dropped"}`. Список — в `details` журнала склейки (ключ `"athlete_claims"`). Если таблицы `athlete_claims` нет (`SHOW TABLES LIKE` при первом вызове или перехват ошибки 1146) — ничего не делать (склейка не должна ломаться до миграции).

Проверить, как `apply_merge` (`src/analytics/client_merge.py`) работает с транзакцией/commit — хук должен выполниться до `conn.commit()` в `merge_cards`. Отмену склейки (`undo_action`) не трогать.

- [ ] Тест в `tests/integration/test_athlete_claims.py`: две карточки одного человека (одинаковые ФИ/ДР не допускаются `merge_cards` — дать разные ФИ, ДР одинаковую), привязка на «удаляемой», `merge_cards(conn, [a, b], ФИ, ту же ДР, "tester")` → привязка на итоговой, `claimed_cards` её возвращает; вариант с другой итоговой ДР → `claimed_cards` снимает; итоговая уже заявлена другим аккаунтом → привязка удаляемой снята. Существующие тесты «Качества данных» (`tests/integration/test_admin_data_quality.py`, `test_dq_cases_db.py`, `test_data_quality_undo.py`, unit `tests/unit/*dq*`) — зелёные.
- [ ] Commit `feat(auth): склейка карточек переносит привязку к кабинету`.

---

### Task 5: Интерфейс — `/me`, заявление, история

**`athlete_cabinet.py`:** у группы-человека — `client_id` (ключ `("c", id)` → id, иначе None).

**Роутер `athlete.py`** (тот же `router` с зависимостью переключателя):
- `GET /me`: `claimed, dropped = claimed_cards(email)` → в шаблон: множество заявленных, флаг «данные изменились» для `dropped`, `has_history = bool(claimed)`.
- `POST /me/claim` (`client_id: int`, `birthday: str` `ГГГГ-ММ-ДД`): проверка Origin как у остальных POST; неверный формат → `/me` с ошибкой «Проверьте дату»; `ValueError` → 404; результат → редирект 303 на `/me?claim={client_id}&r={код}` (ошибки показываются у формы этой карточки); `OK`/`ALREADY_MINE` → 303 на `/me`.
- `POST /me/unclaim` (`client_id`) → 303 на `/me`.
- `GET /me/history`: нет сессии → `/me/login`; нет действующих привязок → `/me`; иначе `history_rows` → `build_history(..., diploma_ids=set(_diploma_event_ids()), codes={ev.name: ev.code for ev in settings.EVENTS.values()})` → `me-history.html`.
- Все обращения к БД — `run_in_threadpool`.

Тексты ошибок у формы (по `r`): `mismatch` «Дата не совпадает», `limit` «Слишком много попыток. Попробуйте завтра или напишите нам на 1@krasmarafon.ru», `taken` «Эту карточку уже заявили — напишите нам на 1@krasmarafon.ru», `no_birthday` «Подтвердить не получится — напишите нам на 1@krasmarafon.ru», `date` «Проверьте дату».

**`me.html`:** в шапке группы-человека с `client_id`:
- заявлена → плашка «Это вы · История →» (ссылка `/me/history`);
- снята сейчас (`dropped`) → пояснение «Данные карточки изменились — подтвердите, что это вы» + кнопка;
- иначе — кнопка «Это я» (`<details>`/`<summary>` без JS: раскрывает форму `POST /me/claim` с `<input type="date" name="birthday" required>` и «Подтвердить»); при `?claim={id}` — форма этой карточки раскрыта (`open`) и показан текст ошибки.

**`me-history.html`** (новый, по образцу `me.html`: те же `<link>` — `km-design-tokens.css`, `krasmarafon-header.css`, `navigation.css`, `krasmarafon-footer.css`, `me.css`; шапка/подвал), компоновка H1 по макету (`.superpowers/brainstorm/1478-1793707115/content/history-layout.html` — открыть и повторить структуру):
- «← Личный кабинет», ФИ, «Бегает с {since}»;
- 4 плитки; «Личные рекорды»; «Динамика» — чипы дистанций + `<canvas>`, данные — `<script type="application/json" id="dyn">{{ dynamics|tojson }}</script>`, Chart.js `/static/lib/chart4/chart.umd.min.js`, ось Y — время `ч:мм:сс`, перевёрнутая (быстрее — выше), цвет `#EE2D62`; блок скрыт, если `dynamics` пуст;
- «Забеги и заявки» по годам: ticket — как билет на `/me`; result — строка как в «Результатах» `/me` + темп;
- внизу: `mailto:1@krasmarafon.ru?subject=Ошибка%20в%20истории%2C%20карточка%20№{id}` «Нашли чужой забег? Сообщить об ошибке» (номера заявленных карточек через запятую) и по каждой карточке форма `POST /me/unclaim` «Это не моя карточка №{id} — отвязать» с `onsubmit="return confirm('Отвязать карточку №{id}? История пропадёт из кабинета.')"`.
- Локально `static/lib` может отсутствовать (скачивается при деплое `deploy/download_static_libs.py`): если нет `static/lib/chart4/chart.umd.min.js` в worktree — скопировать папку `static/lib` из основного репозитория `C:\Users\podbo\Работа\КРАСМАРАФОН\KM_track\static\lib` (не коммитить; проверить, что `static/lib` в `.gitignore`), иначе запустить скрипт скачивания.

**Стили** — дописать в `static/css/me.css` (токены сайта; плитки 4 в ряд и на 390px).

- [ ] Интеграционные тесты в `tests/integration/test_athlete_claims.py` через `TestClient(app, base_url="https://testserver")` и вход как в `test_athlete_routes.py` (код из перехваченного `send_mail`): «Это я» видна; неверная ДР → «Дата не совпадает» у формы; верная → плашка «Это вы»; `/me/history` 200 с ФИ, плитками, строкой результата; без привязок → редирект `/me`; без сессии → `/me/login`; переключатель выключен → 404; чужая карточка в `/me/claim` → 404; отвязка; после правки ДР карточки — пояснение «Данные карточки изменились».
- [ ] Скриншоты (agent-browser, локальный сервер уже запущен на :8000 из этого worktree с `--reload`; кабинет локально скрыт — для скриншотов временно создать `config/athlete_cabinet_enabled.local` с `true` и потом удалить): `/me` с кнопкой и раскрытой формой, `/me/history` — 1280px и 390px; посмотреть самому и описать в отчёте, что видно. Для входа — запросить код через форму на тестовую почту, код взять из лога сервера (`C:\Users\podbo\AppData\Local\Temp\claude\c--Users-podbo--------------------KM-track\b438ba73-a6e9-4baa-84c7-4f6dd0d0a921\tasks\bqoemx203.output`, строка `MAIL (log) to=…`). Нужна тестовая почта с заявками и карточкой с результатами — создать скриптом (и удалить после) или использовать фикстуру-скрипт.
- [ ] Commit `feat(auth): «Это я» и страница истории спортсмена`.

---

### Task 6: Админка — возможные дубли

- `GET /api/admin/athlete-cabinet-duplicates` (`api_require_auth`) → `{"accounts": duplicate_accounts()}`.
- `admin.html`: под переключателем «Личный кабинет» — блок «Кабинет: возможные дубли» (загрузка при открытии, как `loadAthleteCabinetToggle`): таблица «почта — карточки (№, ФИ, ДР)»; пусто → «Нет». Только просмотр. Если в админке есть экран человека по номеру карточки в «Качестве данных» — ссылка на него, иначе просто номер.
- Проверить, как журнал «Качества данных» (`/api/admin/data-quality/actions`, `dq_actions.py` ~строка 636) показывает новые действия `athlete_claim`/`athlete_unclaim`: не должно падать; отменять их нельзя (`UNDOABLE` не расширять).
- [ ] Тест: эндпоинт требует вход (401); с входом — аккаунт с двумя привязками в ответе.
- [ ] Commit `feat(auth): возможные дубли карточек из кабинета в админке`.

---

### Task 7: Полный прогон и передача пользователю

- [ ] `tests/unit/ -q` и интеграционные: `test_athlete_*.py`, `test_lead_pd_refused.py`, `test_history_toggle_routes.py`, `test_diploma_route.py`, `test_admin_data_quality.py`, `test_dq_cases_db.py`, `test_data_quality_undo.py` — все зелёные (известные падения Siberman к задаче не относятся).
- [ ] Чек-лист для пользователя (код входа — пришлю из лога; кабинет локально включить галочкой в `/admin` или войти в админку): «Это я» с неверной и верной ДР; плашка; история (итоги, рекорды, динамика, лента, протокол/диплом); отвязка; 390px.
- [ ] Obsidian «текущие приоритеты» — статус Б1. Выкладка (миграция `athlete_claims.sql` + push) — только после «да» пользователя.
