"""Интеграционные тесты роута /diploma/{event_id}/{bib} — БД замокана."""
from datetime import timedelta
from unittest.mock import patch

from src.config.event_loader import EventConfig, DistanceConfig, DiplomaConfig, DiplomaBoxConfig


def _fake_event():
    return EventConfig(
        code="women7",
        name="Женская семерка",
        display_name="Женская семёрка",
        year=2026,
        distances=[
            DistanceConfig(
                distance="7 км", distance_km=7.0, db_event_id=555, tracked=True,
                diploma=DiplomaConfig(
                    background="static/images/diplomas/women7/7km/background.png",
                    width_px=1080, height_px=1920,
                    name_box=DiplomaBoxConfig(top=24.8, left=8.8, width=81.6, height=17.9),
                    ranks_box=DiplomaBoxConfig(top=45.8, left=8.8, width=81.6, height=16.3),
                ),
            ),
        ],
    )


def _fake_rows():
    return [{
        'start_number': '101', 'surname': 'Аристархова', 'name': 'Наталья',
        'sex': 'female', 'race_status': 'Finished', 'category': 'Ж45',
        'time_clear_finish': timedelta(minutes=26, seconds=16),
        'rank_absolute_clean': 1, 'rank_sex_clean': 1, 'rank_category_clean': 1,
        'rank_absolute': 1, 'rank_sex': 1, 'rank_category': 1,
    }]


class TestDiplomaRoute:
    def test_diploma_200_for_configured_event_and_existing_bib(self, client):
        with patch('src.config.settings.EVENTS', {'women7': _fake_event()}), \
             patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=_fake_rows()):
            r = client.get("/diploma/555/101")
        assert r.status_code == 200
        assert 'Аристархова' in r.text
        assert '26:16' in r.text

    def test_diploma_404_for_unknown_event_id(self, client):
        with patch('src.config.settings.EVENTS', {'women7': _fake_event()}):
            r = client.get("/diploma/999999/101")
        assert r.status_code == 404

    def test_diploma_404_for_unknown_bib(self, client):
        with patch('src.config.settings.EVENTS', {'women7': _fake_event()}), \
             patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=_fake_rows()):
            r = client.get("/diploma/555/999")
        assert r.status_code == 404

    def test_diploma_hides_sex_rank_for_single_gender_event(self, client):
        with patch('src.config.settings.EVENTS', {'women7': _fake_event()}), \
             patch('src.krasmarafon.services.diploma_service.get_race_results_by_event_id', return_value=_fake_rows()):
            r = client.get("/diploma/555/101")
        assert 'Ж45' in r.text
