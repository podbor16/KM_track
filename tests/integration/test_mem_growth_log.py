"""Middleware log_request_duration: запрос, за который RSS воркера вырос на 20+ МБ, пишется в лог."""
import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


def test_logs_request_that_grew_rss(caplog):
    with patch.object(app_module, "rss_mb", side_effect=[100.0, 135.0]), \
            caplog.at_level(logging.WARNING, logger="km_track.perf"):
        client.get("/health")
    assert any(r.getMessage().startswith("MEM +35MB (rss 135MB) GET /health") for r in caplog.records)


def test_small_growth_and_no_proc_are_silent(caplog):
    with patch.object(app_module, "rss_mb", side_effect=[100.0, 110.0, None, None]), \
            caplog.at_level(logging.WARNING, logger="km_track.perf"):
        client.get("/health")
        client.get("/health")
    assert not any(r.getMessage().startswith("MEM") for r in caplog.records)
