"""Проигрывание Siberman в песочнице через неизменённый прод-путь и запись (спека п. 3).

Шаг повторяет live-путь copernico_run.apply_copernico_snapshot: upsert_checkpoint_time →
update_participant_status → get_participants_for_year + get_checkpoint_times_for_year →
recompute_totals_ranks_records; ответ — как router.api_results (даты с +07:00)."""
import copy
import decimal
import json
import math
import os

from src.siberman import db as sdb
from src.siberman.service import recompute_totals_ranks_records
from tools.demo.siberman.timeline import (
    KRSK, abs_ms, compact_to_abs, day_windows, stage_day, total_compact_s,
)

LISTS = ('individual', 'relay')


def _check_demo(conn) -> None:
    cur = conn.cursor()
    cur.execute("SELECT DATABASE()")
    db = cur.fetchone()[0]
    if not db or db == 'siberman' or not db.endswith('_demo'):
        raise RuntimeError("Запись разрешена только в БД *_demo")


def _pids(conn, race_year) -> list[int]:
    cur = conn.cursor()
    cur.execute("SELECT id FROM participants WHERE race_year=%s", (race_year,))
    return [r[0] for r in cur.fetchall()]


def load_final(conn, race_year: int) -> dict:
    """Итог года (читать ДО clear_results): участники, отметки, якоря."""
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, bib, surname, name, gender, format, relay_team_name, relay_stage, status, "
                "dnf_stage, bike_day2_handicap_s FROM participants WHERE race_year=%s", (race_year,))
    participants = cur.fetchall()
    cur.execute("""SELECT t.participant_id AS pid, t.checkpoint_id AS cp_id, c.stage, c.seq,
                          t.cumulative_s, t.split_s
                   FROM checkpoint_times t JOIN checkpoints c ON c.id=t.checkpoint_id
                   JOIN participants p ON p.id=t.participant_id
                   WHERE p.race_year=%s ORDER BY t.id""", (race_year,))
    rows = cur.fetchall()
    marks = [r for r in rows if r['cumulative_s'] is not None]
    pid_cp_times: dict = {}
    for r in marks:
        pid_cp_times.setdefault(r['pid'], {})[(r['stage'], r['seq'])] = r['cumulative_s']
    cur.execute("SELECT race_start, bike2_start, run_start FROM race_config WHERE race_year=%s", (race_year,))
    anchors = cur.fetchone()
    return {'race_year': race_year, 'participants': participants, 'marks': marks,
            'skipped_null_rows': len(rows) - len(marks), 'pid_cp_times': pid_cp_times, 'anchors': anchors}


def schedule(final: dict) -> tuple[list[dict], list[dict], list[int]]:
    """Отметки с абсолютным моментом `ms` (по возрастанию), окна дней, pid без гандикапа
    (их вело-2 — от базового старта race_config.bike2_start)."""
    a = final['anchors']
    midnight = a['bike2_start'].replace(hour=0, minute=0, second=0, microsecond=0)
    base_h = (a['bike2_start'] - midnight).total_seconds()
    hcap = {p['id']: p['bike_day2_handicap_s'] for p in final['participants']}
    fallback = set()
    out = []
    for m in final['marks']:
        h = hcap.get(m['pid'])
        if m['stage'] == 'bike_day2' and h is None:
            fallback.add(m['pid'])
            h = base_h
        ms = abs_ms(m['stage'], m['cumulative_s'], race_start=a['race_start'], bike2_day_midnight=midnight,
                    handicap_s=h, run_start=a['run_start'])
        out.append({**m, 'ms': ms, 'day': stage_day(m['stage'])})
    out.sort(key=lambda m: m['ms'])
    hs = [h for h in hcap.values() if h is not None]
    first = abs_ms('bike_day2', 0, race_start=a['race_start'], bike2_day_midnight=midnight,
                   handicap_s=min(hs) if hs else base_h, run_start=a['run_start'])
    windows = day_windows([(m['day'], m['ms']) for m in out],
                          dict(race_start=a['race_start'], bike2_start=a['bike2_start'],
                               run_start=a['run_start'], bike2_first_start=first))
    return out, windows, sorted(fallback)


def clear_results(conn, race_year: int) -> None:
    """Обнулить результаты года в песочнице; рекорды — к историческому baseline (иначе
    write_best_record не тронет пары без кандидатов и в начале повтора видны итоги 2026)."""
    _check_demo(conn)
    pids = _pids(conn, race_year)
    cur = conn.cursor()
    if pids:
        ph = ','.join(['%s'] * len(pids))
        for t in ('checkpoint_times', 'transitions', 'stage_totals', 'overall_results'):
            cur.execute(f"DELETE FROM {t} WHERE participant_id IN ({ph})", pids)
    cur.execute("UPDATE participants SET status='active', dnf_stage=NULL, bike_day2_handicap_s=NULL "
                "WHERE race_year=%s", (race_year,))
    cur.execute("UPDATE siberman_records SET best_s=baseline_s, holder_name=baseline_holder_name, "
                "holder_team=baseline_holder_team, year_set=baseline_year_set")
    conn.commit()


def serialize(conn, race_year: int) -> dict:
    """Ответ /api/siberman/results (router.api_results 1-в-1, даты — ISO +07:00) после JSON."""
    data = sdb.get_results_for_year(conn, race_year)
    data["records"] = sdb.get_all_records(conn)

    def _clean(v):
        return float(v) if isinstance(v, decimal.Decimal) else v

    def _clean_row(row):
        return {k: _clean(v) for k, v in row.items()}
    data["individual"] = [_clean_row(r) for r in data["individual"]]
    for team in data["relay"]:
        team["members"] = [_clean_row(m) for m in team["members"]]
    data["checkpoints"] = [_clean_row(c) for c in data["checkpoints"]]
    for key in ("race_start", "bike2_start", "run_start"):
        if data.get(key) is not None:
            data[key] = data[key].replace(tzinfo=KRSK).isoformat()
    return json.loads(json.dumps(data))


def diff(prev: dict, cur: dict) -> dict | None:
    """Изменения prev→cur: элементы individual/relay целиком (по bib), удалённые bib,
    порядок bib (если изменился) и прочие ключи ответа целиком."""
    ch: dict = {}
    for key in LISTS:
        old = {r['bib']: r for r in prev.get(key, [])}
        new = cur.get(key, [])
        changed = [r for r in new if old.get(r['bib']) != r]
        if changed:
            ch[key] = changed
        bibs = {r['bib'] for r in new}
        gone = [b for b in old if b not in bibs]
        if gone:
            ch.setdefault('removed', {})[key] = gone
        order = [r['bib'] for r in new]
        if order != [r['bib'] for r in prev.get(key, [])]:
            ch.setdefault('order', {})[key] = order
    top = {k: v for k, v in cur.items() if k not in LISTS and prev.get(k) != v}
    gone_top = [k for k in prev if k not in LISTS and k not in cur]
    if top:
        ch['top'] = top
    if gone_top:
        ch['top_removed'] = gone_top
    return ch or None


def apply_change(state: dict, ch: dict) -> dict:
    out = dict(state)
    for key in LISTS:
        by_bib = {r['bib']: r for r in state.get(key, [])}
        for b in ch.get('removed', {}).get(key, []):
            by_bib.pop(b, None)
        for r in ch.get(key, []):
            by_bib[r['bib']] = r
        order = ch.get('order', {}).get(key) or [r['bib'] for r in state.get(key, []) if r['bib'] in by_bib]
        out[key] = [by_bib[b] for b in order]
    out.update(ch.get('top', {}))
    for k in ch.get('top_removed', []):
        out.pop(k, None)
    return out


def state_at(rec: dict, t: float) -> dict:
    """Python-эталон demo-replay.js: initial + все changes с t_s ≤ t."""
    state = copy.deepcopy(rec['initial'])
    for ch in rec['changes']:
        if ch['t_s'] > t:
            break
        state = apply_change(state, ch)
    return state


def _set_handicaps(conn, final) -> None:
    cur = conn.cursor()
    for p in final['participants']:
        cur.execute("UPDATE participants SET bike_day2_handicap_s=%s WHERE id=%s",
                    (p['bike_day2_handicap_s'], p['id']))


def _recompute(conn, race_year) -> None:
    fresh = sdb.get_participants_for_year(conn, race_year)
    cumulative, _splits = sdb.get_checkpoint_times_for_year(conn, race_year)
    pid_cp_times = {
        pid: {(stage, seq): v for stage, seqs in stages.items() for seq, v in seqs.items()}
        for pid, stages in cumulative.items()
    }
    recompute_totals_ranks_records(conn, race_year, fresh, pid_cp_times)


def replay(conn, race_year: int, final: dict, windows: list[dict] | None = None, step_s: int = 20,
           on_step=None) -> dict:
    """Проиграть очищенный (clear_results) год по итогу final. windows — по умолчанию из schedule().
    Один шаг — одна транзакция; recompute только на шагах, где что-то записано."""
    _check_demo(conn)
    marks, own_windows, fallback_pids = schedule(final)
    windows = windows or own_windows
    cur_db = conn.cursor()
    cur_db.execute("SELECT DATABASE()")
    os.environ['SIBERMAN_DB_NAME'] = cur_db.fetchone()[0]  # своё соединение прод-кода — тоже в песочницу
    from src.siberman.persons import service as persons_service
    saved_sync = persons_service.sync_safe
    persons_service.sync_safe = lambda: None
    try:
        total = math.ceil(total_compact_s(windows))
        ts = list(range(0, total, step_s)) + [total]
        day1_end, last_end = windows[0]['end_ms'], windows[-1]['end_ms']
        i, hcap_done, status_done = 0, False, False
        initial, prev, changes, steps_changed = None, None, [], 0
        for t in ts:
            now = compact_to_abs(t, windows)
            dirty = initial is None
            while i < len(marks) and marks[i]['ms'] <= now:
                m = marks[i]
                sdb.upsert_checkpoint_time(conn, m['pid'], m['cp_id'], m['cumulative_s'], m['split_s'])
                i += 1
                dirty = True
            if not hcap_done and now >= day1_end:
                _set_handicaps(conn, final)
                hcap_done = dirty = True
            if not status_done and now >= last_end:
                for p in final['participants']:
                    if p['status'] != 'active' or p['dnf_stage'] is not None:
                        sdb.update_participant_status(conn, p['id'], p['status'], p['dnf_stage'])
                status_done = dirty = True
            if not dirty:
                continue
            _recompute(conn, race_year)
            conn.commit()
            cur = serialize(conn, race_year)
            if initial is None:
                initial = cur
            else:
                ch = diff(prev, cur)
                if ch:
                    changes.append({'t_s': t, **ch})
                    steps_changed += 1
            prev = cur
            if on_step:
                on_step(t, total)
        if i != len(marks):
            raise RuntimeError(f"не проиграно отметок: {len(marks) - i}")
    finally:
        persons_service.sync_safe = saved_sync

    a = final['anchors']
    offs, acc = [], 0
    for w in windows:
        offs.append(acc)
        acc += (w['end_ms'] - w['start_ms']) / 1000
    meta = {
        'race_year': race_year, 'step_s': step_s, 'total_s': total, 'steps': len(ts),
        'steps_changed': steps_changed,
        'anchors': {k: a[k].replace(tzinfo=KRSK).isoformat() for k in ('race_start', 'bike2_start', 'run_start')},
        'days': [{'label': w['label'], 'start_s': o, 'end_s': o + (w['end_ms'] - w['start_ms']) / 1000,
                  'start_ms': w['start_ms'], 'end_ms': w['end_ms']} for w, o in zip(windows, offs)],
        'bike2_handicap_fallback_count': len(fallback_pids),
        'skipped_null_rows': final['skipped_null_rows'],
    }
    return {'meta': meta, 'initial': initial, 'changes': changes}
