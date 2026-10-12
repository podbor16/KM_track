#!/usr/bin/env python3
"""
Внешняя проверка доступности сайтов на VPS (GitHub Actions, .github/workflows/uptime.yml, решение 2026-10-12).

Мониторинг на самом VPS (collector, ntfy) молчит, когда VPS лежит целиком, — эта проверка идёт снаружи.
Алерт в ntfy (NTFY_URL) — только при смене состояния (упал / восстановился, с длительностью простоя)
и напоминание раз в час, пока сайт лежит. Состояние между запусками — JSON-файл (кеш Actions).

  python scripts/uptime_check.py --state uptime_state.json
  python scripts/uptime_check.py --state uptime_state.json --test-alert   # + тестовое уведомление (проверка доставки)
"""

import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common import ntfy  # noqa: E402

SITES = {
    "results.krasmarafon.ru": "https://results.krasmarafon.ru/health",
    "live.siberman515.com": "https://live.siberman515.com/",
    "live-race.triatleta.ru": "https://live-race.triatleta.ru/",
}
CONTROL = "https://api.github.com/zen"            # сбой у всех + нет и его → сеть раннера, не сайты
ATTEMPTS, TIMEOUT, PAUSE = 2, 15, 20
REMIND_EVERY = 3600
KRSK = datetime.timezone(datetime.timedelta(hours=7))


def probe(url):
    """None — сайт отвечает 2xx/3xx, иначе причина сбоя (последняя из попыток)."""
    reason = None
    for attempt in range(ATTEMPTS):
        if attempt:
            time.sleep(PAUSE)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "km-uptime-check"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                if resp.status < 400:
                    return None
                reason = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            reason = f"HTTP {e.code}"
        except Exception as e:
            reason = type(e).__name__ + (f": {e.reason}" if getattr(e, "reason", None) else "")
    return reason


def _duration(seconds):
    minutes = int(seconds // 60)
    return f"{minutes // 60} ч {minutes % 60} мин" if minutes >= 60 else f"{minutes} мин"


def transitions(state, results, now):
    """state {сайт: {"down_since": ts, "notified": ts}} + results {сайт: причина|None} →
    (новое состояние, [(заголовок, строки, теги, приоритет)])."""
    new, alerts = {}, []
    for site, reason in results.items():
        was = state.get(site)
        if reason is None:
            if was:
                alerts.append((f"✅ {site} снова доступен", [f"Простой: {_duration(now - was['down_since'])}"],
                               "white_check_mark", "default"))
            continue
        if not was:
            new[site] = {"down_since": now, "notified": now}
            alerts.append((f"🔴 {site} недоступен", [f"Причина: {reason}", "Проверка снаружи (GitHub Actions)"],
                           "rotating_light", "urgent"))
        elif now - was["notified"] >= REMIND_EVERY:
            new[site] = {"down_since": was["down_since"], "notified": now}
            alerts.append((f"🔴 {site} всё ещё недоступен", [f"Уже {_duration(now - was['down_since'])}",
                                                              f"Причина: {reason}"], "rotating_light", "high"))
        else:
            new[site] = was
    return new, alerts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", required=True, help="JSON-файл состояния между запусками")
    ap.add_argument("--test-alert", action="store_true", help="отправить тестовое уведомление (ручной запуск)")
    args = ap.parse_args()
    path = Path(args.state)
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    results = {site: probe(url) for site, url in SITES.items()}
    if any(results.values()) and probe(CONTROL):
        print("Контрольный адрес тоже недоступен — сбой сети раннера, состояние не меняется:", results)
        return 0
    now = time.time()
    stamp = datetime.datetime.fromtimestamp(now, KRSK).strftime("%d.%m %H:%M")
    for site, reason in results.items():
        print(f"{site}: {'ok' if reason is None else reason}")
    state, alerts = transitions(state, results, now)
    if args.test_alert:
        alerts.append(("Тест внешнего мониторинга", [f"{s}: {'ok' if r is None else r}" for s, r in results.items()],
                       "test_tube", "low"))
    sent = True
    for title, lines, tags, priority in alerts:
        print("ntfy:", title)
        sent &= ntfy.send(title, lines + [f"{stamp} (Красноярск)"], tags=tags, priority=priority)
    path.write_text(json.dumps(state), encoding="utf-8")
    return 0 if sent else 1


if __name__ == "__main__":
    sys.exit(main())
