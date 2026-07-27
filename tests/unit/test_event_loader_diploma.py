"""Тесты парсинга опционального блока diploma в DistanceConfig."""
import pytest
from src.config.event_loader import EventConfig, DistanceConfig, DiplomaConfig


def test_distance_without_diploma_defaults_to_none():
    d = DistanceConfig(distance="5 км", distance_km=5.0)
    assert d.diploma is None


def test_distance_with_diploma_parses_paths():
    d = DistanceConfig(
        distance="7 км",
        distance_km=7.0,
        db_event_id=123,
        diploma={"background": "static/images/diplomas/women7/7km/background.png"},
    )
    assert d.diploma is not None
    assert d.diploma.background == "static/images/diplomas/women7/7km/background.png"


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
                "diploma": {
                    "background": "static/images/diplomas/women7/7km/background.png",
                },
            },
            {"distance": "500 м", "distance_km": 0.5},
        ],
    }
    cfg = EventConfig(**raw)
    assert cfg.distances[0].diploma.background.endswith("background.png")
    assert cfg.distances[1].diploma is None
