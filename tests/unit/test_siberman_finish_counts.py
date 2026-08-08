from src.siberman.finish_counts import get_finish_count


def test_known_participant_baseline_only_when_no_db_years():
    assert get_finish_count("Жуков", "Александр", 2026, {}) == 4


def test_case_and_whitespace_insensitive():
    assert get_finish_count("ЖУКОВ", " Александр ", 2026, {}) == 4


def test_first_timer_stored_as_zero():
    assert get_finish_count("Дупляков", "Иван", 2026, {}) == 0


def test_unknown_participant_defaults_to_zero():
    assert get_finish_count("Неизвестный", "Участник", 2026, {}) == 0


def test_latin_name_lookup():
    assert get_finish_count("Wijnand", "Herinckx", 2026, {}) == 2


def test_db_year_before_race_year_adds_to_baseline():
    """Регрессия 2026-08-08: тот же участник финишировал и в 2025 (уже
    в БД) — при просмотре 2026 года это должно добавиться к базовому
    (до-БД) числу."""
    finished = {"русскин дмитрий": {2025}}
    assert get_finish_count("Русскин", "Дмитрий", 2026, finished) == 5 + 1


def test_db_year_equal_to_race_year_not_counted():
    """При просмотре АРХИВА 2025 года сам 2025 ещё не должен считаться
    прошлым финишем — та же гонка, а не финиш ДО неё (та самая жалоба
    пользователя: 2025-архив показывал то же число, что и 2026)."""
    finished = {"русскин дмитрий": {2025}}
    assert get_finish_count("Русскин", "Дмитрий", 2025, finished) == 5


def test_db_year_after_race_year_not_counted():
    finished = {"русскин дмитрий": {2025, 2027}}
    assert get_finish_count("Русскин", "Дмитрий", 2026, finished) == 5 + 1


def test_no_baseline_entry_still_counts_db_years():
    finished = {"новый спортсмен": {2025}}
    assert get_finish_count("Новый", "Спортсмен", 2026, finished) == 0 + 1
