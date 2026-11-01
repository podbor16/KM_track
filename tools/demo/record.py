"""Проигрывание гонки серверным кодом → запись {meta, initial, changes, distance} (спека, п. 5)."""
import json
from datetime import datetime, timedelta

from src.krasmarafon.services.results_service import assemble_event_results
from tools.demo.timeline import rows_at

_TOL_KM = 0.0015   # шум округления current_distance до 0.001 км


def _normalize(results: list[dict]) -> list[dict]:
    """Тот же JSON, что уходит клиенту по SSE (json.dumps(default=str))."""
    return json.loads(json.dumps(results, default=str))


def compress_series(pts: list[list]) -> list[list]:
    """Оставить точки излома ломаной [[t, km], ...]; между ними — линейная интерполяция."""
    if len(pts) <= 2:
        return [list(p) for p in pts]
    keep = [list(pts[0])]
    for i in range(1, len(pts) - 1):
        (t0, d0), (t1, d1), (t2, d2) = pts[i - 1], pts[i], pts[i + 1]
        slope_in = (d1 - d0) / (t1 - t0)
        slope_out = (d2 - d1) / (t2 - t1)
        if abs(slope_out - slope_in) * (t2 - t1) > _TOL_KM:
            keep.append(list(pts[i]))
    keep.append(list(pts[-1]))
    return keep


def build_record(rows, ev_info, events, category_speeds, hist_data, *, event_id,
                 t_from: int, t_to: int, end_s: int, step_s: int) -> dict:
    """rows — уже обезличенные строки; t_* — секунды от выстрела."""
    gun_dt = None
    initial, changes, series, prev = None, [], {}, {}
    for t in range(t_from, t_to + 1, step_s):
        if gun_dt is None:
            probe = assemble_event_results(rows_at(rows, t, end_s), ev_info, events,
                                           category_speeds, hist_data, event_id=event_id)
            gun_ms = probe.race_gun_unix_ms
            gun_dt = datetime.fromtimestamp(gun_ms / 1000)
        res = assemble_event_results(rows_at(rows, t, end_s), ev_info, events, category_speeds,
                                     hist_data, event_id=event_id, now=gun_dt + timedelta(seconds=t))
        results = _normalize(res.results)
        changed = []
        for r in results:
            rid = str(r['id'])
            series.setdefault(rid, []).append([t, r['current_distance']])
            body = {k: v for k, v in r.items() if k != 'current_distance'}
            if prev.get(rid) != body:
                changed.append(body)
            prev[rid] = body
        if initial is None:
            initial = {'total_distance_km': res.total_distance_km,
                       'total_results': res.total_results, 'results': results}
        elif changed:
            changes.append({'t_s': t, 'results': changed})
    return {
        'meta': {'gun_unix_ms': gun_ms, 'step_s': step_s, 't_from': t_from, 't_to': t_to},
        'initial': initial,
        'changes': changes,
        'distance': {rid: compress_series(p) for rid, p in series.items()},
        '_normalize': _normalize,
    }


def _interp(s: list, t: float) -> float:
    if t <= s[0][0]:
        return s[0][1]
    for (t0, d0), (t1, d1) in zip(s, s[1:]):
        if t <= t1:
            return d0 + (d1 - d0) * (t - t0) / (t1 - t0)
    return s[-1][1]


def state_at(rec: dict, t: float) -> list[dict]:
    """Python-эталон того, что делает demo-replay.js: initial + changes ≤ t + ломаная."""
    by_id = {str(r['id']): dict(r) for r in rec['initial']['results']}
    for ch in rec['changes']:
        if ch['t_s'] > t:
            break
        for r in ch['results']:
            by_id[str(r['id'])].update(r)
    for rid, r in by_id.items():
        r['current_distance'] = round(_interp(rec['distance'][rid], t), 3)
    return list(by_id.values())
