"""
Мониторинг RAM/CPU на VPS во время нагрузочного теста.
Запускается в фоновом потоке, пишет метрики в CSV каждые 10 секунд.

Использование:
    from tests.load.vps_monitor import VpsMonitor
    mon = VpsMonitor(report_path)
    mon.start()
    # ... тест ...
    mon.stop()
"""
import csv
import threading
import time
from pathlib import Path
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD


class VpsMonitor:
    def __init__(self, csv_path: Path, interval_s: int = 10):
        self._csv_path = csv_path
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=15)

    def _run(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
            client.get_transport().set_keepalive(30)
        except Exception as e:
            print(f"  [monitor] SSH connect failed: {e}")
            return

        with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ts", "ram_used_mb", "ram_total_mb", "ram_pct", "cpu_idle_pct"])

            while not self._stop.is_set():
                try:
                    _, out, _ = client.exec_command(
                        "free -m | awk 'NR==2{print $3,$2}'; "
                        "vmstat 1 2 | tail -1 | awk '{print $15}'"
                    )
                    lines = out.read().decode("utf-8", errors="replace").strip().splitlines()
                    if len(lines) >= 2:
                        parts = lines[0].split()
                        ram_used, ram_total = int(parts[0]), int(parts[1])
                        ram_pct = round(ram_used / ram_total * 100, 1) if ram_total > 0 else 0.0
                        cpu_idle = int(lines[1].strip())
                        ts = int(time.time())
                        writer.writerow([ts, ram_used, ram_total, ram_pct, cpu_idle])
                        f.flush()
                        print(
                            f"  [VPS] RAM {ram_used}/{ram_total}MB ({ram_pct}%) "
                            f"CPU {100-cpu_idle}%"
                        )
                except Exception as e:
                    print(f"  [monitor] error: {e}")

                self._stop.wait(self._interval)

        client.close()
