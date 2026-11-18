import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts import backup_krasmarafon as backup


def make_pickup(storage, age, data):
    now = datetime.now(timezone.utc)
    suffix = hashlib.sha256(data.encode()).hexdigest()[:8]
    bundle = storage / "pickup" / f"{now:%Y%m%dT%H%M%SZ}-{suffix}"
    bundle.mkdir(parents=True)
    artifacts = []
    for prefix, contents in (("STARTLIST", data), ("JOURNAL", "template")):
        file = bundle / f"{prefix}-pilot.xlsx"
        file.write_text(contents, encoding="utf-8")
        artifacts.append({"file": file.name, "sha256": backup.file_hash(file)})
    (bundle / "manifest.json").write_text(json.dumps({
        "captured_at": now.isoformat(),
        "mysql_captured_at": now.isoformat(),
        "crm_captured_at": (now - timedelta(hours=age)).isoformat(),
        "artifacts": artifacts,
    }), encoding="utf-8")
    return bundle


def test_delivery_replaces_list_and_keeps_operator_journal(tmp_path):
    storage, destination, mirror = [tmp_path / name for name in ("primary", "desk", "mirror")]
    make_pickup(storage, 1, "previous")
    backup.publish(storage, destination)
    journal = destination / "JOURNAL-pilot.xlsx"
    journal.write_text("operator entry", encoding="utf-8")
    make_pickup(storage, 0, "updated0")
    backup.publish(storage, destination)
    assert (destination / "STARTLIST-pilot.xlsx").read_text(encoding="utf-8") == "updated0"
    assert journal.read_text(encoding="utf-8") == "operator entry"
    assert backup.delivery_times([destination])
    assert backup.mirror_bundles(storage, mirror)
    assert len(backup.current_bundles(mirror / "pickup")) == 2


def test_delivery_uses_age_of_oldest_source_and_verifies_checksums(tmp_path):
    stale = tmp_path / "stale"
    make_pickup(stale, 25, "old-data")
    with pytest.raises(ValueError, match="24 часа"):
        backup.publish(stale, tmp_path / "desk")
    fresh = tmp_path / "fresh"
    bundle = make_pickup(fresh, 0, "new-data")
    (bundle / "STARTLIST-pilot.xlsx").write_text("corruption", encoding="utf-8")
    with pytest.raises(ValueError, match="целостности"):
        backup.publish(fresh, tmp_path / "desk")
    assert not (tmp_path / "desk").exists()
