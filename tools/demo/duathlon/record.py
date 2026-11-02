"""Проигрывание Дуатлона 222 в песочнице через неизменённый прод-код и запись (спека п.3).

Смысл колонок participants (load_duathlon_results._process_stages_and_transitions, всё — целые
секунды от выстрела, кроме t1_s/t2_s):
  run1_s, bike_s, run2_s — МОМЕНТЫ финиша этапов («наступают» в своё значение);
  bike_start_s, run2_start_s — моменты выхода из Т1/Т2 на этап (там же «наступают»);
  t1_s, t2_s — ДЛИТЕЛЬНОСТИ транзита, Copernico даёт их вместе со стартом следующего этапа →
  «наступают» в bike_start_s / run2_start_s.
checkpoints.cumulative_s — моменты отметок от выстрела. Статус finished — с run2_s,
dnf/dsq — с последней отметки участника (нет отметок — с выстрела)."""
import math
from datetime import datetime, timedelta, timezone

from src.duathlon222 import service
from tools.demo.replay_poll import record_steps, time_grid
from tools.demo.sandbox import use_sandbox

EVENT_ID = 1
DEMO_DB = 'duathlon_222_demo'
KRSK = timezone(timedelta(hours=7))
GUN = datetime(2026, 9, 5, 7, 1, 51, 797000, tzinfo=KRSK)  # во фронте: GUN_UTC_MS = 2026-09-05T00:01:51.797Z
ACTIVE = 'active'
MARGIN_S = 300
STAGE_COLS = ('run1_s', 't1_s', 'bike_s', 't2_s', 'run2_s', 'bike_start_s', 'run2_start_s')
# колонка -> колонка, в момент которой она появляется
COL_MOMENT = {'run1_s': 'run1_s', 'bike_start_s': 'bike_start_s', 't1_s': 'bike_start_s',
              'bike_s': 'bike_s', 'run2_start_s': 'run2_start_s', 't2_s': 'run2_start_s', 'run2_s': 'run2_s'}
_STAGES = ('run1', 'bike', 'run2')
_STANDINGS = {'fields': {'standings': {'key': ['start_number'], 'item': {'fields': {
    'checkpoints': {'fields': {s: {'key': ['lap']} for s in _STAGES}}}}}}}
_PARTICIPANT = {'fields': {'stages': {'fields': {s: {'fields': {'laps': {'key': ['lap_number']}}} for s in _STAGES}}}}


def spec_for(bibs) -> dict:
    spec = {'standings': _STANDINGS, 'standings?gender=M': _STANDINGS, 'standings?gender=F': _STANDINGS}
    spec.update({f'participant/{n}': _PARTICIPANT for n in bibs})
    return spec


def _check_demo(conn) -> None:
    cur = conn.cursor()
    cur.execute("SELECT DATABASE()")
    db = cur.fetchone()[0]
    if not db or not db.endswith('_demo'):
        raise RuntimeError("Запись разрешена только в БД *_demo")


def prepare(conn) -> None:
    """Перенумеровать id отметок в порядке (участник, этап, отметка) — ДО load_final и «итога».
    get_participant ранжирует отметки устойчивой сортировкой по cumulative_s без ORDER BY в SQL,
    поэтому равные времена упорядочивает план запроса: скан checkpoints по id или
    participants → индекс (participant_id, stage, lap_number). План зависит от статистики,
    а она в ходе повтора другая, чем на полных данных; при таком порядке id оба плана дают
    одинаковые строки, и ответы не зависят от плана."""
    _check_demo(conn)
    cur = conn.cursor()
    cur.execute("SET @n := 0")
    cur.execute("UPDATE checkpoints SET id = (@n := @n + 1) + 1000000000 ORDER BY participant_id, stage, lap_number")
    cur.execute("UPDATE checkpoints SET id = id - 1000000000 ORDER BY id")
    conn.commit()


def load_final(conn) -> dict:
    """Итог события (читать ДО clear_results): участники с этапами/статусами и все отметки."""
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT id, start_number, status, {', '.join(STAGE_COLS)} FROM participants "
                "WHERE event_id=%s ORDER BY id", (EVENT_ID,))
    participants = cur.fetchall()
    cur.execute("SELECT c.id, c.participant_id, c.stage, c.lap_number, c.cumulative_s FROM checkpoints c "
                "JOIN participants p ON p.id=c.participant_id WHERE p.event_id=%s ORDER BY c.id", (EVENT_ID,))
    return {'participants': participants, 'checkpoints': cur.fetchall()}


def clear_results(conn) -> None:
    _check_demo(conn)
    cur = conn.cursor()
    cur.execute("DELETE c FROM checkpoints c JOIN participants p ON p.id=c.participant_id WHERE p.event_id=%s",
                (EVENT_ID,))
    cur.execute(f"UPDATE participants SET {', '.join(f'{c}=NULL' for c in STAGE_COLS)}, status=%s "
                "WHERE event_id=%s", (ACTIVE, EVENT_ID))
    conn.commit()


def _col_moment(p: dict, col: str):
    if p[col] is None:
        return None
    at = p[COL_MOMENT[col]]
    if at is None and col == 't1_s' and p['run1_s'] is not None:
        at = p['run1_s'] + p['t1_s']
    if at is None and col == 't2_s' and p['bike_s'] is not None:
        at = p['bike_s'] + p['t2_s']
    return at


def schedule(final: dict) -> list[tuple]:
    """События по возрастанию момента: (t_s, порядок, вид, данные). Вид: 'cp' — строка checkpoints,
    'col' — (pid, колонка, значение), 'status' — (pid, статус)."""
    ev = []
    last = {}
    for cp in final['checkpoints']:
        ev.append((cp['cumulative_s'], 0, 'cp', cp))
        last[cp['participant_id']] = max(last.get(cp['participant_id'], 0), cp['cumulative_s'])
    for p in final['participants']:
        for col in STAGE_COLS:
            at = _col_moment(p, col)
            if at is not None:
                ev.append((at, 1, 'col', (p['id'], col, p[col])))
                last[p['id']] = max(last.get(p['id'], 0), at)
    for p in final['participants']:
        if p['status'] == 'finished' and p['run2_s'] is not None:
            ev.append((p['run2_s'], 2, 'status', (p['id'], p['status'])))
        elif p['status'] != ACTIVE:
            ev.append((last.get(p['id'], 0), 2, 'status', (p['id'], p['status'])))
    ev.sort(key=lambda e: (e[0], e[1]))
    return ev


def _responses(bibs) -> dict:
    """Ответы эндпоинтов (обёртки — как в router); подключение уже подменено use_sandbox."""
    out = {'standings': {'standings': service.get_standings(EVENT_ID, None)},
           'standings?gender=M': {'standings': service.get_standings(EVENT_ID, 'M')},
           'standings?gender=F': {'standings': service.get_standings(EVENT_ID, 'F')}}
    for n in bibs:
        out[f'participant/{n}'] = service.get_participant(EVENT_ID, n)
    return out


def snapshot(bibs) -> dict:
    with use_sandbox(service, 'get_duathlon_connection', DEMO_DB):
        return _responses(bibs)


def replay(conn, final: dict, step_s: int = 30, on_step=None) -> dict:
    """Проиграть очищенное (clear_results) событие по итогу final."""
    _check_demo(conn)
    events = schedule(final)
    bibs = sorted(p['start_number'] for p in final['participants'])
    spec = spec_for(bibs)
    last_s = events[-1][0] if events else 0
    t_from, t_to = -MARGIN_S, math.ceil(last_s) + MARGIN_S
    ts = time_grid(t_from, t_to, step_s)
    state = {'i': 0}
    cur = conn.cursor()

    def advance(t):
        dirty = False
        while state['i'] < len(events) and events[state['i']][0] <= t:
            _, _, kind, d = events[state['i']]
            if kind == 'cp':
                cur.execute("INSERT INTO checkpoints (id, participant_id, stage, lap_number, cumulative_s) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (d['id'], d['participant_id'], d['stage'], d['lap_number'], d['cumulative_s']))
            elif kind == 'col':
                pid, col, val = d
                cur.execute(f"UPDATE participants SET {col}=%s WHERE id=%s", (val, pid))
            else:
                cur.execute("UPDATE participants SET status=%s WHERE id=%s", (d[1], d[0]))
            state['i'] += 1
            dirty = True
        conn.commit()
        return dirty

    with use_sandbox(service, 'get_duathlon_connection', DEMO_DB):
        initial, changes = record_steps(ts, advance, lambda: _responses(bibs), spec, on_step)
    if state['i'] != len(events):
        raise RuntimeError(f"не проиграно событий: {len(events) - state['i']}")
    ps = final['participants']
    bike0 = min((p['bike_start_s'] for p in ps if p['bike_start_s'] is not None), default=None)
    run20 = min((p['run2_start_s'] for p in ps if p['run2_start_s'] is not None), default=None)
    fin = max((p['run2_s'] for p in ps if p['run2_s'] is not None), default=last_s)
    meta = {
        'product': 'duathlon222_2026',
        'gun': GUN.isoformat(timespec='milliseconds'), 'gun_ms': int(GUN.timestamp() * 1000),
        'step_s': step_s, 't_from': t_from, 't_to': t_to,
        'steps': len(ts), 'steps_changed': len(changes),
        'marks': [{'label': 'Старт', 't_s': 0}, {'label': 'Вело', 't_s': bike0},
                  {'label': 'Бег 42 км', 't_s': run20}, {'label': 'Финиш', 't_s': fin}],
        'loop_start_s': (bike0 + run20) // 2 if bike0 is not None and run20 is not None else 0,
        'bibs': bibs,
        'spec': spec,
    }
    return {'meta': meta, 'initial': initial, 'changes': changes}
