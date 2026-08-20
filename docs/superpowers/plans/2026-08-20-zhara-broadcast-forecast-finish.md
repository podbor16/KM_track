# Прогноз финиша в live-JSON топ-10 — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить поле `forecast_finish_time` (прогноз чистого финишного времени, чч:мм:сс, без астрономического времени) в записи top10-списков на промежуточных КТ live-JSON для трансляции Жары.

**Architecture:** Новая чистая функция `_forecast_finish_seconds()` (линейная экстраполяция среднего темпа с начала гонки на оставшуюся дистанцию) + проброс `remaining_km` через уже существующие `_build_checkpoint()`/`generate_top10_json()` — без новых запросов к БД, всё нужное уже читается текущим кодом.

**Tech Stack:** Python 3.13, pytest (conda base env), без внешних зависимостей.

**Дизайн:** `docs/superpowers/specs/2026-08-20-zhara-broadcast-forecast-finish-design.md`

---

## File Structure

- Modify: `src/krasmarafon/services/live_top10_export.py` — новая функция `_forecast_finish_seconds()`, новый опциональный параметр `remaining_km` в `_build_checkpoint()`, проброс из `generate_top10_json()`
- Test: `tests/unit/test_live_top10_export.py` — существующий файл, дополняется (текущее состояние: 17 тестов, уже прочитано целиком)

Один файл делает всё (сборка одного JSON) — уже устоявшаяся структура модуля, разбивать не нужно, изменение точечное.

---

### Task 1: `_forecast_finish_seconds()` — чистая функция расчёта прогноза

**Files:**
- Modify: `src/krasmarafon/services/live_top10_export.py`
- Test: `tests/unit/test_live_top10_export.py`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/unit/test_live_top10_export.py`, сразу после блока импорта в самом верху файла (после `from src.krasmarafon.services.live_top10_export import (_td_to_seconds, _seconds_to_hms, _seconds_to_pace_str, _format_gap, _sex_code, _format_distance_label,)`), добавить `_forecast_finish_seconds` в этот же импорт:

```python
from src.krasmarafon.services.live_top10_export import (
    _td_to_seconds, _seconds_to_hms, _seconds_to_pace_str, _format_gap,
    _sex_code, _format_distance_label, _forecast_finish_seconds,
)
```

Затем добавить тесты (после `test_format_distance_label_keeps_decimal`, перед строкой `from src.krasmarafon.services.live_top10_export import _build_checkpoint`):

```python
def test_forecast_finish_seconds_extrapolates_remaining_distance():
    # elapsed 1:10:00 = 4200с, темп 5:00/км = 300с/км, осталось 1.1 км
    assert _forecast_finish_seconds(4200.0, 300.0, 1.1) == 4530.0


def test_forecast_finish_seconds_none_pace_returns_none():
    """Темп неизвестен — прогноз невозможен, не 0 (явно отличимо от
    "прогноз совпадает с текущим временем")."""
    assert _forecast_finish_seconds(4200.0, None, 1.1) is None


def test_forecast_finish_seconds_zero_remaining_returns_elapsed():
    assert _forecast_finish_seconds(4200.0, 300.0, 0.0) == 4200.0


def test_forecast_finish_seconds_negative_remaining_does_not_raise():
    """checkpoint_distances может содержать небольшую неточность —
    формула не должна падать, просто даёт прогноз чуть меньше текущего
    времени на КТ (не вводит в заблуждение при таких малых величинах)."""
    assert _forecast_finish_seconds(4200.0, 300.0, -0.5) == 4050.0
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -k forecast_finish_seconds -v`
Expected: FAIL — `ImportError: cannot import name '_forecast_finish_seconds'`

- [ ] **Step 3: Добавить функцию в `live_top10_export.py`**

Открыть `src/krasmarafon/services/live_top10_export.py`, найти функцию `_format_gap()` (строки 56-67):

```python
def _format_gap(seconds: float) -> str:
    """+ММ:СС (+ЧЧ:ММ:СС если ≥ часа), "Лидер" у первого места (0 или
    отрицательное — защита от погрешности округления при сравнении лидера
    с самим собой)."""
    if seconds <= 0:
        return "Лидер"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"+{h:02d}:{m:02d}:{s:02d}"
    return f"+{m:02d}:{s:02d}"
```

Сразу после неё добавить:

```python
def _forecast_finish_seconds(
    time_clear_seconds: float, pace_avg_seconds_per_km: Optional[float], remaining_km: float,
) -> Optional[float]:
    """Прогноз финишного времени (elapsed/чистое, БЕЗ астрономического
    времени) — линейная экстраполяция среднего темпа с начала гонки
    (тот же темп, что уже даёт pace_avg_kt* в БД) на оставшуюся дистанцию.
    None, если темп неизвестен — отсутствие прогноза, не "прогноз
    совпадает с текущим временем"."""
    if pace_avg_seconds_per_km is None:
        return None
    return time_clear_seconds + remaining_km * pace_avg_seconds_per_km
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -k forecast_finish_seconds -v`
Expected: `4 passed`

- [ ] **Step 5: Коммит**

```bash
git add src/krasmarafon/services/live_top10_export.py tests/unit/test_live_top10_export.py
git commit -m "feat(krasmarafon): _forecast_finish_seconds() — расчёт прогноза финиша"
```

---

### Task 2: Прогноз в `_build_checkpoint()` + проброс из `generate_top10_json()`

**Files:**
- Modify: `src/krasmarafon/services/live_top10_export.py`
- Test: `tests/unit/test_live_top10_export.py`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/unit/test_live_top10_export.py`, сразу после `test_build_checkpoint_truncates_below_ten_without_padding` (перед блоком `from src.krasmarafon.services import live_top10_export`):

```python
def test_build_checkpoint_adds_forecast_finish_time_when_remaining_km_given():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur

    abs_rows = [_row(10, "Иванов", "Мужчина", "Красноярск", 1, 1, "01:10:00", "5:00")]
    cur.fetchall.side_effect = [abs_rows, abs_rows, []]

    checkpoint = _build_checkpoint(
        conn, event_id=116, code="kt6", label="КТ6 (20.2 км)",
        time_col="time_clear_kt6", rank_abs_col="rank_absolute_kt6",
        rank_sex_col="rank_sex_kt6", pace_col="pace_avg_kt6",
        photo_map={}, remaining_km=0.9,
    )

    # elapsed 4200с + 0.9км × 300с/км = 4470с = 01:14:30
    assert checkpoint["top10_absolute"][0]["forecast_finish_time"] == "01:14:30"


def test_build_checkpoint_omits_forecast_finish_time_without_remaining_km():
    """Блок "finish" не передаёт remaining_km (используется дефолт None) —
    поле должно ПОЛНОСТЬЮ ОТСУТСТВОВАТЬ в записи, не быть null."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    rows = [_row(10, "Иванов", "Мужчина", "Красноярск", 1, 1, "01:40:00", "4:44")]
    cur.fetchall.side_effect = [rows, rows, []]

    checkpoint = _build_checkpoint(
        conn, event_id=116, code="finish", label="Финиш",
        time_col="time_clear_finish", rank_abs_col="rank_absolute_clean",
        rank_sex_col="rank_sex_clean", pace_col="finish_pace_avg_clean",
        photo_map={},
    )

    assert "forecast_finish_time" not in checkpoint["top10_absolute"][0]
```

Добавить в конец файла (после `test_generate_top10_json_creates_parent_directory`):

```python
def test_generate_top10_json_passes_remaining_km_to_intermediate_checkpoints_only(tmp_path, monkeypatch):
    """Проверяет саму связку generate_top10_json → _build_checkpoint:
    промежуточные КТ получают remaining_km = event_distance - checkpoint_distances[i],
    финиш — не получает remaining_km вовсе (дефолт None)."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = {
        "event_name": "Жара", "event_distance": 21.1, "event_year": 2026,
        "checkpoint_distances": "[0, 5.0, 6.0, 10.55, 14.65, 15.65, 20.2, 21.1]",
    }
    cur.fetchall.return_value = []

    captured = {}

    def fake_build_checkpoint(connection, event_id, code, label, remaining_km=None, **kwargs):
        captured[code] = remaining_km
        return {"code": code, "label": label, "top10_absolute": [], "top10_male": [], "top10_female": []}

    monkeypatch.setattr(live_top10_export, "_build_checkpoint", fake_build_checkpoint)

    output_path = str(tmp_path / "zhara_21km_top10.json")
    generate_top10_json(conn, event_id=116, output_path=output_path)

    assert captured["kt1"] == 21.1 - 5.0
    assert captured["kt6"] == 21.1 - 20.2
    assert captured["finish"] is None
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -k "adds_forecast_finish_time or passes_remaining_km" -v`
Expected: FAIL — `test_build_checkpoint_adds_forecast_finish_time_when_remaining_km_given` падает с `TypeError: _build_checkpoint() got an unexpected keyword argument 'remaining_km'`; `test_generate_top10_json_passes_remaining_km_to_intermediate_checkpoints_only` падает с `AssertionError: assert None == 16.1` (remaining_km нигде ещё не пробрасывается, `captured["kt1"]` остаётся `None`)

(`test_build_checkpoint_omits_forecast_finish_time_without_remaining_km` пройдёт уже сейчас — поля `forecast_finish_time` в коде ещё не существует вовсе, это ожидаемо; тест остаётся как постоянная защита инварианта после реализации Step 3.)

- [ ] **Step 3: Добавить `remaining_km` в `_build_checkpoint()` и проброс из `generate_top10_json()`**

В `src/krasmarafon/services/live_top10_export.py` найти текущее определение `_build_checkpoint()` (строки 114-155):

```python
def _build_checkpoint(
    connection, event_id: int, code: str, label: str, time_col: str,
    rank_abs_col: str, rank_sex_col: str, pace_col: str,
    photo_map: Dict[int, str],
) -> Dict[str, Any]:
    abs_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col)
    male_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col, sex_filter="Мужчина")
    female_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col, sex_filter="Женщина")

    leader_abs_s = _td_to_seconds(abs_rows[0]["time_clear"]) if abs_rows else None
    leader_male_s = _td_to_seconds(male_rows[0]["time_clear"]) if male_rows else None
    leader_female_s = _td_to_seconds(female_rows[0]["time_clear"]) if female_rows else None

    def build_list(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for rec in rows:
            seconds = _td_to_seconds(rec["time_clear"])
            leader_sex_s = leader_male_s if rec["sex"] == "Мужчина" else leader_female_s
            pace_seconds = _td_to_seconds(rec["pace_avg"])
            result.append({
                "start_number": rec["start_number"],
                "surname": rec["surname"],
                "name": rec["name"],
                "sex": _sex_code(rec["sex"]),
                "city": rec.get("city") or "",
                "rank_absolute": int(rec["rank_absolute"]) if rec["rank_absolute"] is not None else None,
                "rank_sex": int(rec["rank_sex"]) if rec["rank_sex"] is not None else None,
                "time": _seconds_to_hms(seconds),
                "pace": _seconds_to_pace_str(pace_seconds) if pace_seconds is not None else None,
                "gap_absolute": _format_gap(seconds - leader_abs_s) if leader_abs_s is not None else "Лидер",
                "gap_sex": _format_gap(seconds - leader_sex_s) if leader_sex_s is not None else "Лидер",
                "photo_url": photo_map.get(rec["start_number"], PARTICIPANT_PHOTO_PLACEHOLDER_URL),
            })
        return result

    return {
        "code": code,
        "label": label,
        "top10_absolute": build_list(abs_rows),
        "top10_male": build_list(male_rows),
        "top10_female": build_list(female_rows),
    }
```

Заменить целиком на:

```python
def _build_checkpoint(
    connection, event_id: int, code: str, label: str, time_col: str,
    rank_abs_col: str, rank_sex_col: str, pace_col: str,
    photo_map: Dict[int, str], remaining_km: Optional[float] = None,
) -> Dict[str, Any]:
    abs_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col)
    male_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col, sex_filter="Мужчина")
    female_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col, sex_filter="Женщина")

    leader_abs_s = _td_to_seconds(abs_rows[0]["time_clear"]) if abs_rows else None
    leader_male_s = _td_to_seconds(male_rows[0]["time_clear"]) if male_rows else None
    leader_female_s = _td_to_seconds(female_rows[0]["time_clear"]) if female_rows else None

    def build_list(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for rec in rows:
            seconds = _td_to_seconds(rec["time_clear"])
            leader_sex_s = leader_male_s if rec["sex"] == "Мужчина" else leader_female_s
            pace_seconds = _td_to_seconds(rec["pace_avg"])
            entry = {
                "start_number": rec["start_number"],
                "surname": rec["surname"],
                "name": rec["name"],
                "sex": _sex_code(rec["sex"]),
                "city": rec.get("city") or "",
                "rank_absolute": int(rec["rank_absolute"]) if rec["rank_absolute"] is not None else None,
                "rank_sex": int(rec["rank_sex"]) if rec["rank_sex"] is not None else None,
                "time": _seconds_to_hms(seconds),
                "pace": _seconds_to_pace_str(pace_seconds) if pace_seconds is not None else None,
                "gap_absolute": _format_gap(seconds - leader_abs_s) if leader_abs_s is not None else "Лидер",
                "gap_sex": _format_gap(seconds - leader_sex_s) if leader_sex_s is not None else "Лидер",
                "photo_url": photo_map.get(rec["start_number"], PARTICIPANT_PHOTO_PLACEHOLDER_URL),
            }
            if remaining_km is not None:
                forecast_seconds = _forecast_finish_seconds(seconds, pace_seconds, remaining_km)
                if forecast_seconds is not None:
                    entry["forecast_finish_time"] = _seconds_to_hms(forecast_seconds)
            result.append(entry)
        return result

    return {
        "code": code,
        "label": label,
        "top10_absolute": build_list(abs_rows),
        "top10_male": build_list(male_rows),
        "top10_female": build_list(female_rows),
    }
```

Затем найти в `generate_top10_json()` цикл построения промежуточных КТ (строки 196-204):

```python
    checkpoints = []
    for i in range(1, num_kt + 1):
        checkpoints.append(_build_checkpoint(
            connection, event_id,
            code=f"kt{i}", label=f"КТ{i} ({checkpoint_distances[i]} км)",
            time_col=f"time_clear_kt{i}", rank_abs_col=f"rank_absolute_kt{i}",
            rank_sex_col=f"rank_sex_kt{i}", pace_col=f"pace_avg_kt{i}",
            photo_map=photo_map,
        ))
```

Заменить на (добавлена ровно одна строка `remaining_km=...`):

```python
    checkpoints = []
    for i in range(1, num_kt + 1):
        checkpoints.append(_build_checkpoint(
            connection, event_id,
            code=f"kt{i}", label=f"КТ{i} ({checkpoint_distances[i]} км)",
            time_col=f"time_clear_kt{i}", rank_abs_col=f"rank_absolute_kt{i}",
            rank_sex_col=f"rank_sex_kt{i}", pace_col=f"pace_avg_kt{i}",
            photo_map=photo_map,
            remaining_km=float(event["event_distance"]) - checkpoint_distances[i],
        ))
```

Вызов `_build_checkpoint()` для `code="finish"` (несколькими строками ниже) НЕ трогать — `remaining_km` там по-прежнему не передаётся, используется дефолт `None`.

- [ ] **Step 4: Запустить все тесты файла, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_live_top10_export.py -v`
Expected: `24 passed` (17 существующих + 4 из Task 1 + 3 из Task 2)

- [ ] **Step 5: Коммит**

```bash
git add src/krasmarafon/services/live_top10_export.py tests/unit/test_live_top10_export.py
git commit -m "feat(krasmarafon): forecast_finish_time в live-JSON топ-10 для промежуточных КТ"
```

---

## Итог

2 задачи, каждая с собственным коммитом. Task 1 — изолированная чистая функция расчёта (легко тестируется отдельно от БД/сети). Task 2 — интеграция в уже существующий пайплайн сборки JSON, без новых запросов к БД, обратно совместимо (существующие тесты `_build_checkpoint`/`generate_top10_json` без `remaining_km` продолжают работать благодаря дефолту `None`).
