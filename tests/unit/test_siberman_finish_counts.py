from src.siberman.finish_counts import get_finish_count, person_key


def test_counts_only_years_before_race_year():
    finished = {"русскин дмитрий": {2020, 2021, 2022, 2023, 2024, 2025}}
    assert get_finish_count("Русскин", "Дмитрий", 2026, finished) == 6


def test_race_year_itself_not_counted():
    """При просмотре АРХИВА 2025 года сам 2025 ещё не должен считаться
    прошлым финишем (жалоба пользователя 2026-08-08)."""
    finished = {"русскин дмитрий": {2024, 2025}}
    assert get_finish_count("Русскин", "Дмитрий", 2025, finished) == 1


def test_later_years_not_counted():
    finished = {"русскин дмитрий": {2025, 2027}}
    assert get_finish_count("Русскин", "Дмитрий", 2026, finished) == 1


def test_unknown_participant_is_zero():
    assert get_finish_count("Неизвестный", "Участник", 2026, {}) == 0


def test_person_key_case_whitespace_yo_insensitive():
    assert person_key("ПАНЧЕНКО ", " Алексей") == "панченко алексей"
    assert person_key("Печёнкина", "Екатерина") == person_key("Печенкина", "Екатерина")


def test_person_key_alias_maiden_name():
    # Один человек: 2024 — «Заволокина Олеся», рейтинг — «Князева (Заволокина) Олеся»
    assert person_key("Заволокина", "Олеся") == person_key("Князева", "Олеся")
    assert person_key("Князева (Заволокина)", "Олеся") == person_key("Князева", "Олеся")


def test_alias_counts_years_under_both_surnames():
    finished = {person_key("Заволокина", "Олеся"): {2024}}
    assert get_finish_count("Князева", "Олеся", 2026, finished) == 1
