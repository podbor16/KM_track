"""
Нагрузочный тест KM_track — до 10 000 одновременных пользователей (HTTP-часть).
SSE-нагрузка — отдельно в tests/load/sse_test.js (k6).

Запуск:
    locust -f locustfile.py --config locust.conf
    # или через оркестратор:
    python tests/load/run_load_test.py
"""

import os
import random
from locust import HttpUser, task, between


class FakeIPUser(HttpUser):
    """Базовый класс: каждый VU получает уникальный X-Forwarded-For.
    Nginx читает этот заголовок для rate limiting → имитируем разные IP.
    """
    abstract = True

    def on_start(self):
        fake_ip = (
            f"{random.randint(1, 223)}."
            f"{random.randint(1, 254)}."
            f"{random.randint(1, 254)}."
            f"{random.randint(1, 254)}"
        )
        self.client.headers.update({"X-Forwarded-For": fake_ip})

# Event IDs, которые реально есть в БД
EVENT_IDS = [67, 71, 75, 104, 106, 121]

# Текущее live-событие (трекер поллит именно этот event_id)
LIVE_EVENT_ID = os.environ.get("LOCUST_LIVE_EVENT_ID", "106")

# Пароль для бизнес-аналитики (из .env или переменной окружения)
ADMIN_PASSWORD = os.environ.get("LOCUST_ADMIN_PASSWORD", "km2026admin")

# Имя пользователя для бизнес-аналитики
ADMIN_USERNAME = os.environ.get("LOCUST_ADMIN_USERNAME", "admin")


class TrackerUser(FakeIPUser):
    """55% трафика — открыли трекер один раз, подключились к SSE.
    HTTP-активность минимальна: загрузка страницы при входе + редкий поиск.
    Основная нагрузка от этих пользователей — SSE-соединение (sse_load_remote.py).
    """
    weight = 55
    wait_time = between(30, 120)  # реалистично: действие раз в 30-120с

    SEARCH_NAMES = ["Ива", "Пет", "Алек", "Сер", "Мар", "Ан", "Дм", "Ол"]

    def on_start(self):
        super().on_start()
        # Одноразовая загрузка при входе
        self.client.get("/tracker", name="/tracker")
        self.client.get(
            f"/api/event-results?event_id={LIVE_EVENT_ID}",
            name="/api/event-results[live]",
        )

    @task(1)
    def occasional_search(self):
        """Редкий поиск конкретного участника."""
        q = random.choice(self.SEARCH_NAMES)
        self.client.get(f"/api/search-athletes?q={q}", name="/api/search-athletes")


class ResultsUser(FakeIPUser):
    """25% трафика — просматривают результаты, иногда переключают события."""
    weight = 25
    wait_time = between(10, 30)  # читают таблицу результатов, не polling

    @task(3)
    def view_results_page(self):
        self.client.get("/results", name="/results")

    @task(2)
    def load_event_results(self):
        eid = random.choice(EVENT_IDS)
        self.client.get(f"/api/event-results?event_id={eid}", name="/api/event-results")

    @task(1)
    def view_analytics(self):
        self.client.get("/race-analysis", name="/race-analysis")


class StartListUser(FakeIPUser):
    """10% трафика — смотрят стартовый список."""
    weight = 10
    wait_time = between(5, 15)

    @task(2)
    def view_start_list_page(self):
        self.client.get("/start_list", name="/start_list")

    @task(3)
    def get_registered_runners_api(self):
        self.client.get(
            f"/api/registered-runners?event_id={LIVE_EVENT_ID}",
            name="/api/registered-runners",
        )

    @task(1)
    def view_history(self):
        self.client.get("/history", name="/history")


class SearchUser(FakeIPUser):
    """5% трафика — ищут конкретного спортсмена."""
    weight = 5
    wait_time = between(5, 15)

    QUERIES = ["Ива", "Пет", "Алек", "Сер", "Мар", "Ан", "Дм", "Ол"]

    @task(3)
    def search_athlete(self):
        q = random.choice(self.QUERIES)
        self.client.get(f"/api/search-athletes?q={q}", name="/api/search-athletes")

    @task(1)
    def health_check(self):
        self.client.get("/health", name="/health")


class BusinessUser(FakeIPUser):
    """5% трафика — организаторы в бизнес-аналитике."""
    weight = 5
    wait_time = between(10, 30)

    def on_start(self):
        super().on_start()  # назначить уникальный X-Forwarded-For
        """Войти один раз при старте VU — cookie сохраняется автоматически."""
        resp = self.client.post(
            "/login",
            data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            name="/login",
            allow_redirects=True,
        )
        if resp.status_code not in (200, 302):
            self.environment.runner.quit()

    @task(1)
    def view_business_analytics(self):
        self.client.get("/business-analytics", name="/business-analytics")
