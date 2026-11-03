"""Выбор действия перепривязки строки после правки ФИ/ДР — чистая логика без БД."""
import pytest

from src.analytics.dq_actions import _decide

ROW = {"surname": "Иванова", "name": "Анна", "birthday": "2015-04-05"}


def test_match_is_current_card_means_nothing_to_do():
    assert _decide(ROW, card_id=10, other_rows=3, match=10)[0] == "none"


def test_other_card_with_same_fio_and_bd_means_move_even_if_current_card_has_no_other_rows():
    assert _decide(ROW, card_id=10, other_rows=0, match=20)[0] == "move"
    assert _decide(ROW, card_id=10, other_rows=5, match=20)[0] == "move"


def test_no_card_and_current_card_has_no_other_rows_means_rename():
    assert _decide(ROW, card_id=10, other_rows=0, match=None)[0] == "rename"


def test_no_card_and_current_card_has_other_rows_means_new_card():
    assert _decide(ROW, card_id=10, other_rows=1, match=None)[0] == "new_card"


@pytest.mark.parametrize("bd", [None, "", "1900-01-01", "1905-01-01"])
def test_placeholder_or_empty_birthday_is_skipped_for_any_match(bd):
    for match in (None, 10, 20):
        action, reason = _decide({**ROW, "birthday": bd}, card_id=10, other_rows=0, match=match)
        assert action == "skip" and reason


@pytest.mark.parametrize("field", ["surname", "name"])
def test_empty_surname_or_name_is_skipped(field):
    assert _decide({**ROW, field: ""}, card_id=10, other_rows=0, match=None)[0] == "skip"


@pytest.mark.parametrize("card_id", [None, 0])
def test_row_without_card_is_skipped(card_id):
    assert _decide(ROW, card_id=card_id, other_rows=0, match=None)[0] == "skip"


def test_every_decision_has_a_reason():
    for match, other in ((10, 0), (20, 0), (None, 0), (None, 2)):
        assert _decide(ROW, card_id=10, other_rows=other, match=match)[1]
