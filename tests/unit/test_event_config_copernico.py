"""Верификация блоков copernico в config/events/zhara.yaml и kids.yaml —
race_id общий для Жары и Детского забега, event: строка у Жары 5км,
список из 6 возрастных групп у Детского забега 1км."""
import sys
from pathlib import Path

import yaml as _yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from load_race_results import _load_event_config

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_zhara_5km_copernico_config():
    dist_cfg = _load_event_config(str(PROJECT_ROOT / "config/events/zhara.yaml"), "5 км")
    cop = dist_cfg["copernico"]
    assert cop["race_id"] == "--2026-6118"
    assert cop["event"] == "5km"
    assert cop["preset"] == "km_analytics"


def test_zhara_21km_copernico_not_touched():
    """21.1 км ещё не создана в Copernico — конфиг не должен был измениться
    в рамках этой задачи."""
    dist_cfg = _load_event_config(str(PROJECT_ROOT / "config/events/zhara.yaml"), "21.1 км")
    cop = dist_cfg["copernico"]
    assert cop["race_id"] is None


def test_kids_1km_copernico_config_has_all_six_age_groups():
    dist_cfg = _load_event_config(str(PROJECT_ROOT / "config/events/kids.yaml"), "1 км")
    cop = dist_cfg["copernico"]
    assert cop["race_id"] == "--2026-6118"
    assert cop["event"] == [
        "1km-2020", "1km-2019", "1km-2018", "1km-2017", "1km-2016", "1km-2015",
    ]
    assert cop["preset"] == "km_analytics"


def test_km_analytics_preset_exists_and_has_expected_fields():
    """Без этого файла загрузчик не стартует (parser.error при отсутствии
    config/copernico/<preset>.yaml) — см. load_race_results.py main()."""
    preset_path = PROJECT_ROOT / "config/copernico/km_analytics.yaml"
    assert preset_path.exists(), f"Preset-файл не найден: {preset_path}"

    preset = _yaml.safe_load(preset_path.read_text(encoding="utf-8"))

    assert preset["fields"]["bib"] == "dorsal"
    assert preset["fields"]["surname"] == "surname"
    assert preset["fields"]["name"] == "name"
    assert preset["fields"]["birthdate"] == "birthdate"
    assert preset["fields"]["gender"] == "gender"
    assert preset["fields"]["status"] == "status"
    assert preset["fields"]["category"] == "category"

    assert preset["time_fields"]["gun_start"] == "times.official_:::start:::"
    assert preset["time_fields"]["gun_finish"] == "times.official_:::finish:::"
    assert preset["time_fields"]["chip_start"] is None
    assert preset["time_fields"]["chip_finish"] is None

    assert preset["checkpoint_fields"] == {}
