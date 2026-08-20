"""Тесты для src/monitoring/collector.py — generate_suggestions() и связанные
методы MetricsCollector (baseline SSE, чтение алертов)."""
import csv
import time
from unittest.mock import patch

import pytest

from src.monitoring.collector import MetricsCollector, generate_suggestions


def _base_point(**overrides):
    base = {
        "ram_used_mb": 500, "ram_total_mb": 2972,
        "avg_response_ms": 100, "total_requests": 100, "http_errors": 0,
        "sse_connections": 5,
    }
    base.update(overrides)
    return base


# --- generate_suggestions() ---------------------------------------------

def test_ram_high_triggers_suggestion():
    point = _base_point(ram_used_mb=2400)  # 80.8% из 2972 MB
    suggestions = generate_suggestions(point, recent_avg_sse=5.0)
    assert len(suggestions) == 1
    assert "RAM" in suggestions[0]
    assert "systemctl restart km_track" in suggestions[0]


def test_response_time_high_triggers_suggestion():
    point = _base_point(avg_response_ms=5000)
    suggestions = generate_suggestions(point, recent_avg_sse=5.0)
    assert len(suggestions) == 1
    assert "Среднее время ответа" in suggestions[0]


def test_error_rate_high_triggers_suggestion():
    point = _base_point(http_errors=10)  # 10% от 100 запросов
    suggestions = generate_suggestions(point, recent_avg_sse=5.0)
    assert len(suggestions) == 1
    assert "Ошибок" in suggestions[0]


def test_sse_anomaly_triggers_suggestion():
    point = _base_point(sse_connections=60)
    suggestions = generate_suggestions(point, recent_avg_sse=10.0)  # 60 > 10*2 и 60 > 20
    assert len(suggestions) == 1
    assert "SSE-подключений" in suggestions[0]


def test_sse_anomaly_requires_absolute_floor_not_just_multiplier():
    """Мультипликатор формально сработал бы (5 > 1*2), но абсолютный порог
    (20 соединений) — нет: не шумим на переходе с 1 до 5 при почти нулевом
    трафике."""
    point = _base_point(sse_connections=5)
    assert generate_suggestions(point, recent_avg_sse=1.0) == []


def test_sse_check_skipped_when_no_baseline():
    point = _base_point(sse_connections=100)
    assert generate_suggestions(point, recent_avg_sse=None) == []


def test_multiple_factors_produce_multiple_suggestions():
    point = _base_point(ram_used_mb=2600, http_errors=20)  # RAM ~87.5%, ошибок 20%
    suggestions = generate_suggestions(point, recent_avg_sse=5.0)
    assert len(suggestions) == 2


def test_nothing_over_threshold_returns_empty_list():
    assert generate_suggestions(_base_point(), recent_avg_sse=5.0) == []


def test_empty_point_does_not_raise():
    """point без ожидаемых ключей — не падает, просто не добавляет советы
    по недостающим показателям (используется .get() с дефолтами)."""
    assert generate_suggestions({}, recent_avg_sse=None) == []


def test_zero_total_requests_does_not_divide_by_zero():
    point = _base_point(total_requests=0, http_errors=0)
    assert generate_suggestions(point, recent_avg_sse=5.0) == []


# --- MetricsCollector._recent_avg_sse() ----------------------------------

@patch.object(MetricsCollector, "query")
def test_recent_avg_sse_averages_query_points(mock_query, tmp_path):
    mock_query.return_value = [
        {"sse_connections": 10}, {"sse_connections": 20}, {"sse_connections": 30},
    ]
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    assert collector._recent_avg_sse() == 20.0


@patch.object(MetricsCollector, "query")
def test_recent_avg_sse_returns_none_when_no_history(mock_query, tmp_path):
    mock_query.return_value = []
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    assert collector._recent_avg_sse() is None


# --- MetricsCollector.get_alerts_path() ----------------------------------

def test_get_alerts_path_matches_db_path_parent(tmp_path):
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    assert collector.get_alerts_path() == tmp_path / "high_load_alerts.csv"
