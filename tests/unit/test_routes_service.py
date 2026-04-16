"""
Unit-тесты для src/tracker/services/routes_service.py
Тестируют RouteCalculator без сети и без БД.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.tracker.services.routes_service import RouteCalculator


# Простой маршрут: 5 точек по прямой (широта 56.0..56.004, долгота 92.0)
SIMPLE_COORDS = [
    [56.000, 92.000],
    [56.001, 92.000],
    [56.002, 92.000],
    [56.003, 92.000],
    [56.004, 92.000],
]


@pytest.fixture
def calc():
    rc = RouteCalculator()
    rc.set_path(SIMPLE_COORDS)
    return rc


class TestRouteCalculatorSetup:
    def test_set_path_fills_coords(self, calc):
        assert len(calc.path_coords) == 5

    def test_total_length_positive(self, calc):
        assert calc.total_path_length > 0

    def test_segment_lengths_count(self, calc):
        """Количество сегментов = количество точек - 1."""
        assert len(calc.segment_lengths) == len(SIMPLE_COORDS) - 1


class TestGetPositionOnLoop:
    def test_distance_zero_returns_first_point(self, calc):
        result = calc.get_position_on_loop(0.0)
        assert result is not None
        assert result[0] == pytest.approx(SIMPLE_COORDS[0][0], abs=0.001)

    def test_distance_max_returns_last_point(self, calc):
        result = calc.get_position_on_loop(calc.total_path_length)
        assert result is not None
        assert result[0] == pytest.approx(SIMPLE_COORDS[-1][0], abs=0.001)

    def test_distance_midpoint(self, calc):
        """Середина маршрута → средняя координата."""
        mid = calc.total_path_length / 2
        result = calc.get_position_on_loop(mid)
        assert result is not None
        # Должна быть между первой и последней точкой
        assert SIMPLE_COORDS[0][0] <= result[0] <= SIMPLE_COORDS[-1][0]

    def test_empty_route_returns_none(self):
        rc = RouteCalculator()
        assert rc.get_position_on_loop(1.0) is None

    def test_large_distance_clamped(self, calc):
        """Дистанция больше маршрута → последняя точка (не выходит за пределы)."""
        result = calc.get_position_on_loop(9999.0)
        assert result is not None
        assert result[0] == pytest.approx(SIMPLE_COORDS[-1][0], abs=0.001)


class TestGetShuttlePosition:
    ONE_WAY = 0.002  # половина маршрута (в "градусных" единицах)
    TOTAL = 0.004

    def test_forward_phase_start(self, calc):
        """Дистанция 0 → начало маршрута."""
        result = calc.get_shuttle_position(0.0, self.ONE_WAY, self.TOTAL)
        assert result is not None
        assert result[0] == pytest.approx(SIMPLE_COORDS[0][0], abs=0.001)

    def test_forward_phase_midpoint(self, calc):
        """Половина пути туда → средняя точка."""
        result = calc.get_shuttle_position(self.ONE_WAY / 2, self.ONE_WAY, self.TOTAL)
        assert result is not None

    def test_turnaround_point(self, calc):
        """На дистанции one_way → конец маршрута (разворот)."""
        result = calc.get_shuttle_position(self.ONE_WAY, self.ONE_WAY, self.TOTAL)
        assert result is not None
        assert result[0] == pytest.approx(SIMPLE_COORDS[-1][0], abs=0.001)

    def test_return_phase(self, calc):
        """После разворота → движение обратно (ratio убывает)."""
        result_turn = calc.get_shuttle_position(self.ONE_WAY, self.ONE_WAY, self.TOTAL)
        result_back = calc.get_shuttle_position(self.ONE_WAY * 1.5, self.ONE_WAY, self.TOTAL)
        assert result_turn is not None and result_back is not None
        # На обратном пути широта должна быть меньше, чем на развороте
        assert result_back[0] <= result_turn[0]

    def test_empty_route_returns_none(self):
        rc = RouteCalculator()
        assert rc.get_shuttle_position(1.0, 2.5, 5.0) is None
