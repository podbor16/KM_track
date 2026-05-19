"""
Деплоит кастомный HTML-дашборд Race Day на VPS в директорию Netdata web.
Дашборд доступен по адресу: https://analytics.krasmarafon.ru/netdata/race-day.html

Использует Netdata REST API v1 + Chart.js (CDN) — совместимо с Netdata v2.x,
где классический dashboard.js отсутствует.

Шаги:
  1. Найти webroot Netdata динамически
  2. Загрузить race-day.html
  3. Установить права 644
  4. Smoke-check: curl http://127.0.0.1:19999/race-day.html → 200
"""
import io
import sys
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = VPS_HOST

# ---------------------------------------------------------------------------
# HTML-контент дашборда
# Использует /netdata/api/v1/data (через nginx-прокси) + Chart.js CDN.
# API-путь /netdata/api/v1/data совпадает с расположением дашборда — браузер
# передаёт basic-auth автоматически в рамках той же авторизованной сессии.
# ---------------------------------------------------------------------------

HTML_CONTENT = """\
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Race Day — KM_track</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
    <style>
        * { box-sizing: border-box; }
        body { background: #1a1a2e; color: #eee; font-family: sans-serif; padding: 20px; margin: 0; }
        h1 { color: #00d4ff; margin-bottom: 4px; font-size: 1.4em; }
        .subtitle { color: #888; margin-bottom: 20px; font-size: 0.9em; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .chart-box { background: #16213e; border-radius: 8px; padding: 12px; }
        .chart-title { color: #aaa; font-size: 0.85em; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }
        .chart-value { color: #00d4ff; font-size: 1.1em; font-weight: bold; margin-bottom: 4px; }
        canvas { width: 100% !important; }
        .footer { margin-top: 16px; color: #555; font-size: 0.8em; }
        .footer a { color: #00d4ff; }
        @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <h1>Race Day Dashboard</h1>
    <div class="subtitle">KM_track · analytics.krasmarafon.ru · Live monitoring</div>
    <div class="grid">
        <div class="chart-box">
            <div class="chart-title">CPU Utilization</div>
            <div class="chart-value" id="val-cpu">—</div>
            <canvas id="chart-cpu" height="120"></canvas>
        </div>
        <div class="chart-box">
            <div class="chart-title">RAM Used (MiB)</div>
            <div class="chart-value" id="val-ram">—</div>
            <canvas id="chart-ram" height="120"></canvas>
        </div>
        <div class="chart-box">
            <div class="chart-title">TCP Sockets (SSE connections)</div>
            <div class="chart-value" id="val-sock">—</div>
            <canvas id="chart-sock" height="120"></canvas>
        </div>
        <div class="chart-box">
            <div class="chart-title">nginx Requests/s</div>
            <div class="chart-value" id="val-nginx">—</div>
            <canvas id="chart-nginx" height="120"></canvas>
        </div>
        <div class="chart-box">
            <div class="chart-title">Redis Commands/s</div>
            <div class="chart-value" id="val-redis">—</div>
            <canvas id="chart-redis" height="120"></canvas>
        </div>
        <div class="chart-box">
            <div class="chart-title">km_track RAM (MiB)</div>
            <div class="chart-value" id="val-km">—</div>
            <canvas id="chart-km" height="120"></canvas>
        </div>
    </div>
    <div class="footer">
        Auto-refreshes every 5s · Last 5 minutes shown ·
        <a href="/netdata/">Full Netdata</a>
    </div>

<script>
// Netdata REST API base path (same origin as the dashboard, goes through nginx proxy)
const API = '/netdata/api/v1/data';

// Chart definitions: { canvasId, valueId, chart, dimensions, label, color }
const CHARTS = [
    { id: 'cpu',   chart: 'system.cpu',           dims: null,    label: 'CPU %',      color: '#e74c3c' },
    { id: 'ram',   chart: 'system.ram',            dims: 'used',  label: 'RAM MiB',    color: '#3498db' },
    { id: 'sock',  chart: 'ip.sockstat_sockets',   dims: null,    label: 'Sockets',    color: '#2ecc71' },
    { id: 'nginx', chart: 'web_log_nginx.requests', dims: null,   label: 'req/s',      color: '#f39c12' },
    { id: 'redis', chart: 'redis_local.commands',  dims: null,    label: 'cmd/s',      color: '#9b59b6' },
    { id: 'km',    chart: 'systemd_km_track.mem',  dims: 'anon',  label: 'km_track MiB', color: '#1abc9c' },
];

const instances = {};

Chart.defaults.color = '#999';
Chart.defaults.borderColor = '#2a2a4a';

function mkChart(id, label, color) {
    const ctx = document.getElementById('chart-' + id).getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label,
                data: [],
                borderColor: color,
                backgroundColor: color + '22',
                borderWidth: 1.5,
                pointRadius: 0,
                fill: true,
                tension: 0.3,
            }]
        },
        options: {
            animation: false,
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { display: false },
                y: { grid: { color: '#2a2a4a' }, ticks: { color: '#777', maxTicksLimit: 4 } }
            }
        }
    });
}

async function fetchChart(def) {
    let url = `${API}?chart=${def.chart}&after=-300&points=60&format=json`;
    if (def.dims) url += `&dimensions=${def.dims}`;
    try {
        const r = await fetch(url, { credentials: 'include' });
        if (!r.ok) return;
        const d = await r.json();
        const labels = d.labels;          // ['time', 'dim1', ...]
        const data   = d.data;            // [[timestamp, v1, ...], ...]
        if (!data || data.length === 0) return;

        // Sum all dimension values (skip index 0 = timestamp)
        const times = data.map(row => {
            const dt = new Date(row[0] * 1000);
            return dt.getHours().toString().padStart(2,'0') + ':' +
                   dt.getMinutes().toString().padStart(2,'0') + ':' +
                   dt.getSeconds().toString().padStart(2,'0');
        });
        const values = data.map(row => {
            let s = 0;
            for (let i = 1; i < row.length; i++) s += (row[i] || 0);
            return Math.round(s * 10) / 10;
        });

        const ch = instances[def.id];
        ch.data.labels = times;
        ch.data.datasets[0].data = values;
        ch.update('none');

        // Update current value display
        const last = values[values.length - 1];
        document.getElementById('val-' + def.id).textContent =
            last !== undefined ? last + ' ' + def.label : '—';
    } catch(e) {
        console.warn(def.id, e);
    }
}

// Init charts
CHARTS.forEach(def => {
    instances[def.id] = mkChart(def.id, def.label, def.color);
});

// Initial fetch + poll
async function refresh() {
    await Promise.all(CHARTS.map(fetchChart));
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def run(client, cmd, timeout=60, check=False):
    print(f">>> {cmd[:120]}")
    _, sout, serr = client.exec_command(cmd, timeout=timeout, get_pty=False)
    out = sout.read().decode("utf-8", errors="replace").strip()
    err = serr.read().decode("utf-8", errors="replace").strip()
    exit_code = sout.channel.recv_exit_status()
    if out:
        print(out[:600])
    if err and not any(x in err.lower() for x in ["warning", "deprecated", "notice"]):
        print(f"[err] {err[:300]}")
    if check and exit_code != 0:
        print(f"ERROR: command exited with code {exit_code}: {cmd[:120]}")
        raise SystemExit(1)
    return out


def upload_text(sftp, content, remote_path):
    with sftp.open(remote_path, "w") as f:
        f.write(content)
    print(f"Загружен {remote_path}")


# ---------------------------------------------------------------------------
# Основной деплой
# ---------------------------------------------------------------------------

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
print(f"Подключился к {HOST}\n")

sftp = client.open_sftp()

# 1. Найти webroot Netdata
print("=== 1. Поиск webroot Netdata ===")
# Primary: look for web dir next to known netdata paths
webroot_candidates = run(
    client,
    "find /usr/share/netdata /opt/netdata -maxdepth 3 -name 'index.html' 2>/dev/null | head -3",
    timeout=15,
)
if webroot_candidates:
    webroot = webroot_candidates.splitlines()[0].rsplit("/", 1)[0]
else:
    # Fallback: standard Debian/Ubuntu path
    webroot = "/usr/share/netdata/web"
    print(f"index.html не найден, используем дефолтный путь: {webroot}")

# Verify webroot exists
exists = run(client, f"test -d {webroot} && echo yes || echo no")
if exists.strip() != "yes":
    print(f"ERROR: webroot {webroot} не существует")
    client.close()
    raise SystemExit(1)
print(f"webroot: {webroot}")

# 2. Загружаем race-day.html
print("\n=== 2. Загрузка race-day.html ===")
remote_path = f"{webroot}/race-day.html"
upload_text(sftp, HTML_CONTENT, remote_path)

sftp.close()

# 3. Устанавливаем права
print("\n=== 3. Права доступа ===")
run(client, f"chmod 644 {remote_path}", check=True)

# 4. Smoke-check
print("\n=== 4. Smoke-check ===")
http_code = run(
    client,
    "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:19999/race-day.html",
    timeout=15,
)
print(f"HTTP status: {http_code}")

client.close()

print("\n=== ГОТОВО ===")
print(f"Дашборд загружен: {remote_path}")
print("URL: https://analytics.krasmarafon.ru/netdata/race-day.html")
if http_code == "200":
    print("Smoke-check: OK (200)")
else:
    print(f"Smoke-check: ВНИМАНИЕ — статус {http_code} (ожидался 200)")
