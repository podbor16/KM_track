from datetime import date
from io import BytesIO
from unittest.mock import Mock

import pytest
from openpyxl import load_workbook

from src.siberman.draw import service
from src.siberman.draw.chances import MAIN_COLUMNS, READY_COLUMN, external_start_bonus
from src.siberman.draw.importer import COL_EXTRA, COL_TOTAL, EXTRA_COLS, parse_applicants
from src.siberman.persons.linking import plain_key


DOB = date(1985, 1, 1)
NAME = {"surname": "Тестов", "name": "Алексей"}


def start(event_id, birthdate=DOB, year=2026):
    return dict(NAME, event_id=event_id, race_year=year, birthdate=birthdate)


@pytest.mark.parametrize(("rows", "reported", "birthdate", "expected", "issue"), [
    ([start(1), start(1, None), start(2), start(3, year=2029)], 2, DOB, 2, False),
    ([start(1), start(2, None)], 1, DOB, None, True),
    ([start(1, date(1990, 1, 1))], 0, DOB, 0, False),
    ([start(1, date(1990, 1, 1))], 1, DOB, None, True),
    ([start(1)], 2, DOB, 1, True),
    ([start(1, date(1990, 1, 1))], None, DOB, None, True),
    ([start(1, None)], 0, DOB, None, True),
    ([start(1)], 0, None, None, True),
    ([], 0, DOB, None, True),
    (None, 0, DOB, None, True),
])
def test_external_start_bonus(rows, reported, birthdate, expected, issue):
    value, _, warning = external_start_bonus(
        rows, race="Дуатлон 222", name_key=plain_key(**NAME), birthdate=birthdate,
        reported=reported, through_year=2028,
    )
    assert value == expected
    assert bool(warning) == issue


def test_cycling_relay_rosters_are_reviewed_even_when_application_reports_zero(monkeypatch):
    team = {
        "surname": "Команда", "name": "Тестов Алексей, Мария Примерова",
        "category": "Эстафета", "birthdate": DOB, "status": "finished", "laps": 100,
    }
    conn = Mock()
    conn.cursor.return_value.fetchall.return_value = [
        dict(team, event_id=1, race_year=2025, duration_hours=24),
        dict(team, event_id=2, race_year=2026, duration_hours=24),
        dict(team, event_id=3, race_year=2027, duration_hours=6),
    ]
    monkeypatch.setattr(service, "get_tri_connection", lambda: conn)
    rows = service._known_24h_starts()

    value, _, issue = external_start_bonus(
        rows, race="Суточная велогонка", name_key=plain_key(**NAME), birthdate=DOB,
        reported=0, through_year=2028,
    )
    assert value is None
    assert "в составе эстафеты за 2025, 2026" in issue
    assert "2027" not in issue


def test_chance_draft_writes_external_values_and_requires_review_for_unverified_starts(monkeypatch):
    entry = dict(NAME, id=3, birthdate=DOB, format="relay", city="Красноярск", gender="M",
                 raw={"222_starts": "1", "24h_starts": "2", "tattoo": "нет"})
    monkeypatch.setattr(service, "_connect", Mock())
    monkeypatch.setattr(service.edb, "admitted_for_draw", lambda conn, year: [entry])
    monkeypatch.setattr(service.ddb, "load_applicants", lambda conn, year: [])
    monkeypatch.setattr(service.ddb, "load_chance_history", lambda conn, year: {
        2026: {"applicants": [{"id": 9, "person_id": 7, "draw_accumulated": 2, "payment_status": ""}],
               "picks": [], "config": {}, "offered": set()},
    })
    monkeypatch.setattr(service.ddb, "archive_draw_years", lambda conn, year: {})
    monkeypatch.setattr(service.hall_data, "load_entries", lambda conn: [
        service.hall_data.Entry(year=2025, bib="1", stage="bike", format="relay", gender="M", person_id=7,
                                has_time=True, **NAME),
    ])
    monkeypatch.setattr(service.identity, "decisions", lambda conn, entries, include_candidates: {
        3: {"person_id": 7, "state": "new", "candidates": [{"id": 7, "birthdate": DOB}]},
    })
    monkeypatch.setattr(service, "_known_duathlon_starts", lambda: [start(1)])
    monkeypatch.setattr(service, "_known_24h_starts", lambda: [start(2, None)])

    data = service.chance_draft(2028)
    sheet = load_workbook(BytesIO(data)).active
    cells = dict(zip(MAIN_COLUMNS, sheet[2]))

    assert cells[EXTRA_COLS["duathlon_222"]].value == 1
    assert cells[EXTRA_COLS["race_24h"]].value is None
    assert cells[EXTRA_COLS["draw_accumulated"]].value == 3
    assert cells[COL_EXTRA].data_type == cells[COL_TOTAL].data_type == "f"
    assert cells[READY_COLUMN].value == "ПРОВЕРИТЬ"
    assert sheet.max_row == 2
    assert "2025" in cells[EXTRA_COLS["starts_relay"]].comment.text
    assert "Подтверждены старты за 2026" in cells[EXTRA_COLS["duathlon_222"]].comment.text
    assert "возможные старты без даты рождения за 2026" in cells[EXTRA_COLS["race_24h"]].comment.text
    accumulated_note = cells[EXTRA_COLS["draw_accumulated"]].comment.text
    assert "Жеребьёвка 2026" in accumulated_note
    assert "Накоплено до неё — 2" in accumulated_note and "+1" in accumulated_note
    assert "Красноярский край" in cells[EXTRA_COLS["is_local"]].comment.text
    assert "тату Siberman нет" in cells[EXTRA_COLS["tattoo"]].comment.text
    assert cells[COL_EXTRA].comment and cells[COL_TOTAL].comment
    assert parse_applicants(data)[1]
