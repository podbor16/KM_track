"""Внешняя проверка доступности (scripts/uptime_check.py): алерт только при смене состояния и раз в час."""
import json
from unittest.mock import patch

from scripts import uptime_check as uc


def test_down_alerts_once_then_reminds_hourly_and_recovers():
    state, alerts = uc.transitions({}, {"a": "HTTP 502", "b": None}, now=1000)
    assert list(state) == ["a"] and [t for t, *_ in alerts] == ["🔴 a недоступен"]
    assert alerts[0][3] == "urgent"

    state, alerts = uc.transitions(state, {"a": "HTTP 502", "b": None}, now=1000 + 1800)
    assert alerts == [] and state["a"]["down_since"] == 1000

    state, alerts = uc.transitions(state, {"a": "URLError: timed out", "b": None}, now=1000 + 3600)
    assert [t for t, *_ in alerts] == ["🔴 a всё ещё недоступен"] and "Уже 1 ч 0 мин" in alerts[0][1]

    state, alerts = uc.transitions(state, {"a": None, "b": None}, now=1000 + 3600 + 600)
    assert state == {} and [t for t, *_ in alerts] == ["✅ a снова доступен"]
    assert alerts[0][1] == ["Простой: 1 ч 10 мин"]


def test_all_ok_no_alerts():
    assert uc.transitions({}, {"a": None, "b": None}, now=5) == ({}, [])


def test_runner_network_failure_keeps_state_and_sends_nothing(tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["uptime_check.py", "--state", str(path)])
    with patch.object(uc, "probe", return_value="URLError: no network"), patch.object(uc.ntfy, "send") as send:
        assert uc.main() == 0
    send.assert_not_called()
    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_main_sends_down_alert_and_saves_state(tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    monkeypatch.setattr("sys.argv", ["uptime_check.py", "--state", str(path)])
    down = {uc.SITES["results.krasmarafon.ru"]: "HTTP 502"}
    with patch.object(uc, "probe", side_effect=lambda url: down.get(url)), \
         patch.object(uc.ntfy, "send", return_value=True) as send:
        assert uc.main() == 0
    title = send.call_args.args[0]
    assert title == "🔴 results.krasmarafon.ru недоступен" and send.call_args.kwargs["priority"] == "urgent"
    assert list(json.loads(path.read_text(encoding="utf-8"))) == ["results.krasmarafon.ru"]
