"""Граница 30 лет для публичных результатов."""

import asyncio
from datetime import date
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.krasmarafon.routers.api import get_event_results
from src.krasmarafon.services import results_service
from src.krasmarafon.services.public_event_access import (
    event_is_public, event_name_year_is_public, is_within_publication_term, result_is_public,
)


def test_anniversary_is_first_closed_day():
    race = date(1996, 7, 28)
    assert is_within_publication_term(race, date(2026, 7, 27))
    assert not is_within_publication_term(race, date(2026, 7, 28))


def test_leap_day_expires_on_february_28():
    race = date(1996, 2, 29)
    assert is_within_publication_term(race, date(2026, 2, 27))
    assert not is_within_publication_term(race, date(2026, 2, 28))


def test_missing_date_cannot_be_published():
    assert not is_within_publication_term(None, date(2026, 11, 26))


def test_event_and_result_access_use_the_same_rule():
    with patch("src.krasmarafon.services.public_event_access._event_dates", return_value=(date(1996, 7, 28),)), \
         patch("src.krasmarafon.services.public_event_access._result_event_id", return_value=123):
        assert event_is_public(123, date(2026, 7, 27))
        assert not event_is_public(123, date(2026, 7, 28))
        assert not result_is_public(456, date(2026, 7, 28))


def test_name_and_year_cannot_mix_expired_and_current_distances():
    with patch("src.krasmarafon.services.public_event_access._name_year_dates",
               return_value=(date(1996, 7, 28), date(1996, 7, 29))):
        assert not event_name_year_is_public("race", 1996, date(2026, 7, 28))


def test_expired_event_cannot_be_served_from_json_cache():
    key = "123|None|None"
    results_service._json_cache[key] = '{"results":[{"surname":"private"}]}'
    results_service._response_cache_ts[key] = 10**12
    try:
        with patch("src.krasmarafon.routers.api.event_is_public", return_value=False):
            with pytest.raises(HTTPException) as error:
                asyncio.run(get_event_results(event_id=123, event_name=None, year=None))
        assert error.value.status_code == 404
    finally:
        results_service._json_cache.pop(key, None)
        results_service._response_cache_ts.pop(key, None)
