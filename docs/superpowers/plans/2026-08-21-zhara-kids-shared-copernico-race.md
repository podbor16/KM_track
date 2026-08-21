# Жара + Детский забег — общий Copernico race_id — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `RaceLoader.fetch_from_copernico()` поддерживает список Copernico `event`-значений на одну дистанцию (нужно для Детского забега — 6 возрастных групп по году рождения в один `db_event_id=113`), плюс реальные конфиг-значения для Жары 5км и Детского забега 1км и новый preset-файл.

**Architecture:** Минимальное расширение существующей функции — `self.copernico_event` принимает строку (как сейчас) или список строк; при списке делаются последовательные запросы, результаты сливаются в один плоский список участников. Код ниже по потоку не меняется — он уже агностичен к источнику строк. `gun_time_utc` обновляется только при одиночном событии.

**Tech Stack:** Python 3.13, pytest + `unittest.mock` (conda base env), PyYAML.

**Дизайн:** `docs/superpowers/specs/2026-08-21-zhara-kids-shared-copernico-race-design.md`

---

## File Structure

- Modify: `load_race_results.py` — `fetch_from_copernico()` (строки 381-418)
- Test: `tests/unit/test_fetch_from_copernico.py` (новый файл)
- Modify: `config/events/zhara.yaml` — дистанция «5 км», блок `copernico`
- Modify: `config/events/kids.yaml` — дистанция «1 км», блок `copernico`
- Create: `config/copernico/km_analytics.yaml` — новый preset-файл
- Test: `tests/unit/test_event_config_copernico.py` (новый файл) — верификация, что YAML-конфиги и preset корректно резолвятся через уже существующую `_load_event_config()`

---

### Task 1: `fetch_from_copernico()` — список событий на одну дистанцию

**Files:**
- Modify: `load_race_results.py:381-418`
- Test: `tests/unit/test_fetch_from_copernico.py` (создать)

- [x] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_fetch_from_copernico.py`:

```python
"""Тесты для RaceLoader.fetch_from_copernico() — поддержка списка Copernico
event-значений на одну дистанцию (нужно для Детского забега, где 6
возрастных групп по году рождения объединяются в один db_event_id)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from load_race_results import RaceLoader


def make_loader(copernico_event):
    """RaceLoader с замоканным логгером и заданными Copernico-параметрами —
    без реального __init__ (без БД/сети), по образцу make_loader() в
    tests/unit/test_bulk_upsert.py."""
    logger = MagicMock()
    loader = RaceLoader.__new__(RaceLoader)
    loader.logger = logger
    loader.copernico_race_id = "--2026-6118"
    loader.copernico_login = "podbor250718@gmail.com"
    loader.copernico_preset = "km_analytics"
    loader.copernico_event = copernico_event
    loader.gun_time_utc = None
    return loader


def _fake_response(runners, gun_time=None):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    payload = {"data": runners}
    if gun_time:
        payload["gunTime"] = gun_time
    resp.json.return_value = payload
    return resp


class TestFetchFromCopernicoSingleEvent:
    """Регрессия — поведение с одной строкой event не должно измениться
    (все уже настроенные события Красмарафона используют одну строку)."""

    @patch("requests.get")
    def test_single_event_returns_runners_and_updates_gun_time(self, mock_get):
        loader = make_loader("5km")
        mock_get.return_value = _fake_response(
            [{"dorsal": 1, "surname": "Иванов"}], gun_time="2026-08-22T03:30:00.000Z"
        )

        runners = loader.fetch_from_copernico()

        assert runners == [{"dorsal": 1, "surname": "Иванов"}]
        assert loader.gun_time_utc == "2026-08-22T03:30:00.000Z"
        assert mock_get.call_count == 1
        url = mock_get.call_args.args[0]
        assert url.endswith("/5km")


class TestFetchFromCopernicoEventList:
    @patch("requests.get")
    def test_merges_runners_from_all_events(self, mock_get):
        loader = make_loader(["1km-2020", "1km-2019"])
        mock_get.side_effect = [
            _fake_response([{"dorsal": 2118, "surname": None}], gun_time="2026-08-22T03:30:00.000Z"),
            _fake_response([{"dorsal": 9014, "surname": "Рековская"}], gun_time="2026-08-22T03:45:00.000Z"),
        ]

        runners = loader.fetch_from_copernico()

        assert len(runners) == 2
        assert {r["dorsal"] for r in runners} == {2118, 9014}
        assert mock_get.call_count == 2

    @patch("requests.get")
    def test_gun_time_utc_not_updated_for_multiple_events(self, mock_get):
        """У каждой возрастной группы своё время старта — нет одного
        корректного значения для общего поля на весь db_event_id."""
        loader = make_loader(["1km-2020", "1km-2019"])
        mock_get.side_effect = [
            _fake_response([{"dorsal": 2118}], gun_time="2026-08-22T03:30:00.000Z"),
            _fake_response([{"dorsal": 9014}], gun_time="2026-08-22T03:45:00.000Z"),
        ]

        loader.fetch_from_copernico()

        assert loader.gun_time_utc is None

    @patch("requests.get")
    def test_one_failing_sub_event_does_not_break_the_rest(self, mock_get):
        loader = make_loader(["1km-2020", "1km-2019", "1km-2018"])

        def side_effect(url, **kwargs):
            if "1km-2019" in url:
                raise ConnectionError("timeout")
            if "1km-2020" in url:
                return _fake_response([{"dorsal": 2118}])
            return _fake_response([{"dorsal": 8008}])

        mock_get.side_effect = side_effect

        runners = loader.fetch_from_copernico()

        assert {r["dorsal"] for r in runners} == {2118, 8008}
        assert mock_get.call_count == 3

    @patch("requests.get")
    def test_all_sub_events_failing_returns_empty_list(self, mock_get):
        loader = make_loader(["1km-2020", "1km-2019"])
        mock_get.side_effect = ConnectionError("timeout")

        runners = loader.fetch_from_copernico()

        assert runners == []
```

- [x] **Step 2: Запустить тесты, убедиться что падают**

Run: `conda run -n base python -m pytest tests/unit/test_fetch_from_copernico.py -v`
Expected: FAIL — `test_single_event_returns_runners_and_updates_gun_time` падает, т.к. `requests.get` сейчас не патчится (реальный код делает `import requests as _req` и обращается к настоящему API) — тест либо зависнет на реальном сетевом запросе, либо упадёт по таймауту/ошибке подключения, а не по логике. Тесты на список событий (`TestFetchFromCopernicoEventList`) упадут с `AttributeError` или неверным числом вызовов `mock_get` (текущий код делает РОВНО ОДИН запрос, используя `self.copernico_event` напрямую как строку — при списке `urllib.parse.quote(self.copernico_event)` упадёт с `TypeError`, т.к. `quote()` не принимает список).

- [x] **Step 3: Переписать `fetch_from_copernico()`**

Найти в `load_race_results.py` текущее определение (строки 381-418):

```python
    def fetch_from_copernico(self) -> List[Dict]:
        """Получить данные из Copernico API."""
        if not all([self.copernico_race_id, self.copernico_login, self.copernico_preset, self.copernico_event]):
            self.logger.error("❌ Не заданы все параметры Copernico API")
            return []

        encoded_preset = urllib.parse.quote(self.copernico_preset)
        encoded_event = urllib.parse.quote(self.copernico_event)
        url = f"https://public-api.copernico.cloud/api/races/{self.copernico_race_id}/preset/{self.copernico_login}:::{encoded_preset}/{encoded_event}"
        self.logger.info(f"📡 Запрос к Copernico API: {url}")
        try:
            import requests as _req
            response = _req.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=(10, 150))
            response.raise_for_status()
            data = response.json()
            self.logger.debug(f"Ответ API: тип={type(data).__name__}, размер={len(data) if isinstance(data, (list, dict)) else '?'}")
            if isinstance(data, dict) and 'data' in data:
                runners = data['data']
                gun_time = data.get('gunTime')
                # Fallback: gunTime может быть per-runner полем
                if not gun_time and runners:
                    gun_time = runners[0].get('gunTime')
                if gun_time:
                    self.gun_time_utc = gun_time
            elif isinstance(data, list):
                runners = data
                if runners:
                    gun_time = runners[0].get('gunTime')
                    if gun_time:
                        self.gun_time_utc = gun_time
            else:
                self.logger.error(f"❌ Неожиданный формат ответа: {type(data)}")
                return []
            self.logger.info(f"✅ Получено {len(runners)} участников из API")
            return runners
        except Exception as e:
            self.logger.error(f"❌ Ошибка при запросе к API: {e}")
            return []
```

Заменить целиком на:

```python
    def fetch_from_copernico(self) -> List[Dict]:
        """Получить данные из Copernico API. copernico_event может быть
        строкой (один event) или списком строк (несколько event —
        сливаются в один плоский список участников, напр. несколько
        возрастных групп одной дистанции). gun_time_utc обновляется
        ТОЛЬКО при одном event — при списке событий у каждого своё время
        старта, общее поле на event_id писать нечем (не искажаем
        реальность одним случайным значением)."""
        if not all([self.copernico_race_id, self.copernico_login, self.copernico_preset, self.copernico_event]):
            self.logger.error("❌ Не заданы все параметры Copernico API")
            return []

        events = self.copernico_event if isinstance(self.copernico_event, list) else [self.copernico_event]
        all_runners: List[Dict] = []
        for event in events:
            encoded_preset = urllib.parse.quote(self.copernico_preset)
            encoded_event = urllib.parse.quote(event)
            url = f"https://public-api.copernico.cloud/api/races/{self.copernico_race_id}/preset/{self.copernico_login}:::{encoded_preset}/{encoded_event}"
            self.logger.info(f"📡 Запрос к Copernico API: {url}")
            try:
                import requests as _req
                response = _req.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=(10, 150))
                response.raise_for_status()
                data = response.json()
                self.logger.debug(f"Ответ API: тип={type(data).__name__}, размер={len(data) if isinstance(data, (list, dict)) else '?'}")
                if isinstance(data, dict) and 'data' in data:
                    runners = data['data']
                    gun_time = data.get('gunTime')
                    # Fallback: gunTime может быть per-runner полем
                    if not gun_time and runners:
                        gun_time = runners[0].get('gunTime')
                elif isinstance(data, list):
                    runners = data
                    gun_time = runners[0].get('gunTime') if runners else None
                else:
                    self.logger.error(f"❌ Неожиданный формат ответа для event={event}: {type(data)}")
                    continue
                if gun_time and len(events) == 1:
                    self.gun_time_utc = gun_time
                self.logger.info(f"✅ Получено {len(runners)} участников из API (event={event})")
                all_runners.extend(runners)
            except Exception as e:
                self.logger.error(f"❌ Ошибка при запросе к API (event={event}): {e}")
                continue
        return all_runners
```

- [x] **Step 4: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_fetch_from_copernico.py -v`
Expected: `5 passed`

- [x] **Step 5: Прогнать уже существующие тесты загрузчика — убедиться, что не сломалось**

Run: `conda run -n base python -m pytest tests/unit/test_bulk_upsert.py -v`
Expected: все тесты по-прежнему проходят (файл не менялся, но `fetch_from_copernico()` — часть того же класса `RaceLoader`)

- [x] **Step 6: Коммит**

```bash
git add load_race_results.py tests/unit/test_fetch_from_copernico.py
git commit -m "feat(krasmarafon): fetch_from_copernico() — поддержка списка event на одну дистанцию"
```

---

### Task 2: `zhara.yaml`/`kids.yaml` — реальные значения race_id/event

**Files:**
- Modify: `config/events/zhara.yaml`
- Modify: `config/events/kids.yaml`
- Test: `tests/unit/test_event_config_copernico.py` (создать)

- [x] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_event_config_copernico.py`:

```python
"""Верификация блоков copernico в config/events/zhara.yaml и kids.yaml —
race_id общий для Жары и Детского забега, event: строка у Жары 5км,
список из 6 возрастных групп у Детского забега 1км."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from load_race_results import _load_event_config

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_zhara_5km_copernico_config():
    dist_cfg = _load_event_config(str(PROJECT_ROOT / "config/events/zhara.yaml"), "5 км")
    cop = dist_cfg["copernico"]
    assert cop["race_id"] == "--2026-6118"
    assert cop["event"] == "5km"
    assert cop["preset"] == "km_analytics"


def test_zhara_21km_copernico_not_touched():
    """21.1 км ещё не создана в Copernico — конфиг не должен был измениться
    в рамках этой задачи."""
    dist_cfg = _load_event_config(str(PROJECT_ROOT / "config/events/zhara.yaml"), "21.1 км")
    cop = dist_cfg["copernico"]
    assert cop["race_id"] is None


def test_kids_1km_copernico_config_has_all_six_age_groups():
    dist_cfg = _load_event_config(str(PROJECT_ROOT / "config/events/kids.yaml"), "1 км")
    cop = dist_cfg["copernico"]
    assert cop["race_id"] == "--2026-6118"
    assert cop["event"] == [
        "1km-2020", "1km-2019", "1km-2018", "1km-2017", "1km-2016", "1km-2015",
    ]
    assert cop["preset"] == "km_analytics"
```

- [x] **Step 2: Запустить тесты, убедиться что падают**

Run: `conda run -n base python -m pytest tests/unit/test_event_config_copernico.py -v`
Expected: FAIL — `test_zhara_5km_copernico_config` и `test_kids_1km_copernico_config_has_all_six_age_groups` падают на `assert cop["race_id"] == "--2026-6118"` (сейчас там `None`); `test_zhara_21km_copernico_not_touched` проходит уже сейчас (эту дистанцию не трогаем)

- [x] **Step 3: Обновить `config/events/zhara.yaml`**

Найти в файле блок дистанции «5 км»:

```yaml
    copernico:
      race_id: null           # ← отдельный race_id для дистанции 5 км
      login: "podbor250718@gmail.com"
      preset: "km_analytics"
      event: "5 км"
```

Заменить на:

```yaml
    copernico:
      race_id: "--2026-6118"
      login: "podbor250718@gmail.com"
      preset: "km_analytics"
      event: "5km"
```

Блок дистанции «21.1 км» НЕ трогать — остаётся с `race_id: null`.

- [x] **Step 4: Обновить `config/events/kids.yaml`**

Найти в файле блок дистанции «1 км»:

```yaml
    copernico:
      race_id: null           # ← заполнить перед стартом
      login: "podbor250718@gmail.com"
      preset: "km_analytics"
      event: "1 км"
```

Заменить на:

```yaml
    copernico:
      race_id: "--2026-6118"
      login: "podbor250718@gmail.com"
      preset: "km_analytics"
      event:
        - "1km-2020"
        - "1km-2019"
        - "1km-2018"
        - "1km-2017"
        - "1km-2016"
        - "1km-2015"
```

Блок дистанции «500 м» НЕ трогать (у неё нет секции `copernico`).

- [x] **Step 5: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_event_config_copernico.py -v`
Expected: `3 passed`

- [x] **Step 6: Коммит**

```bash
git add config/events/zhara.yaml config/events/kids.yaml tests/unit/test_event_config_copernico.py
git commit -m "feat(krasmarafon): race_id/event для Жары 5км и Детского забега 1км (Copernico)"
```

---

### Task 3: `config/copernico/km_analytics.yaml` — новый preset-файл

**Files:**
- Create: `config/copernico/km_analytics.yaml`
- Test: `tests/unit/test_event_config_copernico.py` (дополнить)

- [ ] **Step 1: Написать падающий тест**

Добавить в конец `tests/unit/test_event_config_copernico.py`:

```python
import yaml as _yaml


def test_km_analytics_preset_exists_and_has_expected_fields():
    """Без этого файла загрузчик не стартует (parser.error при отсутствии
    config/copernico/<preset>.yaml) — см. load_race_results.py main()."""
    preset_path = PROJECT_ROOT / "config/copernico/km_analytics.yaml"
    assert preset_path.exists(), f"Preset-файл не найден: {preset_path}"

    preset = _yaml.safe_load(preset_path.read_text(encoding="utf-8"))

    assert preset["fields"]["bib"] == "dorsal"
    assert preset["fields"]["surname"] == "surname"
    assert preset["fields"]["name"] == "name"
    assert preset["fields"]["birthdate"] == "birthdate"
    assert preset["fields"]["gender"] == "gender"
    assert preset["fields"]["status"] == "status"
    assert preset["fields"]["category"] == "category"

    assert preset["time_fields"]["gun_start"] == "times.official_:::start:::"
    assert preset["time_fields"]["gun_finish"] == "times.official_:::finish:::"
    assert preset["time_fields"]["chip_start"] is None
    assert preset["time_fields"]["chip_finish"] is None

    assert preset["checkpoint_fields"] == {}
```

- [ ] **Step 2: Запустить тест, убедиться что падает**

Run: `conda run -n base python -m pytest tests/unit/test_event_config_copernico.py -k km_analytics_preset -v`
Expected: FAIL — `assert preset_path.exists()` (файла ещё нет)

- [ ] **Step 3: Создать `config/copernico/km_analytics.yaml`**

По образцу уже существующего `config/copernico/km_vesna_5km_2026.yaml`:

```yaml
description: "Жара 5км + Детский забег 1км (6 возрастных групп), race_id --2026-6118. Chip-времена не включены в пресет (нет times.real_*). Контрольные точки трассы отсутствуют — единственные КТ-поля, которые сейчас отдаёт Copernico по этому race_id, физически принадлежат дистанции 21.1 км, которой ещё нет в Copernico (появятся здесь же или в отдельном preset-файле, когда организатор её создаст)."

fields:
  bib: dorsal
  surname: surname
  name: name
  birthdate: birthdate
  gender: gender
  status: status
  category: category

time_fields:
  gun_start:   "times.official_:::start:::"
  gun_finish:  "times.official_:::finish:::"
  chip_start:  null
  chip_finish: null

checkpoint_fields: {}
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_event_config_copernico.py -v`
Expected: `4 passed`

- [ ] **Step 5: Коммит**

```bash
git add config/copernico/km_analytics.yaml tests/unit/test_event_config_copernico.py
git commit -m "feat(krasmarafon): config/copernico/km_analytics.yaml — preset для Жары/Детского забега"
```

---

## Итог

3 задачи, каждая с собственным коммитом. Task 1 — изолированное расширение существующей функции (полная обратная совместимость с уже настроенными событиями — Весна, Первомайский и т.д., у них `event` остаётся одиночной строкой). Task 2-3 — конфигурационные изменения с верификационными тестами через уже существующую `_load_event_config()`. Реальный запуск загрузчика (`--init`/`--continuous`) на этих конфигах — вне рамок плана, по решению пользователя (участники ещё не полностью выгружены организатором).
