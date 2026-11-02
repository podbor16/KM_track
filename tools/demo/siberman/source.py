"""Входные данные демо Siberman: песочница siberman_demo (копия локальной БД) -> обезличивание -> проигрывание."""
import os

from tools.demo.races import RACES
from tools.demo.siberman import record, sandbox
from tools.demo.siberman.anonymize import anonymize_sandbox

SEED = 2026
STEP_S = 20
EVENT_DATE = "06–08.08.2026"


def build_siberman(key: str) -> tuple[dict, dict]:
    """-> (запись, real_pii). Пишет только в siberman_demo; SIBERMAN_DB_NAME возвращает как было."""
    race = RACES[key]
    year = race["race_year"]
    sandbox.assert_local(*(sandbox._env_params()[k] for k in ("host", "port")))
    prev = os.environ.get("SIBERMAN_DB_NAME")
    os.environ["SIBERMAN_DB_NAME"] = "siberman_demo"
    try:
        sandbox.recreate()
        conn = sandbox.connect("siberman_demo")
        try:
            real_pii = anonymize_sandbox(conn, seed=SEED, race_year=year)
            final = record.load_final(conn, year)
            record.clear_results(conn, year)
            rec = record.replay(conn, year, final, step_s=STEP_S,
                                on_step=lambda t, total: print(f"\r  {t}/{total}", end="", flush=True))
            print()
        finally:
            conn.close()
    finally:
        if prev is None:
            os.environ.pop("SIBERMAN_DB_NAME", None)
        else:
            os.environ["SIBERMAN_DB_NAME"] = prev
    d1 = rec["meta"]["days"][0]
    rec["meta"].update(
        race=key, title=race["title"], caption=race["caption"], participants=len(final["participants"]),
        event_date=EVENT_DATE, loop_start_s=int((d1["start_s"] + d1["end_s"]) / 2),
    )
    return rec, real_pii
