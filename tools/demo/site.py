"""Рендер страниц демо и копирование статики (спека, пп. 6–7)."""
import gzip
import html
import json
import re
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

SIBERMAN_STATIC_FILES = [
    "lib/chart4", "js/siberman-common.js", "fonts/siberman/Onest-Light.ttf", "fonts/siberman/Onest-ExtraBold.ttf",
    "images/siberman/apple-touch-icon.png", "images/siberman/favicon-32.png", "images/siberman/favicon.ico",
    "images/siberman/favicon-512.png", "images/siberman/logo-dark.png", "images/siberman/logo-light.png",
    "images/siberman/star.png",
]
PUBLIC_URL = "https://podbor16.github.io"


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


def copy_static(out: Path, base: str, gpx_files: list[str], siberman: bool = False, ep: bool = False) -> None:
    names = STATIC_FILES + (SIBERMAN_STATIC_FILES if siberman else []) + (EP_STATIC_FILES if ep else [])
    items = [ROOT / "static" / s for s in names] + [ROOT / g for g in gpx_files]
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
    event_config = {"id": ce["db_event_id"], "code": ce["event"], "name": ce.get("display_name") or ce["name"],
                    "year": ce["year"], "distance": ce["distances"][0]["distance"],
                    "title": m["title"], "description": m["caption"],
                    "coordinates": [56.0075, 92.7246]}
    html = _env().get_template("krasmarafon/tracker.html").render(
        event_title=f"{m['title']} — демо трекера", event_config=event_config, events=[],
        v="demo", base=base, race_key=key, race_title=m["title"],
        gun_ms=m["gun_unix_ms"], loop_start_s=m["loop_start_s"])
    page = out / slug / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(rewrite_static(html, base), encoding="utf-8")


def render_index(out: Path, base: str, races: list[dict]) -> None:
    env = _env()
    (out / "index.html").write_text(env.get_template("demo/index.html").render(base=base, races=races), encoding="utf-8")
    (out / "404.html").write_text(env.get_template("demo/404.html").render(base=base), encoding="utf-8")
    (out / ".nojekyll").write_text("")


def inject_demo(html_text: str, head_tag: str, strip: str) -> str:
    """Теги демо - сразу после <head> (до скриптов страницы), полоса - в начало <body>."""
    out, n = re.subn(r"<head>", lambda m: "<head>\n" + head_tag, html_text, count=1)
    out, m = re.subn(r"<body[^>]*>", lambda mt: mt.group(0) + "\n" + strip, out, count=1)
    if not (n and m):
        raise RuntimeError("в странице нет <head>/<body>")
    return out


def _poll_head_tag(base: str, key: str, slug: str, rec: dict) -> str:
    m = rec["meta"]
    days = [{k: d[k] for k in ("label", "start_s", "end_s", "start_ms", "end_ms")} for d in m["days"]]
    days_attr = html.escape(json.dumps(days, ensure_ascii=False, separators=(",", ":")), quote=True)
    return (f'<meta name="robots" content="noindex">\n<link rel="stylesheet" href="/static/demo/demo-replay.css">\n'
            f'<script src="/static/demo/demo-replay.js" data-mode="poll" data-base="{base}" data-race="{key}" '
            f'data-slug="{slug}" data-start-s="{m["loop_start_s"]}" data-days="{days_attr}"></script>\n')


def _strip(base: str, caption: str) -> str:
    return ('<div class="demo-strip" style="display:flex;align-items:center;gap:16px;padding:12px 16px;'
            'background:#14181f;color:#fff;font:15px system-ui,sans-serif">'
            f'<a href="{base}" style="color:#fff;text-decoration:none;opacity:.85">← Все демо</a>'
            f'<span>{html.escape(caption)}</span></div>')


def _scrub(text: str, real_surnames: set[str]) -> str:
    """В прод-шаблонах бывают реальные фамилии в комментариях кода - заменяем на «…»."""
    from tools.demo.checks import pii_words
    hits = pii_words(real_surnames) & set(re.findall(r"[\w-]+", text))
    for w in sorted(hits):
        print(f"  scrub: «{w[:1]}…» в шаблоне заменено")
        text = re.sub(rf"(?<!\w){re.escape(w)}(?!\w)", "…", text)
    return text


def render_siberman(out: Path, base: str, key: str, slug: str, rec: dict, real_surnames: set[str] = frozenset()) -> None:
    m = rec["meta"]
    env = _env()
    head, strip = _poll_head_tag(base, key, slug, rec), _strip(base, m["caption"])
    url = f"{PUBLIC_URL}{base}{slug}/"

    def page(path: Path, tpl: str, **ctx) -> None:
        text = env.get_template(tpl).render(v="demo", year=m["race_year"], **ctx)
        text = _scrub(text, real_surnames)
        text = re.sub(r'(property="og:url" content=")[^"]*', lambda x: x.group(1) + url, text)
        text = re.sub(r'(property="og:image" content=")[^"]*',
                      lambda x: f"{x.group(1)}{PUBLIC_URL}{base}static/images/siberman/favicon-512.png", text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rewrite_static(inject_demo(text, head, strip), base), encoding="utf-8")

    page(out / slug / "index.html", "siberman/results.html")
    # bib как в API (в БД и ответе - строка), прод-роут тоже отдаёт строку из пути
    bibs = {str(r["bib"]) for lst in ("individual", "relay") for r in rec["initial"][lst]}
    for bib in sorted(bibs):
        page(out / slug / "participant" / bib / "index.html", "siberman/participant.html", bib=bib)


EP_STATIC_FILES = [
    "lib/chart4", "css/tri_results.css", "images/favicon_tri_dark.ico", "images/favicon_tri_light.ico",
    "js/duathlon222-chart.js",
]

# Триатлет и Дуатлон: формат записи 'ep' - несколько эндпоинтов, страницы опрашивают API сами.
EP_PRODUCTS = {
    "triatleta_24h": {
        "endpoints": [{"re": r"^/api/tri/standings$", "ep": "standings"}, {"re": r"^/api/tri/laps$", "ep": "laps"}],
        "refresh": "loadStandings,loadLaps",
    },
    "duathlon222_2026": {
        "endpoints": [{"re": r"^/api/duathlon222_2026/standings$", "ep": "standings", "q": ["gender"]},
                      {"re": r"^/api/duathlon222_2026/participant/(\d+)$", "ep": "participant/$1"}],
        "participant_path": "/duathlon222_2026/participant/{n}",
        "results_path": "/duathlon222_2026",
        "refresh": "loadStandings",
        "card_refresh": "load",
    },
}


def _ep_head_tag(base: str, key: str, slug: str, rec: dict, refresh: str) -> str:
    m, prod = rec["meta"], EP_PRODUCTS[key]
    a = lambda v: html.escape(str(v), quote=True)  # noqa: E731
    eps = json.dumps(prod["endpoints"], ensure_ascii=False, separators=(",", ":"))
    extra = "".join(f' data-{k}="{a(prod[p])}"' for k, p in (("participant-path", "participant_path"),
                                                             ("results-path", "results_path")) if p in prod)
    return (f'<meta name="robots" content="noindex">\n<link rel="stylesheet" href="/static/demo/demo-replay.css">\n'
            f'<script src="/static/demo/demo-replay.js" data-mode="poll" data-format="ep" data-base="{a(base)}" '
            f'data-race="{a(key)}" data-slug="{a(slug)}" data-gun-ms="{m["gun_ms"]}" data-start-s="{m["loop_start_s"]}" '
            f'data-t-from="{m["t_from"]}" data-t-to="{m["t_to"]}" data-endpoints="{a(eps)}" '
            f'data-refresh="{a(refresh)}"{extra}></script>\n')


def render_ep(out: Path, base: str, key: str, slug: str, rec: dict, real_surnames: set[str] = frozenset()) -> None:
    """Страницы Триатлета (одна) или Дуатлона (результаты + карточка каждого номера из meta.bibs)."""
    m, prod, env = rec["meta"], EP_PRODUCTS[key], _env()
    strip = _strip(base, m["caption"])

    def page(path: Path, tpl: str, refresh: str, **ctx) -> None:
        text = _scrub(env.get_template(tpl).render(v="demo", request=None, **ctx), real_surnames)
        path.parent.mkdir(parents=True, exist_ok=True)
        head = _ep_head_tag(base, key, slug, rec, refresh)
        path.write_text(rewrite_static(inject_demo(text, head, strip), base), encoding="utf-8")

    if key == "triatleta_24h":
        page(out / slug / "index.html", "race_triatleta/tri_results.html", prod["refresh"], event_id=1)
    else:
        page(out / slug / "index.html", "race_triatleta/duathlon_results.html", prod["refresh"], year=2026)
        for n in sorted(m["bibs"]):
            page(out / slug / "participant" / str(n) / "index.html", "race_triatleta/duathlon_participant.html",
                 prod["card_refresh"], year=2026, start_number=int(n))
