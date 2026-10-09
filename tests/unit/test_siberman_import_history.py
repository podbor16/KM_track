import pytest

from scripts.siberman_import_history import (
    assign_seqs, drop_outliers, fill_relay_names, guess_gender, km_of,
)
from src.siberman.service import STAGE_MAX_SEQ


def test_bike_finish_always_max_seq_with_fewer_checkpoints():
    # 2016–2017: на вело-1 нет «3 км» и «142 км»
    seqs = assign_seqs("bike_day1", ["10 км", "72 км (разворот)", "135 км", "Финиш 145 км"])
    assert [s for s, _, _ in seqs] == [1, 2, 3, STAGE_MAX_SEQ["bike_day1"]]
    assert seqs[-1][1:] == ("Финиш (145 км)", 145.0)


def test_bike_too_many_checkpoints_rejected():
    with pytest.raises(ValueError):
        assign_seqs("bike_day1", ["1 км", "2 км", "3 км", "4 км", "5 км", "6 км", "Финиш 145 км"])


def test_swim_seq_by_distance_not_by_column_order():
    # Счётчик кругов заплыва завязан на seq (SWIM_LAP_SEQS) — без разворотов
    # круги не должны съехать на seq 1..3.
    seqs = assign_seqs("swim", ["2,6 км", "5,2 км", "7,8 км", "Финиш 10 км"])
    assert [s for s, _, _ in seqs] == [2, 4, 6, 7]


def test_run_seq_is_lap_number():
    seqs = assign_seqs("run", ["1 круг (7 км)", "2 круга (14 км)", "12 кругов (84 км)"])
    assert [(s, km) for s, _, km in seqs] == [(1, 7.0), (2, 14.0), (12, 84.0)]
    assert seqs[-1][1] == "Финиш — 12 круг (84 км)"


def test_km_of_comma_decimal():
    assert km_of("1,3 км") == 1.3


def test_relay_surname_only_filled_from_rating_with_last_minute_swap():
    # 2017 SiberWoman: в протоколе «Артемьева», в рейтинге «Шпенглер Екатерина»
    rating = [("Другая", ["Иванов Иван", "Петров Пётр", "Сидоров Сидор"]),
              ("SiberWoman", ["Шпенглер Екатерина", "Ламакина Ольга", "Торгунова Инга"])]
    assert fill_relay_names(["Артемьева", "Ламакина", "Торгунова"], rating) == \
        ["Шпенглер Екатерина", "Ламакина Ольга", "Торгунова Инга"]


def test_relay_full_names_kept_as_is():
    assert fill_relay_names(["Кузьмин Александр", "Павленко Тимур", "Рызов Игорь"], []) == \
        ["Кузьмин Александр", "Павленко Тимур", "Рызов Игорь"]


def test_relay_without_rating_team_rejected():
    with pytest.raises(ValueError):
        fill_relay_names(["Артемьева", "Ламакина", "Торгунова"], [("X", ["А Б", "В Г", "Д Е"])])


@pytest.mark.parametrize("surname,name,expected", [
    ("Грибенко", "Елена", "F"), ("Ярощук", "Николай", "M"), ("Брума", "Никита", "M"),
    ("Гуль", "Анфиса", "F"), ("Кавун", "Андрей", "M"),
])
def test_guess_gender(surname, name, expected):
    assert guess_gender(surname, name) == expected


def test_drop_outliers_typo_between_neighbours():
    # 2024 Русскин: 4-й круг «5:33:43» между 2:23:32 и 4:01:23
    cp = {("run", 3): 8612, ("run", 4): 20023, ("run", 5): 14483, ("run", 6): 17379}
    notes = drop_outliers(cp, "№50")
    assert cp[("run", 4)] is None and cp[("run", 5)] == 14483
    assert len(notes) == 1


def test_drop_outliers_keeps_monotonic_and_none():
    cp = {("run", 1): 100, ("run", 2): None, ("run", 3): 300}
    assert drop_outliers(cp, "№1") == []
    assert cp == {("run", 1): 100, ("run", 2): None, ("run", 3): 300}
