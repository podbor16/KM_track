"""Входные данные демо-гонки: локальная БД (.env.local) + YAML-конфиг."""
from pathlib import Path

from src.analytics.db_connection_optimized import (
    get_race_results_by_event_id, get_event_info_by_id, get_category_avg_paces,
    get_pooled_connection,
)
from src.config.event_loader import load_all_events
from src.krasmarafon.routers.api import build_current_event_response
from src.krasmarafon.services.results_service import load_hist_data
from tools.demo.anonymize import anonymize
from tools.demo.record import build_record
from tools.demo.races import RACES, LOOP_START_S, TAIL_S, STEP_S

ROOT = Path(__file__).resolve().parents[2]


def _finish_s(r):
    v = r.get('time_gun_finish')
    return v.total_seconds() if v is not None and r.get('race_status') == 'Finished' else None


def _load_finish_ms(event_id: int) -> dict:
    """get_race_results_by_event_id не отдаёт *_ms — они нужны тай-брейку мест в одну секунду."""
    conn = get_pooled_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, time_gun_finish_ms, time_clear_finish_ms FROM results WHERE event_id = %s",
                    (event_id,))
        return {r['id']: r for r in cur.fetchall()}
    finally:
        conn.close()


def pick_preselect(rows: list[dict]) -> list[int]:
    """id записи (индекс строки + 1) пяти «интересных» финишировавших: 1-е, 2-е место, 25/50/75% по месту."""
    fin = sorted((r['rank_absolute'], i + 1) for i, r in enumerate(rows)
                 if r.get('race_status') == 'Finished' and r.get('rank_absolute') is not None)
    n = len(fin)
    out: list[int] = []
    for idx in (0, 1, int(n * 0.25), int(n * 0.5), int(n * 0.75)):
        if idx < n and fin[idx][1] not in out:
            out.append(fin[idx][1])
    return out


def build_race(key: str) -> tuple[dict, list[dict]]:
    race = RACES[key]
    events = load_all_events(ROOT / "config" / "events")
    event = events[race["config_code"]]
    ms = _load_finish_ms(race["db_event_id"])
    rows = [{**r, **{k: v for k, v in ms.get(r['id'], {}).items() if k != 'id'}}
            for r in get_race_results_by_event_id(race["db_event_id"])]
    ev_info = get_event_info_by_id(race["db_event_id"]) or {}
    ev_name, ev_dist, ev_year = ev_info['event_name'], ev_info.get('event_distance'), ev_info['event_year']
    cat_speeds = get_category_avg_paces(ev_name, ev_dist, ev_year) if ev_name else {}
    hist = load_hist_data(ev_name, ev_dist, ev_year)

    anon, key_map = anonymize(rows, seed=race["db_event_id"])
    hist = {**hist, 'personal': {key_map[k]: v for k, v in hist['personal'].items() if k in key_map}}

    finishes = sorted(f for f in map(_finish_s, rows) if f is not None)
    if not finishes:
        raise RuntimeError(f"{key}: нет финишировавших — нечего проигрывать")
    mass = finishes[int(len(finishes) * 0.95) - 1]
    end_s = int(finishes[-1]) + TAIL_S
    rec = build_record(anon, ev_info, events, cat_speeds, hist, event_id=race["db_event_id"],
                       t_from=-TAIL_S, t_to=end_s, end_s=end_s, step_s=STEP_S)

    payload = build_current_event_response(event).model_dump()
    payload['distances'] = [d for d in payload['distances'] if d['db_event_id'] == race["db_event_id"]]
    d = payload['distances'][0]
    payload.update(db_event_id=race["db_event_id"], gpx_file=d['gpx_file'],
                   storage_key=f"demo_{key}_selected_runners")
    loop_start = race.get('loop_start_s', LOOP_START_S)
    if loop_start >= finishes[0]:
        print(f"ПРЕДУПРЕЖДЕНИЕ {key}: loop_start_s={loop_start} >= первого финиша {int(finishes[0])}")
    rec['meta'].update(
        race=key, title=race["title"], caption=race["caption"], current_event=payload,
        gpx=d['gpx_file'], loop_start_s=loop_start, preselect=pick_preselect(rows), loop_end_s=int(mass) + TAIL_S,
        marks=[{'label': 'Старт', 't_s': 0},
               {'label': 'Первый финиш', 't_s': int(finishes[0])},
               {'label': 'Массовый финиш', 't_s': int(mass)}],
        participants=len(rows), event_date=d['event_date'],
    )
    return rec, rows
