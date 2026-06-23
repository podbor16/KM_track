from src.triatleta.service import calculate_gap


def test_gap_leader_returns_dash():
    assert calculate_gap(10, 3600000, 10, 3600000) == "—"


def test_gap_same_laps_returns_time():
    assert calculate_gap(10, 3660000, 10, 3600000) == "+00:01:00"


def test_gap_fewer_laps_returns_one_lap():
    assert calculate_gap(9, 0, 10, 0) == "−1 круг"


def test_gap_two_laps_behind():
    assert calculate_gap(8, 0, 10, 0) == "−2 круга"


def test_gap_five_laps_behind():
    assert calculate_gap(5, 0, 10, 0) == "−5 кругов"
