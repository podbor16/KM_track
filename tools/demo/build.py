"""Сборка демо: python tools/demo/build.py zhara_21 zhara_5 → dist/race-tracker-demo/

Нужен static/lib/leaflet-1.9.4 (не в git — берётся из основного чекаута / deploy/download_static_libs.py).
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env.local", override=True)   # только локальная БД, никогда прод

from tools.demo import checks, site  # noqa: E402
from tools.demo.races import BASE, RACES  # noqa: E402
from tools.demo.duathlon.source import build_duathlon  # noqa: E402
from tools.demo.siberman.source import build_siberman  # noqa: E402
from tools.demo.source import build_race  # noqa: E402
from tools.demo.triatleta.source import build_triatleta  # noqa: E402

EP_BUILDERS = {"triatleta_24h": build_triatleta, "duathlon222_2026": build_duathlon}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if os.environ.get("DB_HOST") not in ("127.0.0.1", "localhost") or str(os.environ.get("DB_PORT")) != "3308":
        print("Сборка только на локальной БД (127.0.0.1:3308)")
        return 2
    ap = argparse.ArgumentParser()
    ap.add_argument("races", nargs="+", choices=sorted(RACES))
    args = ap.parse_args()
    out = ROOT / "dist" / BASE.strip("/")
    shutil.rmtree(out, ignore_errors=True)

    cards, surnames, sib_surnames, phrases, gpx = [], set(), set(), set(), []
    ep_surnames, ep_phrases = set(), set()
    for key in args.races:
        print(f"[{key}] проигрываю гонку…", flush=True)
        if RACES[key].get("mode") == "poll":
            ep = RACES[key].get("format") == "ep"
            rec, pii = EP_BUILDERS[key](key) if ep else build_siberman(key)
            (ep_surnames if ep else sib_surnames).update(pii["real_surnames"])
            (ep_phrases if ep else phrases).update(pii["real_full_names"] | pii["real_teams"] | pii["real_cities"])
            site.write_record(out, key, rec)
            (site.render_ep if ep else site.render_siberman)(out, BASE, key, RACES[key]["slug"], rec, pii["real_surnames"])
        else:
            rec, rows = build_race(key)
            surnames |= {(r.get("surname") or "").strip() for r in rows}
            site.write_record(out, key, rec)
            site.render_tracker(out, BASE, key, RACES[key]["slug"], rec)
            gpx.append(rec["meta"]["gpx"])
        cards.append({**RACES[key], "participants": rec["meta"]["participants"],
                      "event_date": rec["meta"]["event_date"]})
        size = (out / "data" / f"{key}.json.gz").stat().st_size
        print(f"[{key}] шагов с изменениями: {len(rec['changes'])}, запись {size / 1e6:.2f} МБ")
    site.copy_static(out, BASE, gpx, siberman=any(RACES[k].get('mode') == 'poll' and RACES[k].get('format') != 'ep' for k in args.races),
                     ep=any(RACES[k].get('format') == 'ep' for k in args.races))
    site.render_index(out, BASE, cards)

    problems = checks.check_pii(out, surnames) + checks.check_links(out, BASE) + checks.check_api(out)
    def scope(ep: bool) -> tuple:
        return tuple(sc for k in args.races if (RACES[k].get("format") == "ep") == ep and RACES[k].get("mode") == "poll"
                     for sc in (RACES[k]["slug"] + "/", f"data/{k}."))

    if sib_surnames:
        problems += checks.check_pii(out, sib_surnames, phrases, scope=scope(False))
    if ep_surnames:   # в страницах Триатлета/Дуатлона нет данных участников: фразы там - текст шаблона
        problems += checks.check_pii(out, ep_surnames, ep_phrases, scope=scope(True), phrases_skip_html=True)
    for p in problems:
        print("✗", p)
    if problems:
        print("Сборка НЕ прошла проверки")
        return 1
    print(f"Готово: {out}\nПросмотр: python -m http.server -d dist 8765 → http://localhost:8765{BASE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
