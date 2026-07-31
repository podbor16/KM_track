"""Тесты парсинга опционального блока diploma в DistanceConfig."""
import pytest
from src.config.event_loader import EventConfig, DistanceConfig, DiplomaConfig

_DIPLOMA_DICT = {
    "background": "static/images/diplomas/women7/7km/background.png",
    "width_px": 1080,
    "height_px": 1920,
    "name_box": {"top": 24.8, "left": 8.8, "width": 81.6, "height": 17.9},
    "ranks_box": {"top": 45.8, "left": 8.8, "width": 81.6, "height": 16.3},
}


def test_distance_without_diploma_defaults_to_none():
    d = DistanceConfig(distance="5 км", distance_km=5.0)
    assert d.diploma is None


def test_distance_with_diploma_parses_paths():
    d = DistanceConfig(
        distance="7 км",
        distance_km=7.0,
        db_event_id=123,
        diploma=_DIPLOMA_DICT,
    )
    assert d.diploma is not None
    assert d.diploma.background == "static/images/diplomas/women7/7km/background.png"
    assert d.diploma.width_px == 1080
    assert d.diploma.height_px == 1920
    assert d.diploma.name_box.top == 24.8
    assert d.diploma.ranks_box.height == 16.3


def test_diploma_requires_box_positions():
    """width_px/height_px/name_box/ranks_box обязательны — у каждого дизайна
    своя раскладка, магических дефолтов "как у первого события" нет."""
    with pytest.raises(Exception):
        DistanceConfig(
            distance="7 км",
            distance_km=7.0,
            diploma={"background": "static/images/diplomas/women7/7km/background.png"},
        )


def test_event_config_with_yaml_style_dict_parses():
    """Полный EventConfig, как будто загружен из YAML (raw dict, не объекты)."""
    raw = {
        "code": "women7",
        "name": "Женская семерка",
        "display_name": "Женская семёрка",
        "year": 2026,
        "distances": [
            {
                "distance": "7 км",
                "distance_km": 7.0,
                "db_event_id": 123,
                "diploma": _DIPLOMA_DICT,
            },
            {"distance": "500 м", "distance_km": 0.5},
        ],
    }
    cfg = EventConfig(**raw)
    assert cfg.distances[0].diploma.background.endswith("background.png")
    assert cfg.distances[1].diploma is None
