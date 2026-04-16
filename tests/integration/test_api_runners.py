"""
Интеграционные тесты для /api/runners (реальная БД krasmarafon).
Требуют доступ к MySQL на 79.174.89.159:16171.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestRunnersEndpoint:
    def test_response_200(self, client):
        response = client.get("/api/runners")
        assert response.status_code == 200

    def test_response_is_json(self, client):
        response = client.get("/api/runners")
        data = response.json()
        assert isinstance(data, dict)

    def test_response_has_required_fields(self, client):
        data = client.get("/api/runners").json()
        for field in ("event", "total", "running", "finished", "not_started", "runners", "last_update"):
            assert field in data, f"Поле '{field}' отсутствует в ответе"

    def test_runners_list_is_list(self, client):
        data = client.get("/api/runners").json()
        assert isinstance(data["runners"], list)

    def test_each_runner_has_speed_field(self, client):
        data = client.get("/api/runners").json()
        runners = data["runners"]
        if not runners:
            pytest.skip("Нет участников в БД для текущего события")
        for r in runners:
            assert "speed" in r, f"Нет поля speed у {r.get('full_name', r.get('id'))}"

    def test_each_runner_has_position_field(self, client):
        data = client.get("/api/runners").json()
        runners = data["runners"]
        if not runners:
            pytest.skip("Нет участников в БД для текущего события")
        for r in runners:
            assert "position" in r
            assert "lat" in r["position"]
            assert "lng" in r["position"]

    def test_each_runner_has_current_distance(self, client):
        data = client.get("/api/runners").json()
        runners = data["runners"]
        if not runners:
            pytest.skip("Нет участников в БД для текущего события")
        for r in runners:
            assert "current_distance" in r
            assert r["current_distance"] >= 0.0

    def test_runner_distance_within_route_bounds(self, client):
        """Дистанция у каждого участника в пределах [0, total_race_km]."""
        from src.config import settings
        total_km = settings.TOTAL_RACE_KM

        data = client.get("/api/runners").json()
        runners = data["runners"]
        if not runners:
            pytest.skip("Нет участников в БД для текущего события")

        for r in runners:
            dist = r["current_distance"]
            assert 0.0 <= dist <= total_km + 0.1, (
                f"Дистанция {dist} вне диапазона [0, {total_km}] "
                f"для {r.get('full_name', r.get('id'))}"
            )

    def test_different_runners_have_different_speeds(self, client):
        """Ключевой тест: скорости участников должны различаться."""
        data = client.get("/api/runners").json()
        runners = [r for r in data["runners"] if r.get("status") == "running"]
        if len(runners) < 2:
            pytest.skip("Недостаточно бегущих участников для сравнения скоростей")

        speeds = [r["speed"] for r in runners]
        unique_speeds = set(round(s, 2) for s in speeds)
        assert len(unique_speeds) > 1, (
            f"Все {len(runners)} участников имеют одинаковую скорость: {speeds[0]:.2f} км/ч. "
            "Ожидались разные скорости."
        )

    def test_finished_runners_have_zero_speed(self, client):
        """Финишировавшие участники должны иметь speed = 0."""
        data = client.get("/api/runners").json()
        finished = [r for r in data["runners"] if r.get("status") == "finished"]
        if not finished:
            pytest.skip("Нет финишировавших участников")
        for r in finished:
            assert r["speed"] == pytest.approx(0.0), (
                f"Финишировавший {r.get('full_name')} имеет speed={r['speed']}"
            )

    def test_query_param_event(self, client):
        """Параметр ?event=night_run работает без ошибок."""
        response = client.get("/api/runners?event=night_run")
        assert response.status_code in (200, 404)  # 404 если события нет в БД
