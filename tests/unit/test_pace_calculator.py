"""
Unit-тесты для src/tracker/services/pace_calculator.py
Тестируют конвертацию темпа без обращения к БД.
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.tracker.services.pace_calculator import (
    parse_pace_to_kmh,
    kmh_to_pace,
    parse_distance,
    get_initial_pace,
)


class TestParsePaceToKmh:
    """Тесты конвертации строки темпа в км/ч."""

    def test_valid_pace_5_00(self):
        """5:00/км = 12.0 км/ч."""
        assert parse_pace_to_kmh("5:00") == pytest.approx(12.0, rel=0.01)

    def test_valid_pace_6_00(self):
        """6:00/км = 10.0 км/ч."""
        assert parse_pace_to_kmh("6:00") == pytest.approx(10.0, rel=0.01)

    def test_valid_pace_7_30(self):
        """7:30/км = 8.0 км/ч."""
        assert parse_pace_to_kmh("7:30") == pytest.approx(8.0, rel=0.01)

    def test_none_input_returns_default(self):
        """None → дефолтная скорость 10.0 км/ч."""
        assert parse_pace_to_kmh(None) == pytest.approx(10.0, rel=0.01)

    def test_empty_string_returns_default(self):
        """Пустая строка → дефолтная скорость."""
        assert parse_pace_to_kmh("") == pytest.approx(10.0, rel=0.01)

    def test_invalid_string_returns_default(self):
        """'N/A' → дефолтная скорость."""
        assert parse_pace_to_kmh("N/A") == pytest.approx(10.0, rel=0.01)

    def test_zero_pace_returns_default(self):
        """0:00 → дефолтная скорость (деление на ноль защищено)."""
        result = parse_pace_to_kmh("0:00")
        assert result == pytest.approx(10.0, rel=0.01)


class TestKmhToPace:
    """Тесты обратной конвертации км/ч → темп."""

    def test_12_kmh_to_5_00(self):
        """12 км/ч → '5:00'."""
        assert kmh_to_pace(12.0) == "5:00"

    def test_10_kmh_to_6_00(self):
        """10 км/ч → '6:00'."""
        assert kmh_to_pace(10.0) == "6:00"

    def test_zero_speed(self):
        """0 км/ч → '0:00' (без ошибки)."""
        result = kmh_to_pace(0.0)
        assert result == "0:00"


class TestParseDistance:
    """Тесты парсинга строки дистанции."""

    def test_km_suffix(self):
        assert parse_distance("5 км") == pytest.approx(5.0)

    def test_numeric_only(self):
        assert parse_distance("10") == pytest.approx(10.0)

    def test_decimal(self):
        assert parse_distance("2.5") == pytest.approx(2.5)

    def test_empty(self):
        assert parse_distance("") == pytest.approx(0.0)

    def test_none(self):
        assert parse_distance(None) == pytest.approx(0.0)


class TestGetInitialPace:
    """Тесты определения начального темпа через БД (с mock)."""

    def test_returns_historical_pace_when_available(self):
        """Если у участника есть результат прошлого года → берём его темп."""
        mock_results = [
            {
                'client_id': 1,
                'race_status': 'finished',  # pace_calculator проверяет lowercase
                'finish_pace_avg': '5:30',
                'category': 'М40',
            }
        ]
        with patch(
            'src.tracker.services.pace_calculator.get_race_results_by_event_id_and_year',
            return_value=mock_results,
        ):
            pace = get_initial_pace(
                client_id=1,
                category='М40',
                event_name='Ночной забег',
                current_year=2026,
            )
        # Результат должен быть близок к 5:30 (темп из истории)
        speed = parse_pace_to_kmh(pace)
        assert speed == pytest.approx(parse_pace_to_kmh('5:30'), rel=0.05)

    def test_returns_category_pace_when_no_personal_history(self):
        """Если личной истории нет, но есть данные по категории → категорийный темп."""
        mock_results = [
            {
                'client_id': 999,  # другой участник
                'race_status': 'Finished',
                'finish_pace_avg': '6:00',
                'category': 'М40',
            }
        ]
        with patch(
            'src.tracker.services.pace_calculator.get_race_results_by_event_id_and_year',
            return_value=mock_results,
        ):
            pace = get_initial_pace(
                client_id=1,
                category='М40',
                event_name='Ночной забег',
                current_year=2026,
            )
        speed = parse_pace_to_kmh(pace)
        assert speed == pytest.approx(parse_pace_to_kmh('6:00'), rel=0.05)

    def test_returns_default_when_no_history(self):
        """Если нет истории вообще → дефолтный темп (6:00)."""
        with patch(
            'src.tracker.services.pace_calculator.get_race_results_by_event_id_and_year',
            return_value=[],
        ):
            pace = get_initial_pace(
                client_id=1,
                category='М40',
                event_name='Ночной забег',
                current_year=2026,
            )
        assert pace == '6:00'

    def test_handles_db_exception_gracefully(self):
        """Исключение БД → дефолтный темп, без падения."""
        with patch(
            'src.tracker.services.pace_calculator.get_race_results_by_event_id_and_year',
            side_effect=Exception("DB error"),
        ):
            pace = get_initial_pace(
                client_id=1,
                category='М40',
                event_name='Ночной забег',
                current_year=2026,
            )
        assert pace == '6:00'
