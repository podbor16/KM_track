"""
Генератор интерактивного HTML-дашборда нагрузочного тестирования KM_track.
Показывает нагрузку на СЕРВЕР: пользователи, RPS, время ответа, SSE-соединения.

Использование:
    python reports/load/generate_dashboard.py --date 2026-05-18
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ─── Парсеры ─────────────────────────────────────────────────────────────────

def _extract_json_array(content: str, key: str) -> list:
    idx = content.find(f'"{key}":')
    if idx < 0:
        return []
    start = content.find("[", idx)
    depth = 0
    for i, ch in enumerate(content[start: start + 300_000]):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if depth == 0:
            try:
                return json.loads(content[start: start + i + 1])
            except Exception:
                return []
    return []


def parse_locust_html(path: Path) -> dict:
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8", errors="replace")
    history = _extract_json_array(content, "history")
    stats = _extract_json_array(content, "requests_statistics")
    meta = {}
    for key in ("duration", "start_time", "end_time"):
        m = re.search(rf'"{key}":\s*"([^"]+)"', content)
        if m:
            meta[key] = m.group(1)
    return {"history": history, "stats": stats, "meta": meta}


def parse_sse_stdout(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")

    def _int(pattern):
        m = re.search(pattern, text)
        return int(m.group(1)) if m else 0

    def _float(pattern):
        m = re.search(pattern, text)
        return float(m.group(1)) if m else 0.0

    progress = []
    for m in re.finditer(r"\[(\d+)s\]\s+done=(\d+)/(\d+)\s+held=(\d+)\s+active=(\d+)", text):
        progress.append({
            "t": int(m.group(1)),
            "done": int(m.group(2)),
            "total": int(m.group(3)),
            "held": int(m.group(4)),
            "active": int(m.group(5)),
        })

    passed_m = re.search(r"RESULT:\s+(PASSED|FAILED)", text)
    return {
        "vus": _int(r"Total VUs:\s+(\d+)"),
        "held": _int(r"Connected\+held:\s+(\d+)"),
        "no_connected": _int(r"No :connected:\s+(\d+)"),
        "errors": _int(r"Errors:\s+(\d+)"),
        "total_time": _float(r"Total time:\s+([\d.]+)s"),
        "passed": passed_m.group(1) == "PASSED" if passed_m else False,
        "progress": progress,
    }


# ─── Сборка данных ────────────────────────────────────────────────────────────

LEVEL_SPECS = {
    "smoke": {"http": 5,    "sse": 10},
    "L1":    {"http": 165,  "sse": 335},
    "L2":    {"http": 665,  "sse": 1335},
    "L3":    {"http": 1665, "sse": 3335},
    "L4":    {"http": 3335, "sse": 6665},
}

LEVEL_LABELS = {
    "smoke": "Smoke",
    "L1":    "L1 · 165 HTTP + 335 SSE",
    "L2":    "L2 · 665 HTTP + 1335 SSE",
    "L3":    "L3 · 1665 HTTP + 3335 SSE",
    "L4":    "L4 · 3335 HTTP + 6665 SSE",
}


def collect(report_dir: Path) -> list[dict]:
    levels = []
    for name in ["smoke", "L1", "L2", "L3", "L4"]:
        lf = report_dir / f"locust_{name}.html"
        if not lf.exists():
            continue
        # Предпочитаем *_v2 SSE файл (финальный прогон, если есть)
        sse_candidates = [
            report_dir / f"sse_{name}_v2_stdout.txt",
            report_dir / f"sse_{name}_stdout.txt",
        ]
        sse_path = next((p for p in sse_candidates if p.exists()), sse_candidates[-1])
        levels.append({
            "name": name,
            "label": LEVEL_LABELS.get(name, name),
            "spec": LEVEL_SPECS.get(name, {}),
            "locust": parse_locust_html(lf),
            "sse": parse_sse_stdout(sse_path),
        })
    return levels


# ─── HTML ─────────────────────────────────────────────────────────────────────

def generate(levels: list[dict], out: Path) -> None:
    json_payload = json.dumps(
        [{
            "name": lv["name"],
            "label": lv["label"],
            "spec": lv["spec"],
            "history": lv["locust"].get("history", []),
            "stats": lv["locust"].get("stats", []),
            "meta": lv["locust"].get("meta", {}),
            "sse": lv["sse"],
        } for lv in levels],
        ensure_ascii=False,
    )

    # Per-endpoint stats table HTML (строится на Python — чище)
    tables: dict[str, str] = {}
    for lv in levels:
        rows = ""
        stats = lv["locust"].get("stats", [])
        endpoint_stats = sorted(
            [s for s in stats if s.get("name") != "Aggregated"],
            key=lambda s: s.get("total_rps", 0), reverse=True,
        )
        for s in endpoint_stats:
            fails = s.get("num_failures", 0)
            fail_cls = "style='color:var(--red);font-weight:700'" if fails > 0 else ""
            rows += (
                f"<tr>"
                f"<td class='mono'>{s.get('method','GET')}</td>"
                f"<td class='mono small'>{s.get('name','')}</td>"
                f"<td>{s.get('num_requests',0):,}</td>"
                f"<td>{s.get('total_rps',0):.2f}</td>"
                f"<td>{s.get('avg_response_time',0):.0f}</td>"
                f"<td>{s.get('median_response_time',0)}</td>"
                f"<td>{s.get('response_time_percentile_0.95', 0) or s.get('response_time_percentile_0_95', 0)}</td>"
                f"<td {fail_cls}>{fails}</td>"
                f"</tr>"
            )
        # Aggregated row
        agg = next((s for s in stats if s.get("name") == "Aggregated"), {})
        if agg:
            rows += (
                f"<tr class='agg-row'>"
                f"<td colspan='2'>Всего</td>"
                f"<td>{agg.get('num_requests',0):,}</td>"
                f"<td>{agg.get('total_rps',0):.2f}</td>"
                f"<td>{agg.get('avg_response_time',0):.0f}</td>"
                f"<td>{agg.get('median_response_time',0)}</td>"
                f"<td>{agg.get('response_time_percentile_0.95', 0) or agg.get('response_time_percentile_0_95', 0)}</td>"
                f"<td>{agg.get('num_failures',0)}</td>"
                f"</tr>"
            )
        tables[lv["name"]] = rows

    tables_json = json.dumps(tables, ensure_ascii=False)

    html = _HTML.replace("__JSON_DATA__", json_payload).replace("__TABLES__", tables_json)
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard: {out}")


# ─── HTML шаблон ─────────────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KM_track — Нагрузочное тестирование сервера</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
<style>
:root{
  --bg:#0f1117;--surface:#181c27;--surface2:#1e2235;--border:#262b3d;
  --text:#e2e8f0;--muted:#7c87a0;--accent:#6366f1;
  --green:#22c55e;--red:#ef4444;--yellow:#f59e0b;--blue:#38bdf8;--purple:#a78bfa;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;min-height:100vh}

/* ── Header ── */
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 28px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.header-title{font-size:17px;font-weight:700}
.header-sub{color:var(--muted);font-size:11px;margin-top:2px}
.chip{background:rgba(99,102,241,.2);color:var(--accent);padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid rgba(99,102,241,.35)}

/* ── Tabs ── */
.tabs{display:flex;gap:2px;padding:0 28px;background:var(--surface);border-bottom:1px solid var(--border);overflow-x:auto}
.tab{padding:10px 20px;cursor:pointer;font-size:12px;font-weight:600;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap;transition:.15s}
.tab.active{color:var(--text);border-bottom-color:var(--accent)}
.tab:hover:not(.active){color:var(--text)}

/* ── Layout ── */
.page{display:none;padding:24px 28px;max-width:1400px;margin:0 auto}
.page.active{display:block}

/* ── KPI cards ── */
.kpi-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:20px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 16px}
.kpi .lbl{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px}
.kpi .val{font-size:22px;font-weight:800;line-height:1}
.kpi .sub{color:var(--muted);font-size:11px;margin-top:4px}
.kpi.pass .val{color:var(--green)}
.kpi.fail .val{color:var(--red)}
.kpi.warn .val{color:var(--yellow)}
.kpi.info .val{color:var(--blue)}
.kpi.purple .val{color:var(--purple)}

/* ── Charts ── */
.chart-controls{display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.chart-controls .hint{color:var(--muted);font-size:11px;flex:1}
.btn{background:var(--surface2);border:1px solid var(--border);color:var(--muted);padding:4px 12px;border-radius:5px;cursor:pointer;font-size:11px;font-weight:600;transition:.15s}
.btn:hover{color:var(--text);border-color:var(--muted)}
.btn.active{background:var(--accent);border-color:var(--accent);color:#fff}

.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}
@media(max-width:860px){.chart-grid{grid-template-columns:1fr}}
.chart-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px}
.chart-card h3{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}
.chart-card.wide{grid-column:1/-1}

/* ── Table ── */
.table-section{margin-bottom:24px}
.table-section h3{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}
.table-wrap{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden;overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{background:var(--surface2);color:var(--muted);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;padding:9px 12px;text-align:left;white-space:nowrap}
td{padding:8px 12px;border-top:1px solid var(--border);white-space:nowrap}
tr:hover td{background:rgba(99,102,241,.05)}
.agg-row td{background:var(--surface2);font-weight:700;border-top:2px solid var(--border)}
.mono{font-family:ui-monospace,monospace}
.small{font-size:11px}

/* ── SSE card ── */
.sse-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px 20px;margin-bottom:20px}
.sse-card h3{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
.sse-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px 20px}
.sse-row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)}
.sse-row:last-child{border-bottom:none}
.sse-row .k{color:var(--muted)}
.sse-row .v{font-weight:700}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:10px;font-weight:800;letter-spacing:.04em}
.badge.pass{background:rgba(34,197,94,.15);color:var(--green)}
.badge.fail{background:rgba(239,68,68,.15);color:var(--red)}

/* ── Server info ── */
.server-info{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 18px;margin-bottom:20px;display:flex;flex-wrap:wrap;gap:6px 32px}
.si-item .k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em}
.si-item .v{font-weight:700;font-size:13px;margin-top:1px}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="header-title">KM_track — Нагрузка на сервер</div>
    <div class="header-sub">Нагрузочное тестирование · 2026-05-18 · analytics.krasmarafon.ru</div>
  </div>
  <span class="chip">Отчёт</span>
</div>

<div class="tabs" id="tabs-root"></div>
<div id="pages-root"></div>

<script>
const DATA = __JSON_DATA__;
const TABLES = __TABLES__;

// ─── helpers ──────────────────────────────────────────────────────────────────
function el(tag, attrs={}, ...children){
  const e=document.createElement(tag);
  Object.entries(attrs).forEach(([k,v])=>{
    if(k==='class') e.className=v;
    else if(k==='html') e.innerHTML=v;
    else e.setAttribute(k,v);
  });
  children.forEach(c=>{ if(c) e.appendChild(typeof c==='string'?document.createTextNode(c):c); });
  return e;
}

function kpi(label,value,sub,cls='info'){
  return `<div class="kpi ${cls}"><div class="lbl">${label}</div><div class="val">${value}</div>${sub?`<div class="sub">${sub}</div>`:''}</div>`;
}

// ─── chart factory ────────────────────────────────────────────────────────────
const ZOOM_OPTS = {
  zoom:{ wheel:{enabled:true}, pinch:{enabled:true}, mode:'x' },
  pan:{ enabled:true, mode:'x' }
};
const SCALE_X = { ticks:{color:'#5a637a',maxTicksLimit:12,font:{size:10}}, grid:{color:'#1a1f30'} };
const SCALE_Y = (lbl) => ({
  ticks:{color:'#5a637a',font:{size:10}}, grid:{color:'#1a1f30'},
  title:{display:!!lbl,text:lbl||'',color:'#5a637a',font:{size:10}}, min:0
});

function mkChart(id, datasets, yLabel, extraOpts={}) {
  const ctx = document.getElementById(id);
  if (!ctx) return null;
  return new Chart(ctx, {
    type:'line',
    data:{ datasets },
    options:{
      responsive:true, animation:false,
      interaction:{ mode:'index', intersect:false },
      plugins:{
        legend:{ labels:{color:'#7c87a0',boxWidth:12,font:{size:10}} },
        zoom: ZOOM_OPTS,
        ...extraOpts.plugins
      },
      scales:{ x:SCALE_X, y:SCALE_Y(yLabel), ...(extraOpts.scales||{}) },
    }
  });
}

// Конвертируем ISO-строку в метку времени (ЧЧ:ММ:СС)
function isoToLabel(iso){
  const d=new Date(iso);
  return d.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
}

// ─── build pages ──────────────────────────────────────────────────────────────
const tabsRoot = document.getElementById('tabs-root');
const pagesRoot = document.getElementById('pages-root');
const charts = {};  // {levelName: {id: Chart}}

DATA.forEach((lv, idx) => {
  const active = idx===0;
  // Tab
  const tab = el('div',{class:`tab${active?' active':''}`, 'data-name':lv.name}, lv.label);
  tab.addEventListener('click', ()=>switchTo(lv.name));
  tabsRoot.appendChild(tab);

  // ── Page ──
  const page = el('div',{class:`page${active?' active':''}`, id:`page-${lv.name}`});

  // Server info strip
  const spec = lv.spec || {};
  page.innerHTML += `
    <div class="server-info">
      <div class="si-item"><div class="k">Сервер</div><div class="v">VPS · 1 CPU · 960 MB RAM</div></div>
      <div class="si-item"><div class="k">Приложение</div><div class="v">FastAPI · 2 workers · uvicorn</div></div>
      <div class="si-item"><div class="k">HTTP пользователей</div><div class="v">${spec.http||'—'}</div></div>
      <div class="si-item"><div class="k">SSE соединений</div><div class="v">${spec.sse||'—'}</div></div>
      <div class="si-item"><div class="k">Итого на сервере</div><div class="v">${(spec.http||0)+(spec.sse||0)}</div></div>
      <div class="si-item"><div class="k">Длительность</div><div class="v">${lv.meta?.duration||'—'}</div></div>
    </div>`;

  // KPIs
  const h = lv.history || [];
  const stats = lv.stats || [];
  const agg = stats.find(s=>s.name==='Aggregated')||{};
  const sse = lv.sse||{};

  const maxUsers = h.reduce((m,r)=>Math.max(m,r.user_count?.[1]||0),0);
  const peakRps  = h.reduce((m,r)=>Math.max(m,r.current_rps?.[1]||0),0).toFixed(1);
  const totalReq = agg.num_requests||0;
  const totalFail= agg.num_failures||0;
  const avgRt    = (agg.avg_response_time||0).toFixed(0);
  const p95      = agg['response_time_percentile_0.95']||agg.response_time_percentile_0_95||0;
  const errPct   = totalReq ? (totalFail/totalReq*100).toFixed(2) : '0.00';
  const httpOk   = parseFloat(errPct) < 1;
  const ssePct   = sse.vus ? ((sse.held||0)/sse.vus*100).toFixed(0) : null;
  const sseOk    = sse.passed;
  const overall  = httpOk && (ssePct===null || sseOk);

  page.innerHTML += `<div class="kpi-row">
    ${kpi('HTTP VUs (пик)', maxUsers, 'одновременно', 'info')}
    ${kpi('SSE соединений', sse.vus||'—', 'VU', 'purple')}
    ${kpi('Всего VUs', (maxUsers+(sse.vus||0))||'—', 'HTTP + SSE', 'info')}
    ${kpi('Пик RPS', peakRps, 'запросов/сек', 'info')}
    ${kpi('Всего запросов', totalReq.toLocaleString('ru'), lv.meta?.duration||'')}
    ${kpi('Среднее время', avgRt+' мс', `p95 = ${p95} мс`, avgRt>3000?'warn':'info')}
    ${kpi('HTTP ошибки', errPct+'%', `${totalFail} из ${totalReq}`, httpOk?'pass':'fail')}
    ${ssePct!==null ? kpi('SSE connected', ssePct+'%', `${sse.held}/${sse.vus} VU`, sseOk?'pass':'fail') : ''}
    ${kpi('ИТОГ', overall?'PASS':'FAIL', lv.name, overall?'pass':'fail')}
  </div>`;

  // ── Controls ──
  page.innerHTML += `
    <div class="chart-controls">
      <span class="hint">🖱 Колесо мыши — масштаб · Перетащить — сдвиг по времени</span>
      <button class="btn active" onclick="setRange('${lv.name}','all',this)">Весь тест</button>
      <button class="btn" onclick="setRange('${lv.name}','ramp',this)">Разгон</button>
      <button class="btn" onclick="setRange('${lv.name}','steady',this)">Устойчивая нагрузка</button>
      <button class="btn" onclick="resetZoom('${lv.name}')">↺ Сброс</button>
    </div>`;

  // ── Charts ──
  page.innerHTML += `
    <div class="chart-grid">
      <div class="chart-card wide">
        <h3>Нагрузка на сервер: HTTP пользователи + SSE соединения</h3>
        <canvas id="c-load-${lv.name}" height="130"></canvas>
      </div>
      <div class="chart-card">
        <h3>Запросы в секунду (RPS)</h3>
        <canvas id="c-rps-${lv.name}" height="160"></canvas>
      </div>
      <div class="chart-card">
        <h3>Время ответа сервера</h3>
        <canvas id="c-rt-${lv.name}" height="160"></canvas>
      </div>
      ${sse.progress?.length ? `
      <div class="chart-card wide">
        <h3>SSE соединения на сервере — динамика за тест</h3>
        <canvas id="c-sse-${lv.name}" height="130"></canvas>
      </div>` : ''}
    </div>`;

  // ── Per-endpoint table ──
  page.innerHTML += `
    <div class="table-section">
      <h3>Нагрузка по endpoint'ам сервера</h3>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Метод</th><th>Endpoint</th><th>Запросов</th><th>RPS</th>
            <th>Среднее (мс)</th><th>Медиана (мс)</th><th>p95 (мс)</th><th>Ошибки</th>
          </tr></thead>
          <tbody>${TABLES[lv.name]||''}</tbody>
        </table>
      </div>
    </div>`;

  // ── SSE summary ──
  if (sse.vus) {
    const badge = sseOk
      ? '<span class="badge pass">PASS</span>'
      : '<span class="badge fail">FAIL</span>';
    page.innerHTML += `
      <div class="sse-card">
        <h3>SSE нагрузка на сервер &nbsp;${badge}</h3>
        <div class="sse-grid">
          <div>
            <div class="sse-row"><span class="k">VUs (подключений)</span><span class="v">${sse.vus}</span></div>
            <div class="sse-row"><span class="k">Удержали соединение</span><span class="v">${sse.held} (${ssePct}%)</span></div>
            <div class="sse-row"><span class="k">Не получили :connected</span><span class="v">${sse.no_connected}</span></div>
          </div>
          <div>
            <div class="sse-row"><span class="k">Ошибки соединения</span><span class="v">${sse.errors}</span></div>
            <div class="sse-row"><span class="k">Время теста SSE</span><span class="v">${sse.total_time?.toFixed(0)||'—'}s</span></div>
            <div class="sse-row"><span class="k">Порог</span><span class="v">≥95% VUs</span></div>
          </div>
        </div>
      </div>`;
  }

  pagesRoot.appendChild(page);
});

// ─── Chart init (после render DOM) ───────────────────────────────────────────
function initCharts(lv) {
  const name = lv.name;
  charts[name] = {};
  const h = lv.history || [];
  if (!h.length) return;

  const xLabels = h.map(r => isoToLabel(r.time));

  // 1. Нагрузка на сервер: HTTP users (из locust) + SSE connections (из SSE progress)
  // SSE прогресс привязан к секундам от старта теста, а locust — к реальному времени.
  // Для объединения: interpolate SSE active на метки времени locust.
  const sseProgress = lv.sse?.progress || [];
  let sseActive = [];
  if (sseProgress.length && h.length) {
    const testDuration = lv.sse?.total_time || 500;
    const startIdx = 0;
    sseActive = h.map((_, i) => {
      const elapsed = (i / h.length) * testDuration;
      // Find nearest SSE progress point
      const pt = sseProgress.reduce((best, p) =>
        Math.abs(p.t - elapsed) < Math.abs(best.t - elapsed) ? p : best,
        sseProgress[0]
      );
      return pt ? pt.active : 0;
    });
  }
  const httpUsers = h.map(r => r.user_count?.[1] || 0);
  const sseDataset = sseActive.length ? [{
    label: 'SSE соединений (на сервере)',
    data: sseActive,
    borderColor:'#a78bfa', backgroundColor:'rgba(167,139,250,.08)', fill:true, tension:.4, pointRadius:0, borderWidth:2,
  }] : [];

  charts[name].load = mkChart(`c-load-${name}`, [
    { label:'HTTP пользователи', data:httpUsers, borderColor:'#6366f1', backgroundColor:'rgba(99,102,241,.1)', fill:true, tension:.4, pointRadius:0, borderWidth:2 },
    ...sseDataset,
  ], 'Пользователей / соединений', { plugins:{ zoom:ZOOM_OPTS } });
  if (charts[name].load) charts[name].load._xLabels = xLabels, charts[name].load.data.labels = xLabels, charts[name].load.update('none');

  // 2. RPS + ошибки
  charts[name].rps = mkChart(`c-rps-${name}`, [
    { label:'RPS (успешные)', data:h.map(r=>+(r.current_rps?.[1]||0).toFixed(2)), borderColor:'#22c55e', backgroundColor:'rgba(34,197,94,.08)', fill:true, tension:.3, pointRadius:0 },
    { label:'Ошибок/с', data:h.map(r=>+(r.current_fail_per_sec?.[1]||0).toFixed(3)), borderColor:'#ef4444', backgroundColor:'rgba(239,68,68,.08)', fill:true, tension:.3, pointRadius:0 },
  ], 'Запросов / сек');
  if (charts[name].rps) charts[name].rps.data.labels=xLabels, charts[name].rps.update('none');

  // 3. Время ответа
  charts[name].rt = mkChart(`c-rt-${name}`, [
    { label:'p50 (медиана)', data:h.map(r=>r['response_time_percentile_0.5']?.[1]||0), borderColor:'#38bdf8', tension:.3, pointRadius:0, borderWidth:2 },
    { label:'p95', data:h.map(r=>r['response_time_percentile_0.95']?.[1]||0), borderColor:'#f59e0b', tension:.3, pointRadius:0, borderWidth:2, borderDash:[5,3] },
    { label:'Среднее', data:h.map(r=>+(r.total_avg_response_time?.[1]||0).toFixed(0)), borderColor:'#a78bfa', tension:.3, pointRadius:0, borderWidth:1.5, borderDash:[2,2] },
  ], 'Время ответа (мс)');
  if (charts[name].rt) charts[name].rt.data.labels=xLabels, charts[name].rt.update('none');

  // 4. SSE progress
  const sp = lv.sse?.progress||[];
  if (sp.length && document.getElementById(`c-sse-${name}`)) {
    const spLabels = sp.map(p=>p.t+'s');
    charts[name].sse = mkChart(`c-sse-${name}`, [
      { label:'Активных (подключаются)', data:sp.map(p=>p.active), borderColor:'#6366f1', fill:false, tension:.3, pointRadius:4, pointHoverRadius:6 },
      { label:'Удерживают соединение', data:sp.map(p=>p.held), borderColor:'#22c55e', backgroundColor:'rgba(34,197,94,.1)', fill:true, tension:.3, pointRadius:4, pointHoverRadius:6 },
    ], 'SSE соединений', { plugins:{zoom:undefined} });
    if (charts[name].sse) {
      charts[name].sse.data.labels = spLabels;
      charts[name].sse.options.scales.y.max = lv.sse.vus;
      charts[name].sse.update('none');
    }
  }
}

// Init all on load
window.addEventListener('DOMContentLoaded', () => {
  DATA.forEach(lv => {
    try { initCharts(lv); } catch(e) { console.error(lv.name, e); }
  });
});

// ─── Switching ────────────────────────────────────────────────────────────────
function switchTo(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t.dataset.name===name));
  document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active', p.id===`page-${name}`));
}

// ─── Zoom helpers ─────────────────────────────────────────────────────────────
function resetZoom(name){
  Object.values(charts[name]||{}).forEach(c=>{ try{c.resetZoom();}catch(e){} });
  document.querySelectorAll(`#page-${name} .btn`).forEach(b=>b.classList.remove('active'));
  document.querySelector(`#page-${name} .btn:first-of-type`).classList.add('active');
}

function setRange(name, range, btn){
  const cs = charts[name]||{};
  const lv = DATA.find(d=>d.name===name);
  const h = lv?.history||[];
  if (!h.length) return;

  const n = h.length;
  let minIdx=0, maxIdx=n-1;
  if (range==='ramp'){
    // Найдём где user_count достигает максимума
    const maxU = Math.max(...h.map(r=>r.user_count?.[1]||0));
    const peakIdx = h.findIndex(r=>(r.user_count?.[1]||0)>=maxU*0.95);
    maxIdx = peakIdx > 0 ? Math.min(peakIdx+5, n-1) : Math.floor(n*0.25);
    minIdx = 0;
  } else if (range==='steady'){
    const maxU = Math.max(...h.map(r=>r.user_count?.[1]||0));
    const peakIdx = h.findIndex(r=>(r.user_count?.[1]||0)>=maxU*0.95);
    minIdx = peakIdx > 0 ? Math.max(0, peakIdx-2) : Math.floor(n*0.2);
    // Конец — до начала спада (последние ~10% когда тест завершается)
    const endIdx = h.map((r,i)=>[i,r.user_count?.[1]||0]).reverse().find(([i,u])=>u>maxU*0.5);
    maxIdx = endIdx ? endIdx[0] : n-1;
  }

  // Применяем к charts с xLabels
  Object.values(cs).forEach(c=>{
    if (!c || !c.data?.labels) return;
    const lb = c.data.labels;
    try {
      c.zoomScale('x', {min: lb[minIdx]||lb[0], max: lb[maxIdx]||lb[lb.length-1]});
    } catch(e) {}
  });

  document.querySelectorAll(`#page-${name} .btn`).forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
}
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-05-18")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    report_dir = Path(__file__).parent / args.date
    if not report_dir.exists():
        print(f"ERROR: {report_dir} not found", file=sys.stderr)
        sys.exit(1)

    levels = collect(report_dir)
    if not levels:
        print("ERROR: no locust_*.html found", file=sys.stderr)
        sys.exit(1)

    print(f"Levels: {[lv['name'] for lv in levels]}")
    out = Path(args.out) if args.out else report_dir / "dashboard.html"
    generate(levels, out)


if __name__ == "__main__":
    main()
