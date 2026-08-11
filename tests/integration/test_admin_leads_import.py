"""Интеграционные тесты роутов /api/admin/leads/import/upload и /apply —
DB-слой и парсер замокированы, проверяем связку роутер+pending-файл."""
from unittest.mock import patch

import pytest

from app import app
from src.core.auth import api_require_auth
from src.krasmarafon.services.tilda_import_parser import ImportResult, ImportRow


@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    yield
    app.dependency_overrides.pop(api_require_auth, None)


def _sample_parsed():
    return ImportResult(
        rows=[ImportRow(
            row_number=2, surname="Иванов", name="Иван", birthday="1990-01-01",
            event_name="Весна", event_year=2027, event_distance="5 км",
        )],
        errors=[],
        total_rows=1,
    )


class TestLeadsImportUpload:
    def test_upload_returns_token_and_preview_counts(self, client):
        with patch(
            "src.krasmarafon.services.tilda_import_parser.parse_tilda_export",
            return_value=_sample_parsed(),
        ), patch(
            "src.analytics.db_results.preview_leads_import_matches",
            return_value=[{
                "row_number": 2, "surname": "Иванов", "name": "Иван", "birthday": "1990-01-01",
                "event_name": "Весна", "event_distance": "5 км", "matched_count": 0, "will": "create",
            }],
        ):
            r = client.post(
                "/api/admin/leads/import/upload",
                files={"file": ("export.csv", b"whatever", "text/csv")},
            )
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and data["token"]
        assert data["total_rows"] == 1
        assert data["to_update"] == 0
        assert data["to_create"] == 1
        assert data["parse_errors"] == []
        assert len(data["sample"]) == 1

    def test_upload_bad_file_returns_422(self, client):
        with patch(
            "src.krasmarafon.services.tilda_import_parser.parse_tilda_export",
            side_effect=ValueError("Неподдерживаемый формат файла: .txt"),
        ):
            r = client.post(
                "/api/admin/leads/import/upload",
                files={"file": ("export.txt", b"whatever", "text/plain")},
            )
        assert r.status_code == 422

    def test_upload_requires_auth(self, client):
        app.dependency_overrides.pop(api_require_auth, None)
        r = client.post(
            "/api/admin/leads/import/upload",
            files={"file": ("export.csv", b"whatever", "text/csv")},
        )
        assert r.status_code == 401


class TestLeadsImportApply:
    def test_apply_without_prior_upload_returns_400(self, client):
        r = client.post("/api/admin/leads/import/apply", params={"token": "does-not-exist"})
        assert r.status_code == 400

    def test_apply_with_valid_token_calls_db_layer_and_clears_pending(self, client):
        with patch(
            "src.krasmarafon.services.tilda_import_parser.parse_tilda_export",
            return_value=_sample_parsed(),
        ), patch(
            "src.analytics.db_results.preview_leads_import_matches",
            return_value=[{
                "row_number": 2, "surname": "Иванов", "name": "Иван", "birthday": "1990-01-01",
                "event_name": "Весна", "event_distance": "5 км", "matched_count": 0, "will": "create",
            }],
        ):
            upload = client.post(
                "/api/admin/leads/import/upload",
                files={"file": ("export.csv", b"whatever", "text/csv")},
            )
        token = upload.json()["token"]

        with patch(
            "src.analytics.db_results.bulk_import_leads",
            return_value={"updated": 0, "created": 1, "errors": []},
        ) as mock_bulk:
            r = client.post("/api/admin/leads/import/apply", params={"token": token})

        assert r.status_code == 200
        data = r.json()
        assert data["updated"] == 0
        assert data["created"] == 1
        assert data["errors"] == []
        mock_bulk.assert_called_once()

        # pending-файл должен быть очищен — повторный apply тем же токеном 400
        r2 = client.post("/api/admin/leads/import/apply", params={"token": token})
        assert r2.status_code == 400
