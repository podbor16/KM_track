import html
import json
import re

import pytest

from tools.demo import checks, site

META = {"gun_ms": 1000, "loop_start_s": 60, "t_from": -5, "t_to": 99, "caption": "Кап <и>", "bibs": [7, 3]}


def _attrs(tag):
    return {k: html.unescape(v) for k, v in re.findall(r'data-([\w-]+)="([^"]*)"', tag)}


def test_ep_head_tag_triatleta():
    tag = site._ep_head_tag("/b/", "triatleta_24h", "triatleta-24h", {"meta": META}, "loadStandings,loadLaps")
    a = _attrs(tag)
    assert 'name="robots" content="noindex"' in tag and "demo-replay.css" in tag
    assert (a["mode"], a["format"], a["gun-ms"], a["start-s"], a["t-from"], a["t-to"]) == ("poll", "ep", "1000", "60", "-5", "99")
    assert a["refresh"] == "loadStandings,loadLaps" and "participant-path" not in a
    assert json.loads(a["endpoints"]) == site.EP_PRODUCTS["triatleta_24h"]["endpoints"]


def test_ep_head_tag_duathlon_paths():
    a = _attrs(site._ep_head_tag("/b/", "duathlon222_2026", "duathlon222-2026", {"meta": META}, "load"))
    assert a["participant-path"] == "/duathlon222_2026/participant/{n}" and a["results-path"] == "/duathlon222_2026"
    eps = json.loads(a["endpoints"])
    assert eps[0]["q"] == ["gender"] and eps[1]["ep"] == "participant/$1"


@pytest.mark.parametrize("key, files", [
    ("triatleta_24h", ["triatleta-24h/index.html"]),
    ("duathlon222_2026", ["duathlon222-2026/index.html", "duathlon222-2026/participant/3/index.html",
                          "duathlon222-2026/participant/7/index.html"]),
])
def test_render_ep(tmp_path, monkeypatch, key, files):
    tpl = tmp_path / "t"
    (tpl / "race_triatleta").mkdir(parents=True)
    for n in ("tri_results", "duathlon_results", "duathlon_participant"):
        (tpl / "race_triatleta" / f"{n}.html").write_text(
            '<html><head><title>x</title></head><body><link href="/static/css/a.css">{{ v }}</body></html>', encoding="utf-8")
    monkeypatch.setattr(site, "_env", lambda: site.Environment(loader=site.FileSystemLoader(tpl)))
    slug = {"triatleta_24h": "triatleta-24h", "duathlon222_2026": "duathlon222-2026"}[key]
    out = tmp_path / "out"
    site.render_ep(out, "/b/", key, slug, {"meta": META})
    got = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html"))
    assert got == sorted(files)
    text = (out / files[0]).read_text(encoding="utf-8")
    assert text.index("demo-replay.js") < text.index("/b/static/css/a.css")
    assert "demo-strip" in text and "Кап &lt;и&gt;" in text


def test_ep_api_allowed(tmp_path):
    (tmp_path / "a.js").write_text("fetch('/api/tri/standings'); fetch('/api/duathlon222_2026/standings')", encoding="utf-8")
    assert checks.check_api(tmp_path) == []
    (tmp_path / "b.js").write_text("fetch('/api/other/x')", encoding="utf-8")
    assert len(checks.check_api(tmp_path)) == 1


def test_pii_phrases_skip_html(tmp_path):
    (tmp_path / "p.html").write_text("Красноярск · Триатлон", encoding="utf-8")
    (tmp_path / "d.json").write_text('{"c":"Красноярск"}', encoding="utf-8")
    got = checks.check_pii(tmp_path, set(), {"Красноярск"}, phrases_skip_html=True)
    assert got == ["d.json: Красноярск"]
