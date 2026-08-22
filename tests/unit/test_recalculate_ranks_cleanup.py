"""Тест для RaceLoader._recalculate_ranks() — очистка "призрачных" мест.

Живой баг на Жаре 5км 2026-08-22 (event_id=115, id=109329): участник со
статусом "Not started" и всеми NULL-временами имел rank_absolute=1394 —
осталось с более раннего цикла, когда организатор откатил ошибочный
финиш в Copernico обратно на "не стартовал". _recalculate_ranks()
выставляет места ТОЛЬКО для текущего списка финишировавших, но раньше
никогда не сбрасывал место у тех, кто из этого списка выпал."""
from datetime import timedelta
from unittest.mock import MagicMock

from load_race_results import RaceLoader


def make_loader():
    logger = MagicMock()
    loader = RaceLoader.__new__(RaceLoader)
    loader.event_id = 115
    loader.logger = logger
    loader.cursor = MagicMock()
    loader.connection = MagicMock()
    return loader


def test_recalculate_ranks_clears_stale_rank_for_non_finishers():
    loader = make_loader()

    finished_row = {
        "id": 42, "sex": "Мужчина", "category": "М18-49",
        "time_gun_finish": "0:22:48", "time_clear_finish": "0:22:29",
        "time_gun_finish_ms": None, "time_clear_finish_ms": None,
    }
    # 1-й fetchall — финишировавшие (для основных мест); затем 7 вызовов
    # для kt1..kt7 (по всем пусто — в этом тесте КТ-места не важны).
    loader.cursor.fetchall.side_effect = [[finished_row]] + [[]] * 7

    loader._recalculate_ranks()

    cleanup_calls = [
        c for c in loader.cursor.execute.call_args_list
        if "rank_absolute = NULL" in c.args[0]
    ]
    assert len(cleanup_calls) == 1, "должен быть ровно один запрос очистки призрачных мест"
    cleanup_sql, cleanup_params = cleanup_calls[0].args
    assert "race_status != 'Finished'" in cleanup_sql
    assert "time_gun_finish IS NULL" in cleanup_sql
    assert cleanup_params == (115,)


def test_recalculate_ranks_returns_early_when_nobody_finished():
    """Пустой список финишировавших — выходим сразу, даже запрос очистки
    призрачных мест не имеет смысла запускать (событие ещё не началось)."""
    loader = make_loader()
    loader.cursor.fetchall.return_value = []

    loader._recalculate_ranks()

    loader.connection.commit.assert_not_called()
