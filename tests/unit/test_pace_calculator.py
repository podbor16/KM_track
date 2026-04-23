"""
Unit-тесты для src/tracker/services/pace_calculator.py
Тестируют конвертацию темпа без обращения к БД.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.tracker.services.pace_calculator import (
    parse_pace_to_kmh,
    parse_distance,
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
