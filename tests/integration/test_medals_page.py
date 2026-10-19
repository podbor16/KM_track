"""/medals — сертификат «Забега Единства» (статика static/medals/, пути к файлам абсолютные)."""
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)
STATIC = Path(__file__).resolve().parents[2] / "static" / "medals"


def test_medals_page_served_with_and_without_slash():
    for url in ("/medals", "/medals/"):
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert "Забег Единства" in r.text


def test_medals_assets_are_absolute_and_exist():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="(/static/medals/[^"?]+)', html)
    assert {"/static/medals/app.js", "/static/medals/styles.css", "/static/medals/favicon.svg"} <= set(refs)
    assert './' not in re.sub(r"<use href=\"#[^\"]+\"", "", html).replace('href="./"', "")
    config = json.loads((STATIC / "certificate.config.json").read_text(encoding="utf-8"))
    overlay = config["overlay"].split("?")[0]
    assert overlay.startswith("/static/medals/")
    for ref in refs + [overlay, "/static/medals/composition.js", "/static/medals/gestures.js"]:
        assert (STATIC / ref.removeprefix("/static/medals/")).is_file(), ref
    assert "fetch('/static/medals/certificate.config.json" in (STATIC / "app.js").read_text(encoding="utf-8")
