"""Offline pickup checks with synthetic data only."""

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import load_workbook

from scripts.backup_pickup import build


class PickupTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.rows = root / "mysql.json"
        self.crm = root / "crm"
        self.crm.mkdir()
        self.output = root / "pickup"
        self.timestamp = datetime.now(timezone.utc)
        self.fields = ("transaction_id", "order_id", "surname", "name", "stage", "payment", "kit", "products")
        self.config = {"pickup": {
            "events": [{"key": "race-2026", "name": "Х Трейл", "year": 2026, "crm_exports": ["race"]}],
            "crm_columns": {field: field for field in self.fields},
            "status_rules": {"mysql_allow": ["active"], "crm_stage_allow": ["active"],
                             "crm_stage_block": ["closed"], "crm_payment_allow": ["paid"],
                             "crm_payment_block": ["refunded"]},
        }}

    def save_mysql(self, records):
        self.rows.write_text(json.dumps({"captured_at": self.timestamp.isoformat(), "rows": records}),
                             encoding="utf-8")

    def save_crm(self, records):
        csv_path = self.crm / "race.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.fields, delimiter=";")
            writer.writeheader()
            writer.writerows(records)
        manifest = {"kind": "tilda", "captured_at": self.timestamp.isoformat(), "artifacts": [
            {"name": "race", "file": csv_path.name, "delimiter": ";", "rows": len(records),
             "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()},
        ]}
        (self.crm / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def local(self, key, number, **changes):
        return {"id": key, "transaction_id": f"test-{key}", "order_id": key + 1000,
                "surname": "Испытатель", "name": "Тестовый", "event_name": "Х Трейл",
                "event_year": 2026, "event_distance": "5км", "start_number": number,
                "status": "active", "refund": 0, "is_duplicate": 0, **changes}

    def remote(self, key, **changes):
        return {"transaction_id": f"test-{key}", "order_id": key + 1000, "surname": "Испытатель",
                "name": "Тестовый", "stage": "active", "payment": "paid",
                "products": "5 км Забег Икс 2026", **changes}

    def test_allocates_only_confirmed_rows_and_keeps_external_values_text(self):
        self.save_mysql([self.local(1, 5), self.local(2, 6, refund=1), self.local(3, 7), self.local(4, None)])
        self.save_crm([self.remote(1, kit="=1+1"), self.remote(2, payment="refunded"),
                       self.remote(4), self.remote(5)])
        result = build(self.config, self.rows, self.crm, self.output)
        workbook = load_workbook(result / "STARTLIST-race-2026.xlsx")
        self.addCleanup(workbook.close)
        ready, review = workbook["Выдача"], workbook["Проверить"]
        self.assertEqual([row[0] for row in ready.iter_rows(min_row=2, values_only=True)], ["km:1"])
        self.assertEqual(ready["F2"].value, "=1+1")
        self.assertEqual(ready["F2"].data_type, "s")
        self.assertEqual({row[0] for row in review.iter_rows(min_row=2, values_only=True)},
                         {"km:2", "km:3", "km:4", "crm:test-5"})
        journal = load_workbook(result / "JOURNAL-race-2026.xlsx")
        self.addCleanup(journal.close)
        self.assertEqual(journal["Журнал выдачи"].max_row, 1)

    def test_shared_identifiers_route_all_candidates_to_review(self):
        self.save_mysql([self.local(1, 5), self.local(2, 6, transaction_id="test-1", order_id=1001)])
        self.save_crm([self.remote(1)])
        result = build(self.config, self.rows, self.crm, self.output)
        workbook = load_workbook(result / "STARTLIST-race-2026.xlsx")
        self.addCleanup(workbook.close)
        self.assertEqual(workbook["Выдача"].max_row, 1)
        self.assertEqual(workbook["Проверить"].max_row, 4)

    def test_stale_or_damaged_source_prevents_publication(self):
        self.save_mysql([self.local(1, 5)])
        self.timestamp -= timedelta(hours=25)
        self.save_crm([self.remote(1)])
        with self.assertRaises(ValueError):
            build(self.config, self.rows, self.crm, self.output)
        self.timestamp += timedelta(hours=25)
        self.save_crm([self.remote(1)])
        (self.crm / "race.csv").write_bytes(b"damaged")
        with self.assertRaises(ValueError):
            build(self.config, self.rows, self.crm, self.output)
        self.assertEqual(list(self.output.glob("*")), [])
