import pytest
from src.siberman.parser import ParseResult
from src.siberman.service import (
    format_seconds, format_pace, compute_split_times,
    convert_bike_times_to_elapsed, BIKE_DAY2_BASE_START_S,
)

RACE_START_S = 8 * 3600  # 08:00:00


def test_format_seconds_full():
    assert format_seconds(8647) == "2:24:07"


def test_format_seconds_zero():
    assert format_seconds(0) == "0:00:00"


def test_format_seconds_none():
    assert format_seconds(None) == "—"


def test_format_pace_normal():
    # 375 сек/км → "6:15"
    assert format_pace(375) == "6:15"


def test_format_pace_none():
    assert format_pace(None) == "—"


def test_compute_split_times_basic():
    # Накопленные: [100, 350, 600] → сплиты: [100, 250, 250]
    cumulative = [100, 350, 600]
    splits = compute_split_times(cumulative)
    assert splits == [100, 250, 250]


def test_compute_split_times_with_none():
    # None в середине → соответствующий сплит тоже None
    cumulative = [100, None, 600]
    splits = compute_split_times(cumulative)
    assert splits[0] == 100
    assert splits[1] is None
    assert splits[2] is None


def _mk_result(participants, checkpoint_times) -> ParseResult:
    r = ParseResult(race_year=2026)
    r.participants = participants
    r.checkpoint_times = checkpoint_times
    return r


def test_convert_bike_times_basic_two_individuals():
    # bib1: swim finish elapsed=3600, bike_day1 30 мин → faster, rank 1
    # bib2: swim finish elapsed=3600, bike_day1 60 мин → slower, rank 2
    participants = [
        {"bib": "1", "format": "individual"},
        {"bib": "2", "format": "individual"},
    ]
    cp = {
        "1": {("swim", 7): 3600, ("bike_day1", 6): RACE_START_S + 3600 + 1800,
              ("bike_day2", 8): RACE_START_S + 100},
        "2": {("swim", 7): 3600, ("bike_day1", 6): RACE_START_S + 3600 + 3600,
              ("bike_day2", 8): RACE_START_S + 200},
    }
    result = _mk_result(participants, cp)
    starts = convert_bike_times_to_elapsed(result, RACE_START_S)

    assert result.checkpoint_times["1"][("bike_day1", 6)] == 5400
    assert result.checkpoint_times["2"][("bike_day1", 6)] == 7200

    assert starts == {"1": BIKE_DAY2_BASE_START_S, "2": BIKE_DAY2_BASE_START_S + 180}
    assert result.checkpoint_times["1"][("bike_day2", 8)] == 100
    assert result.checkpoint_times["2"][("bike_day2", 8)] == 20


def test_convert_bike_times_top5_vs_rank6_formula():
    # 6 райдеров с разным bike_day1 total (600с интервал) — без плавания (0)
    participants = [{"bib": str(i), "format": "individual"} for i in range(1, 7)]
    cp = {
        str(i): {
            ("swim", 7): 0,
            ("bike_day1", 6): RACE_START_S + i * 600,
        }
        for i in range(1, 7)
    }
    result = _mk_result(participants, cp)
    starts = convert_bike_times_to_elapsed(result, RACE_START_S)

    assert starts["1"] == BIKE_DAY2_BASE_START_S               # ранг 1: +0
    assert starts["2"] == BIKE_DAY2_BASE_START_S + 180          # ранг 2: +3мин
    assert starts["5"] == BIKE_DAY2_BASE_START_S + 4 * 180      # ранг 5: +12мин
    assert starts["6"] == BIKE_DAY2_BASE_START_S + 4 * 180 + 60  # ранг 6: +12мин+1мин


def test_convert_bike_times_ties_get_same_start():
    # bib1 и bib2 — одинаковый bike_day1 total → одинаковый ранг → одинаковый старт
    participants = [
        {"bib": "1", "format": "individual"},
        {"bib": "2", "format": "individual"},
        {"bib": "3", "format": "individual"},
    ]
    cp = {
        "1": {("swim", 7): 0, ("bike_day1", 6): RACE_START_S + 1800},
        "2": {("swim", 7): 0, ("bike_day1", 6): RACE_START_S + 1800},
        "3": {("swim", 7): 0, ("bike_day1", 6): RACE_START_S + 3600},
    }
    result = _mk_result(participants, cp)
    starts = convert_bike_times_to_elapsed(result, RACE_START_S)

    assert starts["1"] == starts["2"] == BIKE_DAY2_BASE_START_S
    # ранг 3 (не 2, т.к. 1 и 2 разделили первое место) → +6 мин
    assert starts["3"] == BIKE_DAY2_BASE_START_S + 360


def test_convert_bike_times_relay_uses_team_swim_total():
    # Команда: пловец cp_key "10:swim", велосипедист cp_key "10:bike".
    # Личник bib "20" — быстрее по итогу вело-1, должен получить ранг 1.
    participants = [
        {"bib": "10", "format": "relay", "relay_stage": "swim"},
        {"bib": "10", "format": "relay", "relay_stage": "bike"},
        {"bib": "20", "format": "individual"},
    ]
    cp = {
        "10:swim": {("swim", 7): 3600},
        "10:bike": {("bike_day1", 6): RACE_START_S + 3600 + 3600,   # total=3600 (60 мин)
                    ("bike_day2", 8): RACE_START_S + 50},
        "20": {("swim", 7): 0, ("bike_day1", 6): RACE_START_S + 1800},  # total=1800 (30 мин), быстрее
    }
    result = _mk_result(participants, cp)
    starts = convert_bike_times_to_elapsed(result, RACE_START_S)

    assert starts["20"] == BIKE_DAY2_BASE_START_S             # ранг 1 — личник
    assert starts["10:bike"] == BIKE_DAY2_BASE_START_S + 180  # ранг 2 — эстафета
    assert "10:swim" not in starts  # пловец не райдер, старт вело-2 не считается для него
    assert result.checkpoint_times["10:bike"][("bike_day1", 6)] == 7200


def test_convert_bike_times_dnf_excluded_from_ranking():
    # bib1 не финишировал вело-1 (нет cp) → не участвует в ранжировании
    participants = [
        {"bib": "1", "format": "individual"},
        {"bib": "2", "format": "individual"},
    ]
    cp = {
        "1": {("swim", 7): 3600},  # нет bike_day1
        "2": {("swim", 7): 3600, ("bike_day1", 6): RACE_START_S + 3600 + 1800},
    }
    result = _mk_result(participants, cp)
    starts = convert_bike_times_to_elapsed(result, RACE_START_S)

    assert "1" not in starts
    assert starts["2"] == BIKE_DAY2_BASE_START_S
