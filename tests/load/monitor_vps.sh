#!/bin/bash
# Мониторинг CPU/RAM/TCP-соединений на VPS во время нагрузочного теста.
# Запускать НА VPS в отдельной SSH-сессии параллельно с тестом.
#
# Использование:
#   chmod +x monitor_vps.sh
#   ./monitor_vps.sh L1
#
# Лог сохраняется в vps_monitor_L1.csv — скопировать на тест-машину после теста:
#   scp km@<VPS_IP>:~/vps_monitor_L1.csv reports/load/YYYY-MM-DD/

# set -e — removed to prevent script exit on individual command failures

LEVEL="${1:-test}"
LOG="vps_monitor_${LEVEL}.csv"

echo "timestamp,cpu_pct,ram_used_mb,ram_total_mb,tcp_established,tcp_time_wait" > "$LOG"
echo "Мониторинг запущен → $LOG (Ctrl+C для остановки)"
echo "Уровень: $LEVEL"

while true; do
    ts=$(date +%s)
    # CPU% — берём idle из vmstat, вычитаем из 100
    cpu_idle=$(vmstat 1 2 | tail -1 | awk '{print $15+0}')
    cpu=$((100 - cpu_idle))
    # RAM
    ram_used=$(free -m | awk '/^Mem:/{print $3}')
    ram_total=$(free -m | awk '/^Mem:/{print $2}')
    # TCP соединения
    tcp_est=$(ss -s 2>/dev/null | awk '/estab/{match($0,/estab ([0-9]+)/,a); print a[1]+0}')
    tcp_tw=$(ss -s 2>/dev/null | awk '/timewait/{match($0,/timewait ([0-9]+)/,a); print a[1]+0}')

    echo "${ts},${cpu:-0},${ram_used:-0},${ram_total:-0},${tcp_est:-0},${tcp_tw:-0}" >> "$LOG"
    sleep 5
done
