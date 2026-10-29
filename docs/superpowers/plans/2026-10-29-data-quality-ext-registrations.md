# «Качество данных»: внешние регистрации («Бум») — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Таблица исторических регистраций «Бум.xlsx» (45 тыс. строк 2016–2022 по всем забегам, с ДР/телефоном/почтой) становится справочником в БД; по нему «Качество данных» находит настоящие ДР для заглушек, двойников по телефону/почте и расхождения ДР; 48 надёжных ДР записываются сразу.

**Решения пользователя (2026-10-29):** делать п.1 (48 надёжных ДР — сразу, журналом), п.2 (вопросы: ДР «только по ФИО» 146 + неоднозначные 7, «один телефон/почта» 37 пар), п.3 (расхождение ДР) — по правилу поддержки: наша ДР — истина, если строк (заявок+результатов) с нашей ДР больше, чем записей таблицы с другой ДР, ИЛИ наша последняя строка свежее; вопрос — если таблица и многочисленнее, и свежее; при равенстве — вопрос. Пробелы импорта (198 строк) — не трогать.

**Architecture:** Миграция `ext_registrations` + скрипт загрузки; `dq_checks` грузит справочник в `Data.ext` (полная загрузка — целиком, `load_scoped` — по фамилиям/телефонам набора) и три новые проверки: `X-BD`, `X-PHONE`, `X-BDDIFF`; `dq_cases` — вопросы и ответ `bd:<дата>` (ДР карточки + строк с заглушкой); разовый скрипт применения 48 надёжных ДР через `dq_actions` (журнал, отмена).

**Tech Stack:** Python 3.13, MySQL, pytest, openpyxl.

---

## Общее

- Тесты: `C:/Users/podbo/miniconda3/python.exe -m pytest <пути> -q -p no:warnings` (DB-тесты — по одному прогону за раз, маркеры с суффиксом прогона как в `tests/integration/test_dq_cases_db.py`).
- Файл с ПДн — только локально: `C:\Users\podbo\Downloads\Бум (2).xlsx`; в репозиторий не класть; в выводе скриптов маскировать телефон (`923…87`) и почту (`…@домен`).
- Нормализация как в `scratchpad` сверки: телефон — последние 10 цифр; почта — `strip().lower()`, пропускать `example@…`; ДР — дата 1920–2025, иначе NULL; ФИО — как в таблице (`norm` при сравнении).
- Записи на прод — только в Task 6, после подтверждения (подтверждено пользователем 2026-10-29 для этих действий).
- Коммиты — с `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### Task 1: Справочник `ext_registrations` и загрузка

**Files:** Create `migrations/ext_registrations.sql`, `scripts/import_ext_registrations.py`, `tests/unit/test_import_ext_registrations.py`.

- Миграция:
```sql
-- Внешние регистрации (сборный дамп Tilda «Бум.xlsx», 2016–2022, все забеги) — справочник для «Качества данных»:
-- настоящие ДР для заглушек, двойники по телефону/почте, расхождения ДР. Не заявки: в leads не попадают.
CREATE TABLE IF NOT EXISTS ext_registrations (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(40) NOT NULL,
    source_row INT UNSIGNED NOT NULL,
    surname VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    birthday DATE NULL,
    sex CHAR(1) NOT NULL DEFAULT '',
    phone VARCHAR(10) NOT NULL DEFAULT '',
    email VARCHAR(255) NOT NULL DEFAULT '',
    product VARCHAR(255) NOT NULL DEFAULT '',
    event_year SMALLINT UNSIGNED NULL,
    UNIQUE KEY uq_ext_source_row (source, source_row),
    KEY idx_ext_surname (surname),
    KEY idx_ext_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```
- Скрипт `scripts/import_ext_registrations.py --file <xlsx> --source boom [--apply]`: лист «Все участники», колонки по заголовку (`surname, name, sex, birthday, phone, email, product`), год — первое `(19|20)\d{2}` в `product`; пропуск строк без фамилии/имени; dry-run по умолчанию (число строк, с ДР, с телефоном); `--apply` — в транзакции `DELETE FROM ext_registrations WHERE source = %s`, затем пакетный INSERT (по 1000). Подключение — `src.analytics.db_pool.get_pooled_connection` (локально — `.env.local`, на проде — `.env` сервера).
- Unit-тесты на чистые функции разбора: ДР (datetime, `dd.mm.yyyy`, мусор, 1905 → None), телефон (`+7 (923) …` → 10 цифр, короткий → ''), год из товара, почта.
- Применить на локальной БД (`--apply`), проверить число строк. Коммит `feat(data-quality): справочник внешних регистраций (ext_registrations) и его загрузка`.

### Task 2: Данные проверок — справочник и контакты заявок

**Files:** `src/analytics/dq_checks.py`.

- `COLUMNS["leads"]` += `phone, email`; `COLUMNS["ext_registrations"] = "id, surname, name, birthday, sex, phone, email, product, event_year"`.
- `Data(..., ext=())`: хранит `ext` и индексы `ext_by_fio[(norm s, norm n)]`, `ext_by_phone`, `ext_by_email`; для карточек — `card_phones[cid]`, `card_emails[cid]` из заявок (нормализованные как в «Общее»); `phone_cards`, `email_cards`. ДР в ext — строкой `YYYY-MM-DD` или ''.
- `load()` грузит `ext_registrations` целиком (если таблицы нет — пустой список, без ошибки: `SHOW TABLES LIKE`).
- `load_scoped`: ext — строки с фамилией из ключей набора ИЛИ телефоном/почтой карточек набора; плюс карточки, у заявок которых этот телефон/почта (для X-PHONE) — со всеми их строками.
- Тест эквивалентности card-scope из этапа 2 должен остаться зелёным; добавить случаи с телефоном.
- Коммит `feat(data-quality): справочник регистраций и контакты заявок в данных проверок`.

### Task 3: Три проверки

**Files:** `src/analytics/dq_checks.py` (+ `run_checks`), `tests/unit/test_data_quality.py`.

Константа «надёжная ДР»: `real(b) = real_bd(b) and not b.endswith("-01-01")`.

1. **X-BD** «ДР найдена в регистрациях»: карточка с результатами и ДР-заглушкой или `ГГГГ-01-01`; кандидаты — ext с тем же ФИ (или переставленным) и `real` ДР (для `ГГГГ-01-01` — того же года). Сильные — у которых телефон/почта есть среди контактов карточки. Если сильные есть — только их ДР. Finding(`X-BD`, severity `high` если сильные и одна ДР, иначе `medium`, `client_ids=(cid,)`, `fix=tuple(sorted ДР)`, message «ДР в регистрациях: …»; ключ — стандартный `X-BD::<cid>`).
2. **X-PHONE** «Один телефон/почта у двух карточек»: пары карточек из `phone_cards`/`email_cards` с той же фамилией (`norm`) и совместимым именем (`names_compatible`) или переставленным ФИ; пары, которые уже даёт C-TWIN, не повторять. Finding(`X-PHONE`, `high` если ДР равны или «близки» (`compatible_bd`), иначе `low` (обычно родитель и ребёнок с общим телефоном), `client_ids=(a, b)`).
3. **X-BDDIFF** «ДР расходится с регистрациями»: карточка с `real` ДР; ext с тем же ФИ и телефоном/почтой карточки и `real` ДР, отличающейся больше чем на год. Поддержка: `ours` = число строк карточки (заявки+результаты) с ДР = ДР карточки, `ours_last` = максимальный год их событий; `theirs` = число ext-строк с этой другой ДР, `theirs_last` = максимальный `event_year`. Находка только если НЕ (`ours > theirs` ИЛИ `ours_last > theirs_last`). Finding(`X-BDDIFF`, `medium`, `client_ids=(cid,)`, `fix=(другая ДР,)`, message с числами поддержки).

- `run_checks` добавляет три проверки; card-scope — фильтр по `client_ids` как у остальных.
- Unit-тесты на данных в памяти: заглушка + сильный кандидат (high), только ФИО (medium, несколько ДР), `ГГГГ-01-01` — кандидат другого года отбрасывается; X-PHONE — та же ДР (high), родитель/ребёнок (low), пара уже C-TWIN — нет дубля; X-BDDIFF — 3 наших строки против 1 регистрации (нет находки), 1 наша старая против 2 свежих регистраций (находка), равенство (находка).
- Прогон на локальной БД (после Task 1): числа находок по трём кодам — в отчёт (ориентир с прода: X-BD 201, X-PHONE 37, X-BDDIFF — заметно меньше 153).
- Коммит `feat(data-quality): проверки по регистрациям — ДР для заглушек, один телефон, расхождение ДР`.

### Task 4: Вопросы и ответы

**Files:** `src/analytics/dq_cases.py`, `tests/unit/test_dq_cases.py`, `tests/integration/test_dq_cases_db.py`.

- `STAGES`: `X-PHONE` → 1, `X-BD` → 3, `X-BDDIFF` → 3.
- Вопросы (без кодов, нейтрально):
  - X-BD: «Иванов Иван: в карточке ДР не указана (или «только год 1985»). В регистрациях на «РЖД 2019», «Жара 2021»: ДР 1985-07-14. Записать?» — ответы `bd:<дата>` на каждую ДР (★ — если находка high), `keep` «Оставить как есть», `postpone`. В подсказке — откуда: «совпал телефон/почта» или «совпали только фамилия и имя — проверьте».
  - X-PHONE: «У … и … один телефон/почта. Это один человек?» — ответы как у C-TWIN (`merge` с предложением `propose_final`, ★ только если high и без предохранителей; `different`; `postpone`); подсказка для low — «обычно так регистрируют ребёнка с телефона родителя».
  - X-BDDIFF: «… ДР в карточке 1986-07-04 (подтверждена N строками, последняя — 2019), в регистрациях — 1998-07-04 (M раз, последняя — 2021). Какая верная?» — `bd:<другая>`, `keep` «Как в карточке», `postpone`; без ★.
- Ответ `bd:<YYYY-MM-DD>` (X-BD, X-BDDIFF): `edit_record(clients, cid, {birthday})` (конфликт ФИ+ДР с другой карточкой — как у R-CARD: `conflict` + `merge_with`), затем каждой строке карточки (заявки и результаты) с ДР-заглушкой, `ГГГГ-01-01` того же года или прежней ДР карточки — `edit_record(table, id, {birthday})`. Все действия — в `action_ids`.
- `_live_ok`: эти ответы — правка полей (в «живом» забеге — нельзя; на деле не встречается, но правило общее).
- Тесты: unit — матрица ответов (заглушки dq_actions) для `bd:`, `merge`, `different`, `keep`; integration — `bd:` на локальной БД: карточка и строки с заглушкой получили ДР, отмена всех действий возвращает.
- Коммит `feat(data-quality): вопросы по регистрациям — записать ДР, один телефон, расхождение ДР`.

### Task 5: Разовое применение 48 надёжных ДР

**Files:** Create `scripts/apply_ext_birthdays.py`.

- Берёт находки `X-BD` с severity `high` (одна ДР, совпал телефон/почта) из полного прогона и для каждой выполняет ту же цепочку, что ответ `bd:<дата>` (`dq_cases.apply_answer` с `user="admin (Claude)"`); dry-run по умолчанию — таблица «ФИО · было → станет · забеги · совпало по»; `--apply` — выполнить, вывести id действий журнала. Конфликты ФИ+ДР — не применять, вывести отдельно (останутся вопросами).
- Проверить на локальной БД (dry-run и `--apply` на копии), затем — Task 6.
- Коммит `feat(scripts): применение надёжных ДР из регистраций (журнал, отмена)`.

### Task 6: Прод

- [ ] Полный прогон тестов; деплой (после подтверждения — получено 2026-10-29).
- [ ] Миграция `ext_registrations.sql` на проде (как прочие миграции — через SSH-скрипт `deploy/ssh_apply_migrations.py` или вручную).
- [ ] Загрузка: файл — во временный каталог VPS (`chmod 700`), `scripts/import_ext_registrations.py --apply`, файл удалить; проверить число строк.
- [ ] `scripts/apply_ext_birthdays.py` — dry-run (список в отчёт пользователю), затем `--apply`.
- [ ] Вкладка «Качество данных» на проде: новые дела видны, вопросы читаемые (только открыть).
- [ ] Ревью в `.taskmaster/tasks/todo.md`.
