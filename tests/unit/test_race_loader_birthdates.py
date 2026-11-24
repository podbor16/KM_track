from datetime import date
import sqlite3

import pytest

import load_duathlon_results
import load_tri_results


class Cursor:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.create_function("LOWER", 1, str.lower)
        self.cursor = self.db.execute("""
            CREATE TABLE participants (
                id INTEGER PRIMARY KEY, event_id INT, start_number INT, surname TEXT,
                name TEXT, gender TEXT, status TEXT, category TEXT, team_name TEXT, birthdate DATE
            )
        """)

    def execute(self, sql, args):
        self.cursor.execute(sql.replace("%s", "?"), args)

    def fetchone(self):
        return self.cursor.fetchone()

    @property
    def lastrowid(self):
        return self.cursor.lastrowid


@pytest.mark.parametrize("loader", [load_duathlon_results, load_tri_results])
def test_loader_fills_only_missing_birthdate_for_same_participant(loader):
    cursor = Cursor()
    load = loader._get_or_create_participant
    runner = {"dorsal": 1, "surname": "Example", "name": "Runner", "gender": "male"}
    pid = load(cursor, 1, runner, {})

    load(cursor, 1, {**runner, "surname": "Replacement", "dob": "1990-02-10"}, {"birthdate": "dob"})
    load(cursor, 1, {**runner, "dob": "1990-02-31"}, {"birthdate": "dob"})
    cursor.execute("SELECT birthdate FROM participants WHERE id=%s", (pid,))
    assert cursor.fetchone() == (None,)

    load(cursor, 1, {**runner, "dob": "10.02.1990"}, {"birthdate": "dob"})
    load(cursor, 1, {**runner, "dob": "1991-02-10", "status": "finished"}, {"birthdate": "dob"})
    load(cursor, 1, {**runner, "dob": None, "status": "finished"}, {"birthdate": "dob"})
    cursor.execute("SELECT birthdate, status FROM participants WHERE id=%s", (pid,))
    assert cursor.fetchone() == (date(1990, 2, 10).isoformat(), "finished")

    new_pid = load(cursor, 1, {**runner, "dorsal": 2, "birthdate": "1992-02-29T00:00:00Z"}, {})
    cursor.execute("SELECT birthdate FROM participants WHERE id=%s", (new_pid,))
    assert cursor.fetchone() == ("1992-02-29",)


def test_cycling_loader_keeps_birthdate_empty_for_a_team():
    cursor = Cursor()
    load = load_tri_results._get_or_create_participant
    runner = {"dorsal": 1, "surname": "Example", "name": "Team", "birthdate": "1990-02-10"}
    pid = load(cursor, 1, {**runner, "category": "Эстафета"}, {})
    load(cursor, 1, {**runner, "status": "finished"}, {})
    cursor.execute("SELECT birthdate, status FROM participants WHERE id=%s", (pid,))
    assert cursor.fetchone() == (None, "finished")
