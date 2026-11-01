"""Рендер страниц демо и копирование статики (спека, пп. 6–7)."""
import gzip
import json
import shutil
from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
DEMO = Path(__file__).resolve().parent

STATIC_FILES = [
    "lib/leaflet-1.9.4", "css/km-design-tokens.css", "css/krasmarafon-header.css",
    "css/navigation.css", "css/tracker.css", "css/krasmarafon-footer.css",
    "js/utils.js", "js/realtime.js", "js/tracker-api.js", "js/tracker-search.js", "js/tracker-map.js",
    "fonts/HouschkaRoundedAlt-Bold.woff", "fonts/HouschkaRoundedAlt-Medium.woff",
    "fonts/HouschkaPro-DemiBold.otf", "images/krasmarafon",
]


def rewrite_static(text: str, base: str) -> str:
    return text.replace("/static/", f"{base}static/").replace(f"{base}{base[1:]}static/", f"{base}static/")


def _env() -> Environment:
    return Environment(loader=ChoiceLoader([FileSystemLoader(DEMO / "templates"),
                                            FileSystemLoader(ROOT / "templates")]))


def _copy(src: Path, dst: Path, base: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix in (".css", ".js"):
        dst.write_text(rewrite_static(src.read_text(encoding="utf-8"), base), encoding="utf-8")
    else:
        shutil.copyfile(src, dst)


def copy_static(out: Path, base: str, gpx_files: list[str]) -> None:
    items = [ROOT / "static" / s for s in STATIC_FILES] + [ROOT / g for g in gpx_files]
    for src in items:
        files = [p for p in src.rglob("*") if p.is_file()] if src.is_dir() else [src]
        for f in files:
            _copy(f, out / f.relative_to(ROOT), base)
    # demo-replay.js перехватывает именно '/static/' — переписывать пути в нём нельзя
    (out / "static" / "demo").mkdir(parents=True, exist_ok=True)
    for f in (DEMO / "static").iterdir():
        shutil.copyfile(f, out / "static" / "demo" / f.name)


def write_record(out: Path, key: str, rec: dict) -> None:
    (out / "data").mkdir(parents=True, exist_ok=True)
    body = {k: v for k, v in rec.items() if not k.startswith("_")}
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    (out / "data" / f"{key}.json.gz").write_bytes(gzip.compress(raw, 9))


def render_tracker(out: Path, base: str, key: str, slug: str, rec: dict) -> None:
    m = rec["meta"]
    ce = m["current_event"]
    event_config = {"id": ce["db_event_id"], "code": ce["event"], "name": m["title"],
                    "year": ce["year"], "distance": ce["distances"][0]["distance"],
                    "title": m["title"], "description": m["caption"],
                    "coordinates": [56.0075, 92.7246]}
    html = _env().get_template("krasmarafon/tracker.html").render(
        event_title=f"{m['title']} — демо трекера", event_config=event_config, events=[],
        v="demo", base=base, race_key=key, race_title=m["title"])
    page = out / slug / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(rewrite_static(html, base), encoding="utf-8")


def render_index(out: Path, base: str, races: list[dict]) -> None:
    env = _env()
    (out / "index.html").write_text(env.get_template("demo/index.html").render(base=base, races=races), encoding="utf-8")
    (out / "404.html").write_text(env.get_template("demo/404.html").render(base=base), encoding="utf-8")
    (out / ".nojekyll").write_text("")
