import json
from unittest.mock import Mock

import pytest

from scripts import backup_tilda


EXPORT = {
    "name": "test-stage",
    "required_headers": ["tranid", "Stage"],
    "delimiter": ";",
}


def test_validates_csv_with_excel_bom_and_multiline_value(tmp_path):
    path = tmp_path / "test-stage.csv"
    path.write_text('tranid;Stage;Notes\n99;Ready;"line\nbreak"\n', encoding="utf-8-sig")
    artifact = backup_tilda.validate_csv(path, EXPORT)
    assert artifact["rows"] == 1
    assert artifact["delimiter"] == ";"
    assert len(artifact["sha256"]) == 64


@pytest.mark.parametrize("payload", [
    "<html>Session expired</html>",
    "tranid;Stage\n",
    "tranid;Stage\n99;Ready;Unexpected\n",
])
def test_rejects_wrong_or_incomplete_export(tmp_path, payload):
    path = tmp_path / "test-stage.csv"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(backup_tilda.BackupError):
        backup_tilda.validate_csv(path, EXPORT)


def test_capture_keeps_old_version_when_any_export_fails(tmp_path, monkeypatch):
    state = tmp_path / "session.json"
    state.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(backup_tilda, "launch_browser", Mock(return_value=Mock()))

    def download(_page, export, path):
        if export["name"] == "failed-stage":
            path.write_text("<html>Session expired</html>", encoding="utf-8")
        else:
            path.write_text("tranid;Stage\n99;Ready\n", encoding="utf-8")

    monkeypatch.setattr(backup_tilda, "download_export", download)
    config = {"exports": [EXPORT]}
    backup_tilda.capture(Mock(), config, tmp_path, state, RuntimeError)
    manifests = list((tmp_path / "tilda").glob("*/manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["artifacts"][0]["file"] == "test-stage.csv"
    assert (manifests[0].parent / "test-stage.csv").is_file()

    config["exports"].append({**EXPORT, "name": "failed-stage"})
    with pytest.raises(backup_tilda.BackupError, match="failed-stage"):
        backup_tilda.capture(Mock(), config, tmp_path, state, RuntimeError)
    assert list((tmp_path / "tilda").iterdir()) == [manifests[0].parent]
