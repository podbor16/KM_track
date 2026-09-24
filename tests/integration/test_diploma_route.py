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


def _fake_xtrail_event():
    box = DiplomaBoxConfig(top=46.43, left=9.44, width=81.3, height=15.92)
    return EventConfig(
        code="xtrailrun", name="Х Трейл", display_name="Забег Икс", year=2026,
        distances=[
            DistanceConfig(
                distance="2 км", distance_km=2.0, db_event_id=118,
                diploma=DiplomaConfig(
                    background="static/images/diplomas/xtrail/2km/background.jpg",
                    width_px=1080, height_px=1960, name_box=box, participant_only=True,
                ),
            ),
        ],
    )


class TestParticipantDiplomaRoute:
    """/diploma/lead/{lead_id} — диплом по заявке для дистанций без результатов."""

    def test_200_shows_name_without_time_and_ranks(self, client):
        lead = {'surname': 'Иванова', 'name': 'Анна', 'event_id': 118}
        with patch('src.config.settings.EVENTS', {'xtrailrun': _fake_xtrail_event()}), \
             patch('src.krasmarafon.routers.pages.get_participant_diploma_data', return_value=lead):
            r = client.get("/diploma/lead/42")
        assert r.status_code == 200
        assert 'ИВАНОВА' in r.text and 'АННА' in r.text
        assert 'Абсолют' not in r.text and 'diploma-time' not in r.text.split('<body>')[1]

    def test_404_for_unknown_lead(self, client):
        with patch('src.config.settings.EVENTS', {'xtrailrun': _fake_xtrail_event()}), \
             patch('src.krasmarafon.routers.pages.get_participant_diploma_data', return_value=None):
            r = client.get("/diploma/lead/42")
        assert r.status_code == 404

    def test_404_for_lead_of_result_diploma_distance(self, client):
        """Заявка на дистанцию с дипломом по результату (women7) — по заявке
        диплом не отдаём, только по результату."""
        lead = {'surname': 'Аристархова', 'name': 'Наталья', 'event_id': 555}
        with patch('src.config.settings.EVENTS', {'women7': _fake_event()}), \
             patch('src.krasmarafon.routers.pages.get_participant_diploma_data', return_value=lead):
            r = client.get("/diploma/lead/42")
        assert r.status_code == 404

    def test_result_route_404_for_participant_only_distance(self, client):
        with patch('src.config.settings.EVENTS', {'xtrailrun': _fake_xtrail_event()}):
            r = client.get("/diploma/118/101")
        assert r.status_code == 404
