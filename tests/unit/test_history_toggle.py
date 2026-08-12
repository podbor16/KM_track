"""Тесты get_history_enabled()/set_history_enabled() — переключатель
раздела «История участия» (config/history_enabled.local, вне git, как
active_event.local)."""
import src.config.event_loader as event_loader


def test_history_enabled_by_default_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(event_loader, "_HISTORY_ENABLED_FILE", tmp_path / "history_enabled.local")
    assert event_loader.get_history_enabled() is True


def test_history_disabled_when_file_says_false(tmp_path, monkeypatch):
    f = tmp_path / "history_enabled.local"
    f.write_text("false", encoding="utf-8")
    monkeypatch.setattr(event_loader, "_HISTORY_ENABLED_FILE", f)
    assert event_loader.get_history_enabled() is False


def test_set_history_enabled_round_trip(tmp_path, monkeypatch):
    f = tmp_path / "history_enabled.local"
    monkeypatch.setattr(event_loader, "_HISTORY_ENABLED_FILE", f)

    event_loader.set_history_enabled(False)
    assert event_loader.get_history_enabled() is False

    event_loader.set_history_enabled(True)
    assert event_loader.get_history_enabled() is True


def test_history_enabled_ignores_case_and_whitespace(tmp_path, monkeypatch):
    f = tmp_path / "history_enabled.local"
    f.write_text("  FALSE  \n", encoding="utf-8")
    monkeypatch.setattr(event_loader, "_HISTORY_ENABLED_FILE", f)
    assert event_loader.get_history_enabled() is False
