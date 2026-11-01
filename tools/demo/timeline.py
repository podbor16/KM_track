"""Строки results «как в момент T» (секунды от выстрела) — спека, п. 5."""
import re
from functools import lru_cache
from datetime import timedelta

from load_race_results import RaceLoader

_KT_RE = re.compile(r'^(?:time_(?:gun|clear)|pace_avg)_kt(\d)(?:_ms)?$')
_RANK_FIELDS = ('rank_absolute', 'rank_sex', 'rank_category',
                'rank_absolute_clean', 'rank_sex_clean', 'rank_category_clean')
_FINAL_ONLY = ('DNF', 'DSQ', 'Withdrawn')


def _s(v) -> float | None:
    return v.total_seconds() if isinstance(v, timedelta) else None


def _finish_field(k: str) -> bool:
    return k.startswith(('time_gun_finish', 'time_clear_finish', 'finish_pace'))


def _start_field(k: str) -> bool:
    return k.startswith(('time_gun_start', 'time_clear_start'))


@lru_cache(maxsize=None)
def _classify(k: str):
    """Имя поля → ('kt', N) | ('finish',) | ('start',) | None; имён мало — кеш."""
    m = _KT_RE.match(k)
    if m:
        return ('kt', m.group(1))
    if _finish_field(k):
        return ('finish',)
    if _start_field(k):
        return ('start',)
    return None


def _row_at(r: dict, t: float, end_s: float) -> dict:
    start = _s(r.get('time_gun_start'))
    finish = _s(r.get('time_gun_finish'))
    eff_start = start if start is not None else (
        0.0 if r.get('race_status') != 'Not started' else None)
    a = dict(r)
    for k in r:
        c = _classify(k)
        if c is None:
            continue
        if c[0] == 'kt':
            kt = _s(r.get(f'time_clear_kt{c[1]}'))   # official: от выстрела
            if kt is None or kt > t:
                a[k] = None
        elif c[0] == 'finish':
            if finish is None or finish > t:
                a[k] = None
        elif start is None or start > t:
            a[k] = None
    for k in _RANK_FIELDS:
        a[k] = None
    final = r.get('race_status')
    if final in _FINAL_ONLY and t >= end_s:
        a['race_status'] = final
    elif a.get('time_gun_finish') is not None and final == 'Finished':
        a['race_status'] = 'Finished'
    elif eff_start is not None and eff_start <= t:
        a['race_status'] = 'Running'
    else:
        a['race_status'] = 'Not started'
    return a


def _key(r: dict, time_key: str):
    return (r[time_key].total_seconds(), (r.get(f'{time_key}_ms') or 0) % 1000)


def _assign(rows: list[dict], time_key: str, field: str) -> None:
    for r in rows:
        r['_k'] = _key(r, time_key)
    groups = {field: [rows]}
    for g_field, attr in ((field.replace('absolute', 'sex'), 'sex'),
                          (field.replace('absolute', 'category'), 'category')):
        by = {}
        for r in rows:
            if r.get(attr):
                by.setdefault(r[attr], []).append(r)
        groups[g_field] = list(by.values())
    for f, lists in groups.items():
        for group in lists:
            ranks = RaceLoader._assign_ranks(group, '_k')
            for r in group:
                r[f] = ranks.get(r['id'])
    for r in rows:
        del r['_k']


def rows_at(rows: list[dict], t: float, end_s: float) -> list[dict]:
    """t, end_s — секунды от выстрела. end_s — момент, с которого видны DNF/DSQ."""
    out = [_row_at(r, t, end_s) for r in rows]
    finished = [r for r in out if r['race_status'] == 'Finished' and r.get('time_gun_finish')]
    _assign(finished, 'time_gun_finish', 'rank_absolute')
    _assign([r for r in finished if r.get('time_clear_finish')], 'time_clear_finish', 'rank_absolute_clean')
    return out
