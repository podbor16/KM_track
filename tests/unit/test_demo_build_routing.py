import sys

from tools.demo import build
from tools.demo.races import RACES


def test_ep_races_routed_to_builders():
    ep = {k for k, r in RACES.items() if r.get("format") == "ep"}
    assert ep == set(build.EP_BUILDERS) == {"triatleta_24h", "duathlon222_2026"}
    assert all(RACES[k]["mode"] == "poll" for k in ep)
    assert "format" not in RACES["siberman_2026"]
