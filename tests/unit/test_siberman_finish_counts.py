from src.siberman.finish_counts import get_prior_finish_count


def test_known_participant_returns_stored_count():
    assert get_prior_finish_count("Жуков", "Александр") == 4


def test_case_and_whitespace_insensitive():
    assert get_prior_finish_count("ЖУКОВ", " Александр ") == 4


def test_first_timer_stored_as_zero():
    assert get_prior_finish_count("Дупляков", "Иван") == 0


def test_unknown_participant_defaults_to_zero():
    assert get_prior_finish_count("Неизвестный", "Участник") == 0


def test_latin_name_lookup():
    assert get_prior_finish_count("Wijnand", "Herinckx") == 3
