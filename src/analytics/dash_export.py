"""
Экспорт вкладки дашборда DataLens «Красмарафон — Аналитика» в Excel (вариант B, решение
пользователя 2026-10-26): данные берутся из самого DataLens тем же API, что у встроенного iframe
(`/charts/embeds/api/entry` — устройство дашборда, `/charts/embeds/api/run` — данные чарта и
варианты селектора), с нашим токеном встраивания. API не документирован — при его смене упадёт
выгрузка, дашборд в /admin продолжит работать.

Excel: лист «Сводка» (вкладка, фильтры, время, показатели-индикаторы), далее лист на каждую
таблицу и график в порядке раскладки вкладки; у графика — таблица данных и нативный график Excel.
"""

import io
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime

from src.config import settings
from src.core.datalens import make_embed_token

DL = "https://datalens.ru"
DASH_TITLE = "Красмарафон — Аналитика"
EXPORT_TABS = ("XbA",)          # «Динамика регистраций»; остальные — после согласования пилота
ENTRY_TTL = 600
RETRY_CODES = (403, 424, 429, 500, 502, 503, 504)
RETRY_DELAY = 1.5
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

_entry_cache = {"ts": 0.0, "entry": None}


def _embed():
    cfg = (settings.DATALENS_EMBEDS or [None])[0]
    if not cfg or not settings.DATALENS_KEY_SECRET:
        raise ValueError("DataLens не настроен (DATALENS_EMBEDS, DATALENS_KEY_SECRET)")
    return cfg


def _call(path, body=None, tab_id=None):
    cfg = _embed()
    # заголовки — как у встроенного iframe; с «Python-urllib» DataLens отвечает 403 (проверено 2026-10-26)
    headers = {"accept": "application/json", "user-agent": UA,
               "x-dl-embed-token": make_embed_token(cfg["id"], settings.DATALENS_KEY_SECRET)}
    if body is not None:
        headers.update({"content-type": "application/json", "x-dl-display-mode": "secure-embedded",
                        "x-dl-user-timezone": "Asia/Krasnoyarsk"})
    entry_id = (_entry_cache["entry"] or {}).get("entryId")
    if tab_id and entry_id:
        headers["x-dash-info"] = f"dashId={entry_id}&dashTabId={tab_id}"
    req = urllib.request.Request(DL + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST", headers=headers)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # DataLens изредка отвечает 424/5xx на тот же запрос, что через секунду проходит
            if attempt or e.code not in RETRY_CODES:
                raise
            time.sleep(RETRY_DELAY)


def get_entry():
    """Устройство дашборда (вкладки, виджеты, селекторы, раскладка), кеш 10 мин."""
    if _entry_cache["entry"] is None or time.time() - _entry_cache["ts"] > ENTRY_TTL:
        _entry_cache["entry"] = _call("/charts/embeds/api/entry")
        _entry_cache["ts"] = time.time()
    return _entry_cache["entry"]


def _tab(tab_id):
    for t in get_entry().get("data", {}).get("tabs", []):
        if t.get("id") == tab_id:
            return t
    raise ValueError(f"нет вкладки {tab_id}")


def tabs():
    return [{"id": t["id"], "title": t.get("title", ""), "export": t["id"] in EXPORT_TABS}
            for t in get_entry().get("data", {}).get("tabs", [])]


def _ordered_items(tab):
    pos = {l.get("i"): (l.get("y", 0), l.get("x", 0)) for l in tab.get("layout", [])}
    return sorted(tab.get("items", []), key=lambda it: pos.get(it.get("id"), (10 ** 6, 0)))


def charts(tab_id):
    """[(chart_id, заголовок)] в порядке раскладки (сверху вниз, слева направо)."""
    out = []
    for it in _ordered_items(_tab(tab_id)):
        if it.get("type") == "widget":
            out += [(t["chartId"], t.get("title", "")) for t in it.get("data", {}).get("tabs", []) if t.get("chartId")]
    return out


def _controls(tab_id):
    for it in _ordered_items(_tab(tab_id)):
        if it.get("type") in ("control", "group_control"):
            d = it.get("data", {})
            for g in (d.get("group") or [d]):
                yield it.get("id"), g


def _filter_titles(tab_id):
    return {g.get("source", {}).get("datasetFieldId"): g.get("title", "") for _, g in _controls(tab_id)}


LEAD_FIELDS = ("event_year", "event_name", "event_distance")


def _lead_field(param):
    """event_name_2iel → event_name: параметр DataLens = поле датасета km_leads + суффикс."""
    base = (param or "").rsplit("_", 1)[0]
    return base if base in LEAD_FIELDS else None


def filters(tab_id):
    """Селекторы вкладки: [{param, title, multiselect, options}]. Варианты — из таблицы leads (датасет
    km_leads построен на ней): запрос вариантов селектора у DataLens из-вне отвечает 403."""
    from src.analytics.db_connection_optimized import get_pooled_connection

    out = []
    conn = get_pooled_connection()
    try:
        cur = conn.cursor() if conn else None
        for _, g in _controls(tab_id):
            src = g.get("source", {})
            param, field = src.get("datasetFieldId"), _lead_field(src.get("datasetFieldId"))
            options = []
            if cur and field:
                cur.execute(f"SELECT DISTINCT {field} FROM leads WHERE {field} IS NOT NULL AND {field} <> '' "
                            f"ORDER BY {field} {'DESC' if field == 'event_year' else 'ASC'}")
                options = [str(r[0]) for r in cur.fetchall()]
            out.append({"param": param, "title": g.get("title", ""), "multiselect": bool(src.get("multiselectable")),
                        "options": options})
    finally:
        if conn:
            conn.close()
    return out


def run_chart(chart_id, params, tab_id):
    return _call("/charts/embeds/api/run", {"id": chart_id, "params": params,
                                            "responseOptions": {"includeConfig": True, "includeLogs": False},
                                            "pageUrl": DL}, tab_id)


def normalize(resp):
    """Ответ /api/run → {'kind': 'metric'|'table'|'graph', ...}; неизвестный вид — None."""
    data = resp.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict) and "content" in data[0]:
        cur = (data[0].get("content") or {}).get("current") or {}
        return {"kind": "metric", "label": data[0].get("title", ""), "value": cur.get("value")}
    if isinstance(data, dict) and "head" in data:
        cols = [h.get("name") or h.get("id") or "" for h in data.get("head", [])]
        rows = [[c.get("value") for c in r.get("cells", [])] for r in data.get("rows", [])]
        return {"kind": "table", "columns": cols, "rows": rows}
    if isinstance(data, dict) and isinstance(data.get("series"), dict):
        cats = (data.get("xAxis") or {}).get("categories") or []
        series = []
        for s in data["series"].get("data", []):
            vals = [None] * len(cats)
            for p in s.get("data", []):
                x = p.get("x")
                if isinstance(x, int) and 0 <= x < len(cats):
                    vals[x] = p.get("y")
            series.append({"name": str(s.get("name", "")), "type": s.get("type", ""), "values": vals})
        kind = "bar" if any(s["type"].startswith("bar") for s in series) else "line"
        return {"kind": "graph", "chart": kind, "categories": cats, "series": series}
    return None


def _sheet_title(title, used):
    base = re.sub(r"[\[\]:*?/\\]", " ", title).strip()[:31] or "Лист"
    name, k = base, 2
    while name in used:
        name = f"{base[:28]} {k}"
        k += 1
    used.add(name)
    return name


def build_xlsx(tab_id, params, now=None):
    """Excel вкладки с фильтрами params ({param: '' | значение | [значения]}) -> (bytes, имя файла)."""
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.styles import Font

    if tab_id not in EXPORT_TABS:
        raise ValueError("экспорт этой вкладки ещё не включён")
    now = now or datetime.now()
    tab = _tab(tab_id)
    # каждый селектор вкладки передаём явно: «» — «все», иначе чарт взял бы дефолт селектора
    params = {p: params.get(p, "") for p in _filter_titles(tab_id)}
    bold = Font(bold=True)
    wb = Workbook()
    summary = wb.active
    summary.title = "Сводка"
    used = {"Сводка"}
    summary.append([f"{DASH_TITLE}: {tab.get('title', '')}"])
    summary["A1"].font = Font(bold=True, size=14)
    summary.append([f"Выгружено: {now:%d.%m.%Y %H:%M}"])
    summary.append([])
    summary.append(["Фильтр", "Значение"])
    for c in summary[summary.max_row]:
        c.font = bold
    for param, title in _filter_titles(tab_id).items():
        v = params.get(param)
        summary.append([title, ", ".join(v) if isinstance(v, list) else (v or "все")])
    metrics, skipped = [], []
    for chart_id, title in charts(tab_id):
        n = normalize(run_chart(chart_id, params, tab_id))
        if n is None:
            skipped.append(title)
            continue
        if n["kind"] == "metric":
            metrics.append((title, n["label"], n["value"]))
            continue
        ws = wb.create_sheet(_sheet_title(title, used))
        ws.append([title])
        ws["A1"].font = Font(bold=True, size=12)
        if n["kind"] == "table":
            ws.append(n["columns"])
            for r in n["rows"]:
                ws.append(r)
        else:
            ws.append(["", *[s["name"] for s in n["series"]]])
            for i, cat in enumerate(n["categories"]):
                ws.append([cat, *[s["values"][i] for s in n["series"]]])
            ch = BarChart() if n["chart"] == "bar" else LineChart()
            ch.title, ch.height, ch.width = title, 10, 24
            last = 2 + len(n["categories"])
            ch.add_data(Reference(ws, min_col=2, max_col=1 + len(n["series"]), min_row=2, max_row=last), titles_from_data=True)
            ch.set_categories(Reference(ws, min_col=1, min_row=3, max_row=last))
            ws.add_chart(ch, f"{chr(ord('A') + min(len(n['series']) + 2, 20))}2")
        for c in ws[2]:
            c.font = bold
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = max(10, min(40, max(len(str(c.value or "")) for c in col[1:]) + 2))
    if metrics:
        summary.append([])
        summary.append(["Показатель", "", "Значение"])
        for c in summary[summary.max_row]:
            c.font = bold
        for row in metrics:
            summary.append(list(row))
    if skipped:
        summary.append([])
        summary.append(["Не выгружены (неизвестный вид чарта): " + ", ".join(skipped)])
    for col, w in (("A", 34), ("B", 30), ("C", 16)):
        summary.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    safe = re.sub(r"[^\w\- ]", "", tab.get("title", tab_id)).strip().replace(" ", "_")
    return buf.getvalue(), f"analytics_{safe}_{now:%Y%m%d-%H%M}.xlsx"
