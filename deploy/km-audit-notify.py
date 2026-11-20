"""Send a small ntfy notification for successful nginx worker exec events."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
import urllib.parse
import urllib.request


STATE = Path("/var/lib/km-audit-notify/state.json")
DESTINATION = Path("/etc/km-audit-notify/ntfy-url")
LOG_DIR = Path("/var/log/audit")
WINDOW_SECONDS = 600
LINE = re.compile(rb'^type=SYSCALL msg=audit\((\d+(?:\.\d+)?):\d+\): ')
COMM = re.compile(rb' comm="([A-Za-z0-9._-]{1,64})" ')
KEY = b' key="nginx_worker_exec"'
ROTATED = re.compile(r"audit\.log\.\d+")


def log_paths():
    rotated = sorted(
        (path for path in LOG_DIR.glob("audit.log.*") if ROTATED.fullmatch(path.name)),
        key=lambda path: int(path.suffix[1:]),
        reverse=True,
    )
    return [*rotated, LOG_DIR / "audit.log"]


def read_events(offsets, initialize=False):
    new_offsets = {}
    events = []
    for path in log_paths():
        try:
            stream = path.open("rb")
        except FileNotFoundError:
            continue  # A log rotated before its path could be opened.
        with stream:
            info = os.fstat(stream.fileno())
            identity = f"{info.st_dev}:{info.st_ino}"
            if identity in new_offsets:
                continue
            start = offsets.get(identity, 0)
            stream.seek(0 if start > info.st_size else start)
            if initialize:
                stream.seek(0, os.SEEK_END)
            else:
                while line := stream.readline():
                    if not line.endswith(b"\n"):
                        stream.seek(-len(line), os.SEEK_CUR)
                        break
                    line = line.split(b"\x1d", 1)[0]  # auditd ENRICHED appends resolved fields.
                    stamp = LINE.match(line)
                    if not stamp or b" success=yes " not in line or not line.rstrip().endswith(KEY):
                        continue
                    name = COMM.search(line)
                    events.append({
                        "time": float(stamp[1]),
                        "name": name[1].decode("ascii") if name else "см. журнал",
                    })
            new_offsets[identity] = stream.tell()
    return sorted(events, key=lambda event: event["time"]), new_offsets


def save(state):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(STATE)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def publish(title, event, count=1):
    url = DESTINATION.read_text(encoding="utf-8").strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        raise ValueError("Ожидается HTTPS-адрес темы ntfy")
    when = datetime.fromtimestamp(event["time"]).astimezone().isoformat(timespec="seconds")
    body = f"Узел {socket.gethostname()}\nВремя {when}\nПрограмма {event['name']}"
    if count > 1 or title.endswith("summary"):
        body += f"\nПовторных событий {count}"
    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "Title": title,
            "Tags": "warning",
            "Priority": "high",
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=8) as response:
        print(f"ntfy accepted {title}, HTTP {response.status}", flush=True)


def deliver(state, now):
    repeats = state.get("repeats", 0)
    expired = "until" in state and now >= state["until"]
    if repeats and expired:
        publish("KM_track audit summary", state["last_repeat"], repeats)
        state["repeats"] = 0
        state.pop("last_repeat")
        save(state)
    pending = state.get("pending")
    if not pending:
        return
    publish("KM_track nginx worker exec", pending)
    state.pop("pending")
    state["until"] = now + WINDOW_SECONDS
    save(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args()
    if args.initialize:
        if STATE.exists():
            raise FileExistsError(STATE)
        _, offsets = read_events({}, initialize=True)
        save({"offsets": offsets})
        return
    state = json.loads(STATE.read_text(encoding="utf-8"))
    events, state["offsets"] = read_events(state["offsets"])
    now = time.time()
    for event in events:
        if not state.get("pending") and event["time"] >= state.get("until", 0):
            state["pending"] = event
        else:
            state["repeats"] = state.get("repeats", 0) + 1
            state["last_repeat"] = event
    save(state)
    deliver(state, now)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Exception text from urllib can contain the destination URL.
        print(f"audit notification failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
