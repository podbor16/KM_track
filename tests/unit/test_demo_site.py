import gzip
import json

from tools.demo.checks import check_pii, check_links, check_api
from tools.demo.site import rewrite_static


def test_rewrite_static():
    assert rewrite_static("url('/static/fonts/a.woff')", "/race-tracker-demo/") == \
        "url('/race-tracker-demo/static/fonts/a.woff')"
    assert rewrite_static("/race-tracker-demo/static/x", "/race-tracker-demo/") == "/race-tracker-demo/static/x"


def test_check_pii_finds_surname_in_gz(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "r.json.gz").write_bytes(gzip.compress(json.dumps({"s": "Петров"}).encode()))
    assert check_pii(tmp_path, {"Петров"}) == ["data/r.json.gz: Петров"]
    assert check_pii(tmp_path, {"Сидоров"}) == []


def test_check_links(tmp_path):
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "a.css").write_text("x")
    (tmp_path / "index.html").write_text('<link href="/race-tracker-demo/static/a.css"><script src="/race-tracker-demo/static/b.js">')
    assert check_links(tmp_path, "/race-tracker-demo/") == ["index.html: /race-tracker-demo/static/b.js"]


def test_check_api(tmp_path):
    (tmp_path / "a.js").write_text("fetch('/api/current-event'); fetch('/api/secret/x')")
    assert check_api(tmp_path) == ["a.js: /api/secret/x"]


def test_check_pii_scope_and_fake_names(tmp_path):
    (tmp_path / "static" / "js").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    (tmp_path / "static" / "js" / "x.js").write_text("// Петров")
    assert check_pii(tmp_path, {"Петров"}) == []
    (tmp_path / "data" / "r.json").write_text('{"s": "Петров"}', encoding="utf-8")
    assert check_pii(tmp_path, {"Петров"}) == ["data/r.json: Петров"]
    (tmp_path / "data" / "r.json").write_text('{"name": "Роман"}', encoding="utf-8")
    assert check_pii(tmp_path, {"Роман"}) == []
