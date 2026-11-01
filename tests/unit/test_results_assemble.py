from datetime import datetime, timedelta, timezone

from src.krasmarafon.services.results_service import assemble_event_results

GUN_UTC = "2026-08-23T02:00:00Z"   # 09:00 Красноярск


def _ev_info():
    return {'event_name': 'Жара', 'event_distance': 21.1, 'event_year': 2026,
            'event_date': datetime(2026, 8, 23).date(), 'gun_time_utc': GUN_UTC,
            'checkpoint_distances': [0, 5.0, 21.1]}


def _gun_local_naive():
    return datetime(2026, 8, 23, 2, 0, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def test_assemble_is_pure_and_uses_now():
    rows = [{'id': 1, 'surname': 'Тестов', 'name': 'Тест', 'sex': 'Мужчина', 'category': 'М18-29',
             'birthday': None, 'race_status': 'Running', 'time_gun_start': timedelta(0)}]
    hist = {'personal': {'ТЕСТОВ|ТЕСТ|': 10.0}, 'category_avg': {}, 'prev_year': 2025}
    now = _gun_local_naive() + timedelta(hours=1)
    res = assemble_event_results(rows, _ev_info(), {}, {}, hist, event_id=116, now=now)
    r = res.results[0]
    assert r['speed'] == 10.0
    assert r['current_distance'] == 10.0
    assert r['pace_source'] == 'personal'
    assert res.server_time_unix == int(now.timestamp() * 1000)
    assert res.race_gun_unix_ms == int(datetime(2026, 8, 23, 2, tzinfo=timezone.utc).timestamp() * 1000)
    assert res.total_distance_km == 21.1


def test_assemble_last_kt_unix_ms():
    rows = [{'id': 2, 'surname': 'А', 'name': 'Б', 'sex': 'Женщина', 'category': '',
             'race_status': 'Running', 'time_gun_start': timedelta(0),
             'time_clear_kt1': timedelta(minutes=25)}]
    res = assemble_event_results(rows, _ev_info(), {}, {},
                                 {'personal': {}, 'category_avg': {}, 'prev_year': 2025},
                                 event_id=116, now=_gun_local_naive() + timedelta(minutes=30))
    gun_ms = res.race_gun_unix_ms
    assert res.results[0]['last_kt_unix_ms'] == gun_ms + 25 * 60 * 1000
    assert res.results[0]['current_distance'] == 5.0
