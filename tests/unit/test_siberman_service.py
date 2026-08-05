import pytest
from unittest.mock import patch
from src.siberman.parser import ParseResult
from src.siberman.service import (
    format_seconds, format_pace, compute_split_times,
    convert_bike_times_to_elapsed, BIKE_DAY2_BASE_START_S,
    _finished_stage, SWIM_LAP_SEQS, STAGE_MAX_SEQ, _recompute_records,
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


def test_convert_bike_times_partial_bike1_excluded_from_ranking():
    # bib1 дошёл только до ПЕРВОЙ КТ вело-1 (seq=1, не финиш seq=6) — не
    # должен получать расчётный старт дня 2 (найдено пользователем
    # 2026-08-04: до фикса "_last_cp is not None" срабатывало на ЛЮБОЙ
    # достигнутой КТ, а не только на финише — стартовый лист вело-2
    # появлялся/заполнялся раньше времени, ещё до того как хоть кто-то
    # реально финишировал вело-1).
    participants = [
        {"bib": "1", "format": "individual"},
        {"bib": "2", "format": "individual"},
    ]
    cp = {
        "1": {("swim", 7): 3600, ("bike_day1", 1): RACE_START_S + 3600 + 300},  # только 3 км, не финиш
        "2": {("swim", 7): 3600, ("bike_day1", 6): RACE_START_S + 3600 + 1800},  # финишировал
    }
    result = _mk_result(participants, cp)
    starts = convert_bike_times_to_elapsed(result, RACE_START_S)

    assert "1" not in starts
    assert starts["2"] == BIKE_DAY2_BASE_START_S


def test_finished_stage_true_when_last_seq_present():
    cp = {("run", 12): 30000, ("run", 8): 20000}
    assert _finished_stage(cp, "run") is True


def test_finished_stage_false_partial_no_dnf_marker():
    # Сошёл на середине бега, но без явной пометки DNF в файле — только
    # промежуточные КТ присутствуют, финишной (seq=12) нет.
    cp = {("run", 8): 20000, ("run", 9): 22000}
    assert _finished_stage(cp, "run") is False


def test_finished_stage_false_no_data():
    assert _finished_stage({}, "swim") is False


def test_swim_lap_seqs_covers_exactly_four_laps_ending_at_max_seq():
    assert sorted(SWIM_LAP_SEQS.values()) == [1, 2, 3, 4]
    assert max(SWIM_LAP_SEQS) == STAGE_MAX_SEQ["swim"]


def test_swim_lap_seqs_excludes_turn_checkpoints():
    # seq 1,3,5 — развороты на середине круга, не входят в счётчик кругов
    assert set(SWIM_LAP_SEQS) == {2, 4, 6, 7}


def _mk_pr(race_year, participants):
    r = ParseResult(race_year=race_year)
    r.participants = participants
    return r


def _finish_cp(stage):
    return {(stage, STAGE_MAX_SEQ[stage]): 1}


def _full_finish_cp():
    cp = {}
    for s in ("swim", "bike_day1", "bike_day2", "run"):
        cp.update(_finish_cp(s))
    return cp


def test_recompute_records_individual_full_finisher_writes_broad_and_individual_categories():
    result = _mk_pr(2026, [
        {"bib": "1", "format": "individual", "surname": "Иванов", "name": "Пётр", "gender": "M"},
    ])
    cp_key_to_pid = {"1": 100}
    pid_totals = {100: {"swim": 8000, "bike_day1": 30000, "bike_day2": 50000, "run": 20000, "overall": 108000}}
    pid_meta = {100: {"status": "active", "format": "individual", "gender": "M", "relay_stage": "none"}}
    pid_cp_times = {100: _full_finish_cp()}
    with patch("src.siberman.service.write_best_record") as m:
        _recompute_records(None, result, cp_key_to_pid, pid_totals, pid_meta, pid_cp_times, {})
    calls = {(c.args[1], c.args[2]): c.args[3] for c in m.call_args_list}
    # "overall" — только absolute + _individual (никогда "male"/"female" без "_individual")
    assert ("overall", "absolute") in calls
    assert ("overall", "male_individual") in calls
    assert ("overall", "male") not in calls
    assert ("overall", "female_individual") not in calls
    # Этапные колонки — обе категории (широкая + личная)
    for column in ("swim", "bike_total", "run"):
        assert (column, "absolute") in calls
        assert (column, "male") in calls
        assert (column, "male_individual") in calls
        assert (column, "female") not in calls
    # candidates — список [(value, name, team)]
    assert calls[("swim", "absolute")] == [(8000, "Иванов Пётр", None)]
    assert calls[("bike_total", "absolute")] == [(30000 + 50000, "Иванов Пётр", None)]
    assert calls[("run", "absolute")] == [(20000, "Иванов Пётр", None)]


def test_recompute_records_individual_live_mid_race_only_finished_segments_are_candidates():
    # 2026-08-05, второй раунд: рекорд должен быть виден LIVE — участник
    # ещё бежит бег (гонка не завершена), но уже реально финишировал
    # заплыв и вело-2 — должен быть кандидатом на swim/bike_total, но НЕ
    # на overall/run (они ещё не пройдены).
    result = _mk_pr(2026, [
        {"bib": "1", "format": "individual", "surname": "Иванов", "name": "Пётр", "gender": "M"},
    ])
    cp_key_to_pid = {"1": 100}
    pid_totals = {100: {"swim": 8000, "bike_day1": 30000, "bike_day2": 50000, "run": None, "overall": None}}
    pid_meta = {100: {"status": "active", "format": "individual", "gender": "M", "relay_stage": "none"}}
    cp = {}
    cp.update(_finish_cp("swim"))
    cp.update(_finish_cp("bike_day1"))
    cp.update(_finish_cp("bike_day2"))
    pid_cp_times = {100: cp}
    with patch("src.siberman.service.write_best_record") as m:
        _recompute_records(None, result, cp_key_to_pid, pid_totals, pid_meta, pid_cp_times, {})
    calls = {(c.args[1], c.args[2]): c.args[3] for c in m.call_args_list}
    assert ("swim", "absolute") in calls
    assert ("bike_total", "absolute") in calls
    assert ("overall", "absolute") not in calls
    assert ("run", "absolute") not in calls


def test_recompute_records_individual_dnf_excluded_even_for_already_finished_segments():
    # Финишировал заплыв реально быстро, но потом сошёл (dnf) — не
    # кандидат вообще ни на что, даже на уже пройденный заплыв (решение
    # пользователя: dnf убирает упоминание рекорда).
    result = _mk_pr(2026, [
        {"bib": "1", "format": "individual", "surname": "Иванов", "name": "Пётр", "gender": "M"},
    ])
    cp_key_to_pid = {"1": 100}
    pid_totals = {100: {"swim": 8000, "bike_day1": None, "bike_day2": None, "run": None, "overall": None}}
    pid_meta = {100: {"status": "dnf", "format": "individual", "gender": "M", "relay_stage": "none"}}
    pid_cp_times = {100: _finish_cp("swim")}
    with patch("src.siberman.service.write_best_record") as m:
        _recompute_records(None, result, cp_key_to_pid, pid_totals, pid_meta, pid_cp_times, {})
    m.assert_not_called()


def test_recompute_records_relay_team_writes_broad_categories_only_no_overall():
    result = _mk_pr(2026, [
        {"bib": "10", "_cp_key": "10:swim", "format": "relay", "relay_stage": "swim", "relay_team_name": "КомандаА", "surname": "Смирнова", "name": "Анна", "gender": "F"},
        {"bib": "10", "_cp_key": "10:bike", "format": "relay", "relay_stage": "bike", "relay_team_name": "КомандаА", "surname": "Кузнецов", "name": "Олег", "gender": "M"},
        {"bib": "10", "_cp_key": "10:run", "format": "relay", "relay_stage": "run", "relay_team_name": "КомандаА", "surname": "Попова", "name": "Вера", "gender": "F"},
    ])
    cp_key_to_pid = {"10:swim": 200, "10:bike": 201, "10:run": 202}
    pid_totals = {
        200: {"swim": 7000},
        201: {"bike_day1": 25000, "bike_day2": 45000},
        202: {"run": 18000},
    }
    pid_meta = {
        200: {"status": "active", "format": "relay", "gender": "F", "relay_stage": "swim"},
        201: {"status": "active", "format": "relay", "gender": "M", "relay_stage": "bike"},
        202: {"status": "active", "format": "relay", "gender": "F", "relay_stage": "run"},
    }
    pid_cp_times = {
        200: _finish_cp("swim"),
        201: {**_finish_cp("bike_day1"), **_finish_cp("bike_day2")},
        202: _finish_cp("run"),
    }
    relay_by_bib = {"10": {"swim": 200, "bike": 201, "run": 202}}
    with patch("src.siberman.service.write_best_record") as m:
        _recompute_records(None, result, cp_key_to_pid, pid_totals, pid_meta, pid_cp_times, relay_by_bib)
    calls = {(c.args[1], c.args[2]): c.args[3] for c in m.call_args_list}
    # Эстафета никогда не пишет "overall" (личное достижение, не сумма троих)
    assert not any(k[0] == "overall" for k in calls)
    # "..._individual" не пишется эстафете — только absolute + широкая гендерная
    assert ("swim", "absolute") in calls
    assert ("swim", "female") in calls
    assert ("swim", "female_individual") not in calls
    assert calls[("swim", "absolute")] == [(7000, "Смирнова Анна", "КомандаА")]
    assert ("bike_total", "male") in calls
    assert calls[("bike_total", "absolute")] == [(25000 + 45000, "Кузнецов Олег", "КомандаА")]
    assert ("run", "female") in calls
    assert calls[("run", "absolute")] == [(18000, "Попова Вера", "КомандаА")]


def test_recompute_records_relay_team_partial_completion_is_evaluated_per_role():
    # 2026-08-05, второй раунд: бегун сошёл (dnf) — но пловец и
    # велосипедист СВОИ этапы реально прошли и всё ещё активны, значит
    # команда всё же кандидат на swim/bike_total (не только на "команда
    # финишировала целиком", как было раньше) — просто НЕ на run.
    result = _mk_pr(2026, [
        {"bib": "10", "_cp_key": "10:swim", "format": "relay", "relay_stage": "swim", "relay_team_name": "КомандаБ", "surname": "А", "name": "Б", "gender": "M"},
        {"bib": "10", "_cp_key": "10:bike", "format": "relay", "relay_stage": "bike", "relay_team_name": "КомандаБ", "surname": "В", "name": "Г", "gender": "M"},
        {"bib": "10", "_cp_key": "10:run", "format": "relay", "relay_stage": "run", "relay_team_name": "КомандаБ", "surname": "Д", "name": "Е", "gender": "M"},
    ])
    cp_key_to_pid = {"10:swim": 300, "10:bike": 301, "10:run": 302}
    pid_totals = {300: {"swim": 7500}, 301: {"bike_day1": 26000, "bike_day2": 46000}, 302: {"run": None}}
    pid_meta = {
        300: {"status": "active", "format": "relay", "gender": "M", "relay_stage": "swim"},
        301: {"status": "active", "format": "relay", "gender": "M", "relay_stage": "bike"},
        302: {"status": "dnf", "format": "relay", "gender": "M", "relay_stage": "run"},
    }
    pid_cp_times = {
        300: _finish_cp("swim"),
        301: {**_finish_cp("bike_day1"), **_finish_cp("bike_day2")},
        302: {},
    }
    relay_by_bib = {"10": {"swim": 300, "bike": 301, "run": 302}}
    with patch("src.siberman.service.write_best_record") as m:
        _recompute_records(None, result, cp_key_to_pid, pid_totals, pid_meta, pid_cp_times, relay_by_bib)
    calls = {(c.args[1], c.args[2]): c.args[3] for c in m.call_args_list}
    assert ("swim", "absolute") in calls
    assert ("bike_total", "absolute") in calls
    assert not any(k[0] == "run" for k in calls)
