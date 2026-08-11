"""
Бэкофилл: проставить is_duplicate=1 для всех строк leads в группах
(client_id, event_id), где строк больше одной — компенсирует то, что
trg_leads_before_insert никогда фактически не считал is_duplicate
(мёртвый код `SET NEW.is_duplicate = 0;`). Разовый скрипт, безопасно
перезапускать (SQL идемпотентен).

Запускать ПОСЛЕ деплоя фикса recompute_duplicate_flag() (webhook.py +
db_results.py) — иначе новая заявка между бэкофиллом и деплоем создаст
неучтённый дубль.

Usage: python deploy/ssh_backfill_lead_duplicates.py
"""
import subprocess
from pathlib import Path
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD, DB_NAME

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "deploy" / "sql" / "backfill_lead_is_duplicate.sql"


def plink_run(cmd: str, stdin_bytes: bytes = None, timeout: int = 60) -> str:
    args = ["plink.exe", "-ssh", "-batch", "-pw", VPS_PASSWORD, f"{VPS_USER}@{VPS_HOST}", cmd]
    r = subprocess.run(args, input=stdin_bytes, capture_output=True, timeout=timeout)
    out = r.stdout.decode(errors="replace").strip()
    err = r.stderr.decode(errors="replace").strip()
    if out:
        print(out)
    if r.returncode != 0:
        raise RuntimeError(f"plink command failed (exit {r.returncode}): {cmd[:120]}\n{err}")
    return out


def main():
    print(f"=== Backfilling leads.is_duplicate on {DB_NAME} @ {VPS_HOST} ===")
    sql_bytes = SQL_FILE.read_bytes()
    plink_run(f"mysql -u root {DB_NAME}", stdin_bytes=sql_bytes)
    print("\n=== Done. Review output above. ===")


if __name__ == "__main__":
    main()
