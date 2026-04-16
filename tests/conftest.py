"""
Общие фикстуры для всех тестов KM_track.
"""

import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import pytest
from starlette.testclient import TestClient

# Добавляем корень проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import app


@pytest.fixture(scope="session")
def client():
    """TestClient с полным lifecycle приложения (lifespan)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_result_before_kt1():
    """Участник, ещё не прошедший КТ1 (только стартовал)."""
    return {
        'client_id': 1,
        'surname': 'Иванов',
        'name': 'Иван',
        'category': 'М40',
        'sex': 'male',
        'start_number': '100',
        'race_status': 'Running',
        'time_clear_start': timedelta(hours=10, minutes=0, seconds=0),
        'time_gun_start': timedelta(hours=10, minutes=0, seconds=0),
        'time_clear_kt1': None,
        'time_clear_kt2': None,
        'time_clear_kt3': None,
        'time_clear_kt4': None,
        'time_clear_kt5': None,
        'time_clear_finish': None,
        'pace_avg_kt1': None,
        'pace_avg_kt2': None,
        'finish_pace_avg': None,
        'finish_pace_avg_clean': None,
    }


@pytest.fixture
def sample_result_after_kt1():
    """Участник, прошедший КТ1 за 12 мин 30 сек (темп 5:00/км)."""
    return {
        'client_id': 2,
        'surname': 'Петров',
        'name': 'Пётр',
        'category': 'М30',
        'sex': 'male',
        'start_number': '200',
        'race_status': 'Running',
        'time_clear_start': timedelta(hours=10, minutes=0, seconds=0),
        'time_gun_start': timedelta(hours=10, minutes=0, seconds=0),
        'time_clear_kt1': timedelta(hours=10, minutes=12, seconds=30),
        'time_clear_kt2': None,
        'time_clear_kt3': None,
        'time_clear_kt4': None,
        'time_clear_kt5': None,
        'time_clear_finish': None,
        'pace_avg_kt1': '5:00',
        'pace_avg_kt2': None,
        'finish_pace_avg': None,
        'finish_pace_avg_clean': None,
    }


@pytest.fixture
def sample_result_finished():
    """Участник, финишировавший."""
    return {
        'client_id': 3,
        'surname': 'Сидоров',
        'name': 'Сидор',
        'category': 'М50',
        'sex': 'male',
        'start_number': '300',
        'race_status': 'Finished',
        'time_clear_start': timedelta(hours=10, minutes=0, seconds=0),
        'time_gun_start': timedelta(hours=10, minutes=0, seconds=0),
        'time_clear_kt1': timedelta(hours=10, minutes=15, seconds=0),
        'time_clear_kt2': None,
        'time_clear_kt3': None,
        'time_clear_kt4': None,
        'time_clear_kt5': None,
        'time_clear_finish': timedelta(hours=10, minutes=31, seconds=0),
        'pace_avg_kt1': '6:00',
        'pace_avg_kt2': None,
        'finish_pace_avg': '6:12',
        'finish_pace_avg_clean': '6:12',
    }


@pytest.fixture
def checkpoint_distances_5km():
    """Дистанции КТ для 5-км забега (старт, КТ1 на 2.5, финиш)."""
    return [0.0, 2.5, 5.0]


@pytest.fixture
def race_date_today():
    """Дата гонки — сегодня (для тестов с текущим временем)."""
    return date.today()
