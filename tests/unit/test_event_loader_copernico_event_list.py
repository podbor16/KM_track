"""Регрессия: config/events/kids.yaml перестал загружаться веб-приложением
(load_all_events()) после того, как copernico.event стал списком из 6
возрастных групп — CopernicoConfig.event был типизирован только как str,
Pydantic ронял валидацию, событие тихо выпадало (WARNING в логах каждые
~30с на проде), из-за чего /api/current-event и производные от него
данные (напр. состав колонок в /results) работали по неполному/фолбэк
конфигу для Детского забега."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.event_loader import CopernicoConfig, load_all_events

PROJECT_ROOT = Path(__file__).parent.parent.parent
EVENTS_DIR = PROJECT_ROOT / "config" / "events"


def test_copernico_config_accepts_event_as_list():
    cfg = CopernicoConfig(
        login="podbor250718@gmail.com",
        preset="km_kids_1km_2026",
        event=["1km-2020", "1km-2019"],
    )
    assert cfg.event == ["1km-2020", "1km-2019"]


def test_copernico_config_still_accepts_event_as_string():
    """Регрессия — все остальные события (Весна, Первомай и т.д.) передают
    event одной строкой, это не должно сломаться."""
    cfg = CopernicoConfig(login="x", preset="p", event="5km")
    assert cfg.event == "5km"


def test_kids_yaml_loads_successfully_via_web_app_event_loader():
    """Раньше падало с 'Input should be a valid string' на
    distances.0.copernico.event и событие полностью выпадало из
    load_all_events() — код в try/except только логировал WARNING."""
    events = load_all_events(EVENTS_DIR)
    assert "kids" in events, "kids.yaml не загрузился — событие отсутствует в load_all_events()"

    kids_1km = next(d for d in events["kids"].distances if d.distance == "1 км")
    assert kids_1km.copernico.event == [
        "1km-2020", "1km-2019", "1km-2018", "1km-2017", "1km-2016", "1km-2015",
    ]


def test_zhara_yaml_loads_successfully_via_web_app_event_loader():
    """Регрессия — zhara.yaml (event: строка у всех дистанций) должен
    продолжать загружаться как раньше."""
    events = load_all_events(EVENTS_DIR)
    assert "zhara" in events, "zhara.yaml не загрузился"
