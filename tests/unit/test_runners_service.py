"""
Unit-тесты для calculate_live_position() в runners_service.py
Тестируют расчёт скорости и дистанции без реальной БД.
"""

import pytest
from datetime import date, timedelta, datetime
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.tracker.services.runners_service import calculate_live_position

# Фиксированная дата гонки
RACE_DATE = date(2026, 3, 29)
CP_DISTS = [0.0, 2.5, 5.0]  # старт, КТ1 на 2.5 км, финиш

# Средние скорости по категориям (мок прошлого года)
CAT_SPEEDS = {'М40': 10.0, 'М30': 12.0, 'Ж40': 9.0}
EMPTY_SPEEDS: dict = {}


def _make_result(**kwargs):
    """Базовая строка result с перезаписью полей."""
    base = {
        'client_id': 1,
        'category': 'М40',
        'time_clear_start': timedelta(hours=20, minutes=0, seconds=0),
        'time_clear_kt1': None,
        'time_clear_kt2': None,
        'time_clear_kt3': None,
        'time_clear_kt4': None,
        'time_clear_kt5': None,
        'time_clear_finish': None,
        'finish_pace_avg': None,
        'finish_pace_avg_clean': None,
    }
    base.update(kwargs)
    return base


class TestFinishedRunner:
    def test_finished_speed_is_zero(self):
        result = _make_result(
            time_clear_kt1=timedelta(hours=20, minutes=15),
            time_clear_finish=timedelta(hours=20, minutes=31),
            finish_pace_avg='6:12',
        )
        speed, dist, pace = calculate_live_position(result, CP_DISTS, RACE_DATE, CAT_SPEEDS)
        assert speed == pytest.approx(0.0)

    def test_finished_distance_is_total(self):
        result = _make_result(time_clear_finish=timedelta(hours=20, minutes=31))
        speed, dist, pace = calculate_live_position(result, CP_DISTS, RACE_DATE, CAT_SPEEDS)
        assert dist == pytest.approx(CP_DISTS[-1])

    def test_finished_returns_three_tuple(self):
        result = _make_result(time_clear_finish=timedelta(hours=20, minutes=31))
        result_ = calculate_live_position(result, CP_DISTS, RACE_DATE, CAT_SPEEDS)
        assert len(result_) == 3


class TestBeforeFirstKT:
    """Участник ещё не прошёл ни одну КТ."""

    def test_speed_from_category_speeds(self):
        """Скорость берётся из category_speeds (среднее по категории прошлого года)."""
        result = _make_result(category='М40')
        # Через 10 минут после старта с 10 км/ч = 1.667 км
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=10)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed, dist, pace = calculate_live_position(result, CP_DISTS, RACE_DATE, CAT_SPEEDS)

        assert speed == pytest.approx(10.0, rel=0.05)
        assert dist == pytest.approx(10.0 * 10 / 60, rel=0.05)  # 10 km/h * 10/60 h

    def test_distance_capped_at_total(self):
        """До первой КТ маркер движется непрерывно без кэпа у КТ1 (фикс осцилляции).
        Дистанция ограничена только финишем (total_distance)."""
        result = _make_result(category='М40')
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=22, minutes=0)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed, dist, pace = calculate_live_position(result, CP_DISTS, RACE_DATE, CAT_SPEEDS)

        assert dist == pytest.approx(CP_DISTS[-1])  # ограничен финишем (5.0 км), не КТ1

    def test_no_start_time_returns_default(self):
        """Нет времени старта → дефолтная скорость, дистанция 0."""
        result = _make_result(time_clear_start=None)
        speed, dist, pace = calculate_live_position(result, CP_DISTS, RACE_DATE, CAT_SPEEDS)
        assert speed == pytest.approx(10.0, rel=0.05)
        assert dist == pytest.approx(0.0)

    def test_unknown_category_uses_default_speed(self):
        """Неизвестная категория → дефолт 10 км/ч."""
        result = _make_result(category='Ж99')
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=6)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed, dist, pace = calculate_live_position(result, CP_DISTS, RACE_DATE, EMPTY_SPEEDS)

        assert speed == pytest.approx(10.0, rel=0.05)

    def test_uses_hist_speed_when_provided(self):
        """hist_speed подставляется вместо category_speeds на первом участке."""
        result = _make_result(category='М40')
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=10)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed, dist, pace = calculate_live_position(
                result, CP_DISTS, RACE_DATE, CAT_SPEEDS, hist_speed=12.0
            )
        assert speed == pytest.approx(12.0, rel=0.05)
        assert dist == pytest.approx(12.0 * 10 / 60, rel=0.05)

    def test_hist_speed_zero_falls_back_to_category(self):
        """hist_speed=0 → фолбэк на category_speeds."""
        result = _make_result(category='М40')
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=10)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed, dist, pace = calculate_live_position(
                result, CP_DISTS, RACE_DATE, CAT_SPEEDS, hist_speed=0
            )
        assert speed == pytest.approx(10.0, rel=0.05)  # из CAT_SPEEDS['М40']


CP_DISTS_MULTI = [0.0, 3.0, 7.0, 10.0]  # старт, КТ1 на 3 км, КТ2 на 7 км, финиш


class TestAfterKT1:
    """Участник прошёл КТ1, идёт к финишу."""

    def test_speed_calculated_from_kt_time(self):
        """
        Скорость = dist_kt1 / time_kt1.
        КТ1 = 2.5 км за 15 мин → speed = 2.5 / 0.25 = 10.0 км/ч
        """
        result = _make_result(
            time_clear_kt1=timedelta(minutes=15),  # 15 мин нет time_clear_start
            time_clear_start=timedelta(hours=20),
        )
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=16)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed, dist, pace = calculate_live_position(result, CP_DISTS, RACE_DATE, CAT_SPEEDS)

        # speed = 2.5 km / 0.25 h = 10.0 km/h
        assert speed == pytest.approx(10.0, rel=0.05)
        # dist = 2.5 + 10 * (1/60) ≈ 2.667
        assert dist == pytest.approx(2.5 + 10.0 / 60, rel=0.05)

    def test_faster_runner_higher_speed(self):
        """Быстрый участник (КТ1 за 12 мин) имеет скорость > медленного (за 18 мин)."""
        base_start = timedelta(hours=20)
        result_fast = _make_result(time_clear_start=base_start, time_clear_kt1=timedelta(minutes=12))
        result_slow = _make_result(time_clear_start=base_start, time_clear_kt1=timedelta(minutes=18))

        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=25)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed_fast, _, _ = calculate_live_position(result_fast, CP_DISTS, RACE_DATE, CAT_SPEEDS)
            speed_slow, _, _ = calculate_live_position(result_slow, CP_DISTS, RACE_DATE, CAT_SPEEDS)

        # КТ1 за 12 мин → 2.5/0.2=12.5 км/ч; за 18 мин → 2.5/0.3≈8.33 км/ч
        assert speed_fast == pytest.approx(12.5, rel=0.05)
        assert speed_slow == pytest.approx(8.33, rel=0.05)
        assert speed_fast > speed_slow

    def test_distance_capped_at_finish(self):
        """Дистанция не превышает финиш (5 км)."""
        result = _make_result(
            time_clear_start=timedelta(hours=20),
            time_clear_kt1=timedelta(minutes=15),
        )
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=22)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            _, dist, _ = calculate_live_position(result, CP_DISTS, RACE_DATE, CAT_SPEEDS)

        assert dist == pytest.approx(CP_DISTS[-1])

    def test_pace_str_format(self):
        """Темп возвращается в формате 'мм:сс'."""
        result = _make_result(
            time_clear_start=timedelta(hours=20),
            time_clear_kt1=timedelta(minutes=15),  # 2.5 km / 0.25h = 10 km/h → 6:00
        )
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=20)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            _, _, pace = calculate_live_position(result, CP_DISTS, RACE_DATE, CAT_SPEEDS)

        assert ':' in pace, f"Темп '{pace}' должен содержать ':'"


class TestAfterKT2:
    """Участник прошёл КТ1 и КТ2 в забеге с несколькими КТ."""

    def test_speed_uses_kt2_dist_and_time(self):
        """После КТ2 скорость = dist_kt2 / time_kt2 (средний темп от старта до КТ2).
        КТ2 = 7.0 км за 42 мин → speed = 7.0 / 0.7 = 10.0 км/ч
        """
        result = _make_result(
            time_clear_start=timedelta(hours=20),
            time_clear_kt1=timedelta(minutes=18),  # КТ1 на 3 км за 18 мин
            time_clear_kt2=timedelta(minutes=42),  # КТ2 на 7 км за 42 мин
        )
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=43)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed, dist, _ = calculate_live_position(result, CP_DISTS_MULTI, RACE_DATE, CAT_SPEEDS)

        # speed = 7.0 / (42/60) = 10.0 км/ч
        assert speed == pytest.approx(10.0, rel=0.05)
        # dist = 7.0 + 10.0 * (1/60) ≈ 7.167
        assert dist == pytest.approx(7.0 + 10.0 / 60, rel=0.05)

    def test_kt1_ignored_when_kt2_present(self):
        """Если KT2 пройдена, скорость считается по интервалу KT1→KT2, а не кумулятивно от старта."""
        # KT1 за 30 мин (медленный), KT2 за 42 мин суммарно
        result_kt1_slow = _make_result(
            time_clear_start=timedelta(hours=20),
            time_clear_kt1=timedelta(minutes=30),  # 3.0/0.5 = 6.0 км/ч кумулятив
            time_clear_kt2=timedelta(minutes=42),  # интервал: 4 км за 12 мин = 20.0 км/ч
        )
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=43)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed, _, _ = calculate_live_position(result_kt1_slow, CP_DISTS_MULTI, RACE_DATE, CAT_SPEEDS)

        # Интервальная скорость KT1→KT2: 4.0 км / (12/60 ч) = 20.0 км/ч
        # (не KT1-кумулятив 6.0, не KT2-кумулятив 10.0)
        assert speed == pytest.approx(20.0, rel=0.05)

    def test_distance_capped_at_finish_after_kt2(self):
        """Дистанция не превышает финиш даже после KT2."""
        result = _make_result(
            time_clear_start=timedelta(hours=20),
            time_clear_kt1=timedelta(minutes=18),
            time_clear_kt2=timedelta(minutes=42),
        )
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=23)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            _, dist, _ = calculate_live_position(result, CP_DISTS_MULTI, RACE_DATE, CAT_SPEEDS)

        assert dist == pytest.approx(CP_DISTS_MULTI[-1])

    def test_kt2_not_used_if_not_in_checkpoint_distances(self):
        """Если checkpoint_distances не включает KT2 (len=2), KT2 игнорируется."""
        result = _make_result(
            time_clear_start=timedelta(hours=20),
            time_clear_kt1=timedelta(minutes=15),   # на трассе с 1 КТ
            time_clear_kt2=timedelta(minutes=999),  # посторонние данные
        )
        cp_dists_no_kt2 = [0.0, 5.0]  # нет KT2 в конфиге
        fixed_now = datetime.combine(RACE_DATE, datetime.min.time()) + timedelta(hours=20, minutes=16)
        with patch('src.tracker.services.runners_service.datetime') as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            speed, _, _ = calculate_live_position(result, cp_dists_no_kt2, RACE_DATE, CAT_SPEEDS)

        # KT1: dist=5.0 (финиш), time=15мин → speed=5.0/0.25=20 км/ч
        # KT2 не должен участвовать (cp_idx=2 >= len=2)
        assert speed == pytest.approx(20.0, rel=0.05)
