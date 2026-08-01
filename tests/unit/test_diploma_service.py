"""Тесты сервиса данных диплома — БД замокана, без реального соединения."""
import pytest
from datetime import timedelta
from unittest.mock import patch
from src.krasmarafon.services.diploma_service import get_diploma_data, format_finish_time


def _row(bib, sex, status='Finished', time_s=None, rank_abs=1, rank_sex=1, rank_cat=1, category='Ж45'):
    return {
        'start_number': bib,
        'surname': 'Аристархова',
        'name': 'Наталья',
        'sex': sex,
        'race_status': status,
        'time_clear_finish': timedelta(seconds=time_s) if time_s is not None else None,
        'rank_absolute_clean': rank_abs,
        'rank_sex_clean': rank_sex,
        'rank_category_clean': rank_cat,
        'category': category,
    }


def test_format_finish_time_under_hour():
    assert format_finish_time(timedelta(minutes=26, seconds=16)) == '26:16'


def test_format_finish_time_over_hour():
    assert format_finish_time(timedelta(hours=1, minutes=32, seconds=10)) == '1:32:10'


def test_format_finish_time_none_returns_dash():
    assert format_finish_time(None) == '-'


def test_get_diploma_data_finds_participant_by_bib():
    rows = [_row('101', 'female', time_s=1576), _row('102', 'female', time_s=1620)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data is not None
    assert data['surname'] == 'Аристархова'
    assert data['time_display'] == '26:16'


def test_get_diploma_data_returns_none_for_missing_bib():
    rows = [_row('101', 'female', time_s=1576)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='999')
    assert data is None


def test_get_diploma_data_returns_none_if_not_finished():
    rows = [_row('101', 'female', status='DNF', time_s=None)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data is None


def test_get_diploma_data_hides_sex_row_when_single_gender_event():
    rows = [_row('101', 'female', time_s=1576), _row('102', 'female', time_s=1620)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data['show_sex_rank'] is False


def test_get_diploma_data_shows_sex_row_when_mixed_gender_event():
    rows = [_row('101', 'female', time_s=1576), _row('102', 'male', time_s=1500)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data['show_sex_rank'] is True


def test_get_diploma_data_status_check_accepts_typo_variant():
    """'fifnished' — реальное значение в данных (см. athlete-profile.html), должно приниматься как финишировавший."""
    rows = [_row('101', 'female', status='fifnished', time_s=1576)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data is not None


def test_get_diploma_data_handles_finished_with_missing_time():
    """Помечен финишировавшим, но время почему-то не записано — не должно падать."""
    rows = [_row('101', 'female', status='Finished', time_s=None)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data is not None
    assert data['time_display'] == '-'


def test_get_diploma_data_hides_category_row_when_category_is_just_gender():
    """У события без возрастных категорий (напр. 'Достигая цели') значение
    'category' в БД — буквально 'Мужчины'/'Женщины', т.е. то же самое
    разбиение, что и по полу. Показывать оба ряда ("Пол" и "Мужчины") с
    одинаковым местом — дублирование, строку категории нужно скрыть."""
    rows = [
        _row('101', 'male', rank_sex=1, rank_cat=1, category='Мужчины'),
        _row('102', 'male', rank_sex=2, rank_cat=2, category='Мужчины'),
    ]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data['show_category_rank'] is False


def test_get_diploma_data_sex_label_is_gender_name_not_generic():
    """Вместо нейтрального 'Пол' строка должна называться 'Мужчины'/
    'Женщины' — конкретный пол участника."""
    rows = [_row('101', 'female', time_s=1576), _row('102', 'male', time_s=1500)]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data_f = get_diploma_data(event_id=1, bib='101')
        data_m = get_diploma_data(event_id=1, bib='102')
    assert data_f['sex_label'] == 'Женщины'
    assert data_m['sex_label'] == 'Мужчины'


def test_get_diploma_data_shows_category_row_when_real_age_category():
    """У события с настоящими возрастными категориями (напр. 'мужчины до
    49 лет') строка категории несёт данные, которых нет в строке "Пол" —
    показывать нужно."""
    rows = [
        _row('101', 'male', rank_sex=1, rank_cat=1, category='мужчины до 49 лет'),
        _row('102', 'male', rank_sex=2, rank_cat=1, category='мужчины 50+'),
    ]
    with patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=rows):
        data = get_diploma_data(event_id=1, bib='101')
    assert data['show_category_rank'] is True
