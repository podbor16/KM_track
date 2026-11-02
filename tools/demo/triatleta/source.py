"""Входные данные демо Триатлета 24 ч: песочница triatleta_24h_demo -> обезличивание -> проигрывание."""
from tools.demo import sandbox
from tools.demo.races import RACES
from tools.demo.triatleta import record
from tools.demo.triatleta.anonymize import anonymize_sandbox

SEED = 2026
STEP_S = 30
EVENT_DATE = "25–26.06.2026"


def build_triatleta(key: str) -> tuple[dict, dict]:
    """-> (запись, real_pii). Пишет только в triatleta_24h_demo."""
    race = RACES[key]
    p = sandbox._env_params()
    sandbox.assert_local(p["host"], p["port"])
    sandbox.recreate("triatleta_24h", record.DEMO_DB)
    conn = sandbox.connect(record.DEMO_DB)
    try:
        real_pii = anonymize_sandbox(conn, seed=SEED)
        final = record.load_final(conn)
        record.clear_results(conn)
        rec = record.replay(conn, final, step_s=STEP_S,
                            on_step=lambda t: print(f"\r  {t:.0f} с", end="", flush=True))
        print()
    finally:
        conn.close()
    rec["meta"].update(race=key, title=race["title"], caption=race["caption"],
                       participants=len(final["participants"]), event_date=EVENT_DATE)
    return rec, real_pii
