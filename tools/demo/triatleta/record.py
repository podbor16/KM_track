"""Проигрывание Триатлета 24 ч в песочнице через неизменённый прод-код и запись (спека п.3).

На шаге T (сек от выстрела) в laps дописываются круги с cumulative_ms ≤ T·1000 (как их пишет
load_tri_results._process_laps); ответы — прод src.race_triatleta.service под use_sandbox,
обёртки — как в router (/api/tri/standings, /api/tri/laps)."""
import math
from datetime import datetime, timedelta, timezone

from src.race_triatleta import service
from tools.demo.replay_poll import record_steps, time_grid
from tools.demo.sandbox import use_sandbox

EVENT_ID = 1
DEMO_DB = 'triatleta_24h_demo'
KRSK = timezone(timedelta(hours=7))
GUN = datetime(2026, 6, 25, 20, 0, 0, tzinfo=KRSK)  # во фронте: GUN_UTC_MS = 2026-06-25T13:00:00Z
RUNNING = 'running'  # статус Copernico «на дистанции» (до схода/финиша)
MARGIN_S = 300
SPEC = {
    'standings': {'fields': {'standings': {'key': ['start_number'], 'item': {'fields': {}}}}},
    'laps': {'fields': {'laps': {'key': ['participant_id', 'lap_number']}}},
}


def _check_demo(conn) -> None:
    cur = conn.cursor()
    cur.execute("SELECT DATABASE()")
    db = cur.fetchone()[0]
    if not db or not db.endswith('_demo'):
        raise RuntimeError("Запись разрешена только в БД *_demo")


def load_final(conn) -> dict:
    """Итог события (читать ДО clear_results): участники со статусами и все круги."""
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, start_number, status FROM participants WHERE event_id=%s ORDER BY id", (EVENT_ID,))
    participants = cur.fetchall()
    cur.execute("SELECT id, participant_id, event_id, lap_number, cumulative_ms, lap_ms FROM laps "
                "WHERE event_id=%s ORDER BY cumulative_ms, id", (EVENT_ID,))
    return {'participants': participants, 'laps': cur.fetchall()}


def clear_results(conn) -> None:
    _check_demo(conn)
    cur = conn.cursor()
    cur.execute("DELETE FROM laps WHERE event_id=%s", (EVENT_ID,))
    cur.execute("UPDATE participants SET status=%s WHERE event_id=%s", (RUNNING, EVENT_ID))
    conn.commit()


def status_reveals(final: dict) -> list[tuple[float, dict]]:
    """[(сек от выстрела, участник)]: итоговый статус (finished/dnf/dsq/…) — с последнего круга
    участника (кругов нет — с выстрела). В 24-часовой гонке Copernico ставит finished тому,
    кто закончил ездить, поэтому и «финиш» — это последний круг."""
    last = {}
    for lap in final['laps']:
        last[lap['participant_id']] = lap['cumulative_ms'] / 1000
    out = [(last.get(p['id'], 0), p) for p in final['participants'] if (p['status'] or RUNNING) != RUNNING]
    return sorted(out, key=lambda x: x[0])


def _responses() -> dict:
    """Ответы эндпоинтов (обёртки — как в router); подключение уже подменено use_sandbox."""
    return {'standings': {'standings': service.get_standings(EVENT_ID, None)},
            'laps': {'laps': service.get_all_laps(EVENT_ID)}}


def snapshot() -> dict:
    with use_sandbox(service, 'get_tri_connection', DEMO_DB):
        return _responses()


def replay(conn, final: dict, step_s: int = 30, on_step=None) -> dict:
    """Проиграть очищенное (clear_results) событие по итогу final."""
    _check_demo(conn)
    laps = final['laps']
    last_s = laps[-1]['cumulative_ms'] / 1000 if laps else 0
    t_from, t_to = -MARGIN_S, math.ceil(last_s) + MARGIN_S
    ts = time_grid(t_from, t_to, step_s)
    pending = status_reveals(final)
    state = {'i': 0}
    cur = conn.cursor()

    def advance(t):
        dirty = False
        while state['i'] < len(laps) and laps[state['i']]['cumulative_ms'] <= t * 1000:
            lap = laps[state['i']]
            cur.execute("INSERT INTO laps (id, participant_id, event_id, lap_number, cumulative_ms, lap_ms) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (lap['id'], lap['participant_id'], lap['event_id'], lap['lap_number'],
                         lap['cumulative_ms'], lap['lap_ms']))
            state['i'] += 1
            dirty = True
        while pending and pending[0][0] <= t:
            _, p = pending.pop(0)
            cur.execute("UPDATE participants SET status=%s WHERE id=%s", (p['status'], p['id']))
            dirty = True
        conn.commit()
        return dirty

    with use_sandbox(service, 'get_tri_connection', DEMO_DB):
        initial, changes = record_steps(ts, advance, _responses, SPEC, on_step)
    if state['i'] != len(laps) or pending:
        raise RuntimeError("проиграны не все круги/статусы")
    meta = {
        'product': 'triatleta_24h',
        'gun': GUN.isoformat(), 'gun_ms': int(GUN.timestamp() * 1000),
        'step_s': step_s, 't_from': t_from, 't_to': t_to,
        'steps': len(ts), 'steps_changed': len(changes),
        'marks': [{'label': 'Старт', 't_s': 0}, {'label': '6 ч', 't_s': 21600}, {'label': '12 ч', 't_s': 43200},
                  {'label': '18 ч', 't_s': 64800}, {'label': 'Финиш', 't_s': last_s}],
        'loop_start_s': 7200,
        'spec': SPEC,
    }
    return {'meta': meta, 'initial': initial, 'changes': changes}
