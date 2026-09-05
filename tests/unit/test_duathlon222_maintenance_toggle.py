"""Тесты get_duathlon222_maintenance_enabled()/set_duathlon222_maintenance_enabled() —
независимый переключатель заглушки техработ ТОЛЬКО для Дуатлона 222
(config/duathlon222_maintenance_mode.local, вне git). В отличие от
get_maintenance_enabled() (общий флаг, дефолт "включено" при отсутствии
файла) — здесь дефолт "выключено" (фича добавлена во время идущей гонки
05.09.2026, включать сразу нельзя)."""
import src.config.event_loader as event_loader


def test_duathlon222_maintenance_disabled_by_default_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(event_loader, "_DUATHLON222_MAINTENANCE_MODE_FILE", tmp_path / "duathlon222_maintenance_mode.local")
    assert event_loader.get_duathlon222_maintenance_enabled() is False


def test_duathlon222_maintenance_enabled_when_file_says_true(tmp_path, monkeypatch):
    f = tmp_path / "duathlon222_maintenance_mode.local"
    f.write_text("true", encoding="utf-8")
    monkeypatch.setattr(event_loader, "_DUATHLON222_MAINTENANCE_MODE_FILE", f)
    assert event_loader.get_duathlon222_maintenance_enabled() is True


def test_set_duathlon222_maintenance_enabled_round_trip(tmp_path, monkeypatch):
    f = tmp_path / "duathlon222_maintenance_mode.local"
    monkeypatch.setattr(event_loader, "_DUATHLON222_MAINTENANCE_MODE_FILE", f)

    event_loader.set_duathlon222_maintenance_enabled(True)
    assert event_loader.get_duathlon222_maintenance_enabled() is True

    event_loader.set_duathlon222_maintenance_enabled(False)
    assert event_loader.get_duathlon222_maintenance_enabled() is False


def test_duathlon222_maintenance_ignores_case_and_whitespace(tmp_path, monkeypatch):
    f = tmp_path / "duathlon222_maintenance_mode.local"
    f.write_text("  TRUE  \n", encoding="utf-8")
    monkeypatch.setattr(event_loader, "_DUATHLON222_MAINTENANCE_MODE_FILE", f)
    assert event_loader.get_duathlon222_maintenance_enabled() is True


def test_duathlon222_maintenance_any_other_content_is_disabled(tmp_path, monkeypatch):
    # Не "true" (в любом регистре) -> выключено — намеренно строгая проверка
    # на равенство "true", а не на неравенство "false" (см. docstring
    # get_duathlon222_maintenance_enabled — обратная логика get_maintenance_enabled()).
    f = tmp_path / "duathlon222_maintenance_mode.local"
    f.write_text("garbage", encoding="utf-8")
    monkeypatch.setattr(event_loader, "_DUATHLON222_MAINTENANCE_MODE_FILE", f)
    assert event_loader.get_duathlon222_maintenance_enabled() is False
