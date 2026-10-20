"""/medals/ — сертификат «Забега Единства»: статика разработчика как есть (static/medals/), пути
относительные — поэтому /medals без слеша перенаправляется на /medals/."""
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)
STATIC = Path(__file__).resolve().parents[2] / "static" / "medals"


def test_medals_redirects_to_slash_and_serves_page():
    r = client.get("/medals", follow_redirects=False)
    assert r.status_code in (301, 307) and r.headers["location"].endswith("/medals/")
    r = client.get("/medals/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"] and "Забег Единства" in r.text


def test_medals_files_referenced_by_page_and_config_exist():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    refs = [m.split("?")[0] for m in re.findall(r'(?:src|href)="(\./[^"#]+)"', html)]
    config = json.loads((STATIC / "certificate.config.json").read_text(encoding="utf-8"))
    refs += [config["overlay"].split("?")[0]]
    refs += [t[k].split("?")[0] for t in config["templates"] for k in ("src", "thumbnail")]
    assert len(refs) >= 7
    for ref in refs:
        assert (STATIC / ref.removeprefix("./")).is_file(), ref
        assert client.get("/medals/" + ref.removeprefix("./")).status_code == 200, ref
