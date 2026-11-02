import gzip
import json

from tools.demo import checks
from tools.demo.checks import check_pii, check_links, check_api
import pytest

from tools.demo import site
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


def test_check_pii_phrases(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.json").write_text('{"team":"Быстрые \u041b\u043e\u0441\u0438","c":"Ok"}', encoding="utf-8")
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "a.js").write_text("Быстрые Лоси", encoding="utf-8")
    assert checks.check_pii(tmp_path, set(), {"быстрые лоси", "Ok"}) == ["data/x.json: быстрые лоси"]
    assert checks.check_pii(tmp_path, set()) == []


def test_inject_demo():
    src = '<html><head>\n<meta charset="utf-8"><script src="/a.js"></script></head><body class="x"><p>hi</p></body></html>'
    out = site.inject_demo(src, '<script id="demo"></script>\n', '<div id="strip"></div>')
    assert out.index('id="demo"') < out.index('/a.js')
    assert out.index('<body class="x">') < out.index('id="strip"') < out.index('<p>')
    with pytest.raises(RuntimeError):
        site.inject_demo('<p>no head</p>', 'a', 'b')


def test_check_pii_phrases(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.json").write_text('{"team":"\u0411\u044b\u0441\u0442\u0440\u044b\u0435 \u041b\u043e\u0441\u0438","c":"Ok"}', encoding="utf-8")
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "a.js").write_text("Быстрые Лоси", encoding="utf-8")
    assert checks.check_pii(tmp_path, set(), {"быстрые лоси", "Ok"}) == ["data/x.json: быстрые лоси"]
    assert checks.check_pii(tmp_path, set()) == []


def test_inject_demo():
    src = '<html><head>\n<meta charset="utf-8"><script src="/a.js"></script></head><body class="x"><p>hi</p></body></html>'
    out = site.inject_demo(src, '<script id="demo"></script>\n', '<div id="strip"></div>')
    assert out.index('id="demo"') < out.index('/a.js')
    assert out.index('<body class="x">') < out.index('id="strip"') < out.index('<p>')
    with pytest.raises(RuntimeError):
        site.inject_demo('<p>no head</p>', 'a', 'b')


def test_check_pii_phrases_word_boundary_and_scope(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "x.html").write_text("заблокирован, Киров", encoding="utf-8")
    (tmp_path / "b" / "y.html").write_text("Киров", encoding="utf-8")
    assert checks.check_pii(tmp_path, set(), {"Киров"}, scope=("a/",)) == ["a/x.html: Киров"]
    assert checks.check_pii(tmp_path, set(), {"Киров"}) == ["a/x.html: Киров", "b/y.html: Киров"]


def test_scrub_real_surname():
    out = site._scrub("// Дащенко с DNF; Юров и Север", {"Дащенко", "Юров"})
    assert "Дащенко" not in out and "Юров" in out

