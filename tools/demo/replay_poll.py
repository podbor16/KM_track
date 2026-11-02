"""Общий формат записи poll-продуктов с несколькими эндпоинтами (Триатлет, Дуатлон).

Запись: {'meta': {..., 'spec': {ep: спец}}, 'initial': {ep: ответ}, 'changes': [{'t_s', 'ep': {ep: узел}}]}.

Спец ответа (как сравнивать):
  None                                 — значение целиком;
  {'fields': {имя: спец}}              — объект: перечисленные поля по своим спецам, прочие целиком;
  {'key': [поля], 'item': спец|None}   — список объектов с ключом элемента "v1:v2" (str).
Узел изменения:
  {'=': значение}                      — замена целиком;
  {'f': {поле: узел}, 'x': [поля]}     — объект: изменённые/новые поля, удалённые поля;
  {'u': {ключ: узел}, 'a': [элементы], 'x': [ключи], 'o': [ключи]} — список: изменённые элементы,
                                         новые (целиком, дописываются в конец), удалённые; полный порядок
                                         ключей — только если он не равен «прежние без удалённых + новые».
Узлы не '=' возникают только там, где их задаёт спец, поэтому apply_change различает их по спецу.
"""
import copy
import json

from fastapi.encoders import jsonable_encoder


def normalize(value):
    """Ответ эндпоинта так, как его отдаёт FastAPI (jsonable_encoder → JSON) и читает браузер."""
    return json.loads(json.dumps(jsonable_encoder(value), ensure_ascii=False))


def item_key(item: dict, fields: list) -> str:
    return ':'.join(str(item[f]) for f in fields)


def diff(prev, cur, spec=None):
    """Узел изменения prev→cur по спецу или None, если не изменилось."""
    if prev == cur:
        return None
    if spec and 'fields' in spec and isinstance(prev, dict) and isinstance(cur, dict):
        sub = spec['fields']
        f = {}
        for k, v in cur.items():
            if k not in prev:
                f[k] = {'=': v}
            else:
                node = diff(prev[k], v, sub.get(k))
                if node is not None:
                    f[k] = node
        node = {}
        if f:
            node['f'] = f
        gone = [k for k in prev if k not in cur]
        if gone:
            node['x'] = gone
        return node
    if spec and 'key' in spec and isinstance(prev, list) and isinstance(cur, list):
        fields, item_spec = spec['key'], spec.get('item')
        old = {item_key(r, fields): r for r in prev}
        u, a, order = {}, [], []
        for r in cur:
            k = item_key(r, fields)
            order.append(k)
            if k not in old:
                a.append(r)
            else:
                node = diff(old[k], r, item_spec)
                if node is not None:
                    u[k] = node
        keys = set(order)
        gone = [k for k in old if k not in keys]
        implied = [k for k in old if k in keys] + [item_key(r, fields) for r in a]
        node = {}
        if u:
            node['u'] = u
        if a:
            node['a'] = a
        if gone:
            node['x'] = gone
        if order != implied:
            node['o'] = order
        return node
    return {'=': cur}


def apply_change(value, node, spec=None):
    """value + узел → новое значение (value не меняется)."""
    if '=' in node:
        return copy.deepcopy(node['='])
    if 'key' in spec:
        fields, item_spec = spec['key'], spec.get('item')
        by_key = {item_key(r, fields): r for r in value}
        for k in node.get('x', []):
            by_key.pop(k, None)
        for k, sub in node.get('u', {}).items():
            by_key[k] = apply_change(by_key[k], sub, item_spec)
        order = [k for k in (item_key(r, fields) for r in value) if k in by_key]
        for r in node.get('a', []):
            k = item_key(r, fields)
            by_key[k] = copy.deepcopy(r)
            order.append(k)
        return [by_key[k] for k in node.get('o') or order]
    sub = spec['fields']
    out = dict(value)
    for k in node.get('x', []):
        out.pop(k, None)
    for k, ch in node.get('f', {}).items():
        out[k] = apply_change(out.get(k), ch, sub.get(k))
    return out


def state_at(rec: dict, t: float) -> dict:
    """Python-эталон браузера: {ep: ответ} = initial + все changes с t_s ≤ t."""
    spec = rec['meta']['spec']
    state = copy.deepcopy(rec['initial'])
    for ch in rec['changes']:
        if ch['t_s'] > t:
            break
        for ep, node in ch['ep'].items():
            state[ep] = apply_change(state.get(ep), node, spec.get(ep))
    return state


def record_steps(ts, advance, snapshot, spec: dict, on_step=None) -> tuple[dict, list]:
    """Цикл записи: на шаге t advance(t) -> bool «что-то записано»; snapshot() -> {ep: ответ}
    (только на первом шаге и на шагах с записью). Возвращает (initial, changes)."""
    initial, prev, changes = None, None, []
    for t in ts:
        dirty = advance(t)
        if initial is not None and not dirty:
            continue
        cur = {ep: normalize(v) for ep, v in snapshot().items()}
        if initial is None:
            initial = cur
        else:
            ep_ch = {}
            for ep, v in cur.items():
                node = diff(prev.get(ep), v, spec.get(ep))
                if node is not None:
                    ep_ch[ep] = node
            if ep_ch:
                changes.append({'t_s': t, 'ep': ep_ch})
        prev = cur
        if on_step:
            on_step(t)
    return initial, changes


def time_grid(t_from: int, t_to: int, step_s: int) -> list[int]:
    """Шаги t_from, t_from+step, …, и последним — ровно t_to."""
    return list(range(t_from, t_to, step_s)) + [t_to]
