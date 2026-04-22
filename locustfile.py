"""
Нагрузочный тест KM_track — 10 000 одновременных пользователей.

Запуск:
    locust -f locustfile.py --config locust.conf

Или вручную:
    locust -f locustfile.py --host http://localhost:8000 --users 10000 --spawn-rate 200
"""

import random
from locust import HttpUser, task, between

# Event IDs, которые реально есть в БД
EVENT_IDS = [67, 71, 75, 104, 121]


class ResultsUser(HttpUser):
    """50% трафика — просматривают и переключают результаты событий."""
    weight = 5
    wait_time = between(3, 10)

    @task(3)
    def view_results_page(self):
        self.client.get("/results", name="/results")

    @task(5)
    def load_event_results(self):
        eid = random.choice(EVENT_IDS)
        self.client.get(f"/api/event-results?event_id={eid}", name="/api/event-results")

    @task(1)
    def view_start_list_page(self):
        self.client.get("/start_list", name="/start_list")


class TrackerUser(HttpUser):
    """40% трафика — открыли трекер и polling каждые 2–4s."""
    weight = 4
    wait_time = between(2, 4)

    @task(1)
    def view_tracker(self):
        self.client.get("/tracker", name="/tracker")

    @task(6)
    def poll_event_results(self):
        # Трекер всегда смотрит live-событие (event_id=104)
        self.client.get("/api/event-results?event_id=104", name="/api/event-results[poll]")


class SearchUser(HttpUser):
    """10% трафика — ищут конкретного спортсмена."""
    weight = 1
    wait_time = between(5, 15)

    QUERIES = ["Ива", "Пет", "Алек", "Сер", "Мар", "Ан", "Дм", "Ол"]

    @task(3)
    def search_athlete(self):
        q = random.choice(self.QUERIES)
        self.client.get(f"/api/search-athletes?query={q}", name="/api/search-athletes")

    @task(1)
    def view_start_list_api(self):
        self.client.get("/api/registered-runners", name="/api/registered-runners")

    @task(1)
    def health_check(self):
        self.client.get("/health", name="/health")
