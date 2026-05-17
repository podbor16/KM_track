"""
Unit-тесты для оптимизации bulk_upsert в load_race_results.py.
Проверяют:
1. _bulk_upsert генерирует один SQL с N rows вместо N запросов
2. conditional ranks — вызов _recalculate_ranks только при updated_r > 0
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from load_race_results import RaceLoader


def make_loader():
    """Создать RaceLoader с замоканными cursor/connection."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.debug = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()

    loader = RaceLoader.__new__(RaceLoader)
    loader.event_id = 106
    loader.logger = logger
    loader.cursor = MagicMock()
    loader.connection = MagicMock()
    loader.existing_results = {}
    loader.inserted_count = 0
    loader.updated_results_count = 0
    loader.updated_segments_count = 0
    loader.update_cycles = 0
    loader._cycle_times = []
    loader._kt_reads_per_cycle = []
    loader._last_stats_log = 0
    loader._kt_fields = None
    loader._preset_cfg = {}
    loader.checkpoint_distances = None
    loader.gun_time_utc = None
    loader.event_distance_km = 5.0
    return loader


class TestBulkUpsert:
    def test_single_row_generates_correct_sql(self):
        loader = make_loader()
        loader._bulk_upsert(
            'results',
            ['id', 'race_status'],
            [(42, 'Finished')],
            ['race_status'],
        )
        call_args = loader.cursor.execute.call_args
        sql, values = call_args[0]
        assert 'INSERT INTO `results`' in sql
        assert 'ON DUPLICATE KEY UPDATE' in sql
        assert '`race_status`=VALUES(`race_status`)' in sql
        assert values == [42, 'Finished']

    def test_multiple_rows_single_execute_call(self):
        loader = make_loader()
        batch = [(1, 'Finished'), (2, 'Running'), (3, 'Finished')]
        loader._bulk_upsert('results', ['id', 'race_status'], batch, ['race_status'])

        # cursor.execute вызван ровно 1 раз — один SQL-запрос
        assert loader.cursor.execute.call_count == 1

        call_args = loader.cursor.execute.call_args
        sql, values = call_args[0]
        # Три rows в VALUES
        assert sql.count('(%s,%s)') == 3
        # Все значения переданы плоским списком
        assert values == [1, 'Finished', 2, 'Running', 3, 'Finished']

    def test_empty_batch_skips_execute(self):
        loader = make_loader()
        loader._bulk_upsert('results', ['id', 'race_status'], [], ['race_status'])
        loader.cursor.execute.assert_not_called()

    def test_returns_batch_length(self):
        loader = make_loader()
        result = loader._bulk_upsert(
            'results', ['id', 'col'], [(1, 'a'), (2, 'b')], ['col']
        )
        assert result == 2

    def test_none_cursor_skips_execute(self):
        loader = make_loader()
        loader.cursor = None
        result = loader._bulk_upsert('results', ['id', 'col'], [(1, 'a')], ['col'])
        assert result == 0

    def test_update_cols_subset_of_insert_cols(self):
        """INSERT включает id, UPDATE не включает id."""
        loader = make_loader()
        loader._bulk_upsert(
            'results',
            ['id', 'surname', 'name'],
            [(10, 'Иванов', 'Иван')],
            ['surname', 'name'],
        )
        sql = loader.cursor.execute.call_args[0][0]
        assert '`id`' in sql
        assert '`id`=VALUES(`id`)' not in sql
        assert '`surname`=VALUES(`surname`)' in sql
        assert '`name`=VALUES(`name`)' in sql

    def test_large_batch_single_query(self):
        """895 строк — всё равно 1 вызов execute."""
        loader = make_loader()
        batch = [(i, f'val{i}') for i in range(895)]
        loader._bulk_upsert('results', ['id', 'col'], batch, ['col'])
        assert loader.cursor.execute.call_count == 1
        sql = loader.cursor.execute.call_args[0][0]
        assert sql.count('(%s,%s)') == 895


class TestConditionalRanks:
    def test_ranks_not_called_when_no_updates(self):
        loader = make_loader()
        loader._recalculate_ranks = MagicMock()
        loader._recalculate_segment_ranks = MagicMock()
        loader.load_race_data = MagicMock(return_value=[{'dorsal': '1'}])
        loader._update_existing = MagicMock(return_value=(0, 0, 0))
        loader._cycle_times = []
        loader._kt_reads_per_cycle = []
        loader._last_stats_log = float('inf')
        loader.update_cycles = 0
        loader.gun_time_utc = None

        import time
        with patch('load_race_results.time') as mock_time:
            mock_time.time.side_effect = [0, 0, 1, 1, 1, 1, 1, 1]
            mock_time.sleep = MagicMock(side_effect=KeyboardInterrupt)
            try:
                loader.continuous_mode([], interval=5, reset_cache_interval=60)
            except (KeyboardInterrupt, StopIteration):
                pass

        loader._recalculate_ranks.assert_not_called()
        loader._recalculate_segment_ranks.assert_not_called()

    def test_ranks_called_when_results_updated(self):
        loader = make_loader()
        loader._recalculate_ranks = MagicMock()
        loader._recalculate_segment_ranks = MagicMock()
        loader.load_race_data = MagicMock(return_value=[{'dorsal': '1'}])
        loader._update_existing = MagicMock(return_value=(5, 0, 0))
        loader._cycle_times = []
        loader._kt_reads_per_cycle = []
        loader._last_stats_log = float('inf')
        loader.update_cycles = 0
        loader.gun_time_utc = None

        import time
        with patch('load_race_results.time') as mock_time:
            mock_time.time.side_effect = [0, 0, 1, 1, 1, 1, 1, 1]
            mock_time.sleep = MagicMock(side_effect=KeyboardInterrupt)
            try:
                loader.continuous_mode([], interval=5, reset_cache_interval=60)
            except (KeyboardInterrupt, StopIteration):
                pass

        loader._recalculate_ranks.assert_called_once()
        loader._recalculate_segment_ranks.assert_not_called()

    def test_segment_ranks_called_when_segments_updated(self):
        loader = make_loader()
        loader._recalculate_ranks = MagicMock()
        loader._recalculate_segment_ranks = MagicMock()
        loader.load_race_data = MagicMock(return_value=[{'dorsal': '1'}])
        loader._update_existing = MagicMock(return_value=(0, 10, 0))
        loader._cycle_times = []
        loader._kt_reads_per_cycle = []
        loader._last_stats_log = float('inf')
        loader.update_cycles = 0
        loader.gun_time_utc = None

        import time
        with patch('load_race_results.time') as mock_time:
            mock_time.time.side_effect = [0, 0, 1, 1, 1, 1, 1, 1]
            mock_time.sleep = MagicMock(side_effect=KeyboardInterrupt)
            try:
                loader.continuous_mode([], interval=5, reset_cache_interval=60)
            except (KeyboardInterrupt, StopIteration):
                pass

        loader._recalculate_ranks.assert_not_called()
        loader._recalculate_segment_ranks.assert_called_once()
