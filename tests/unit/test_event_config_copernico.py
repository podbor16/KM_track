"""Верификация блоков copernico в config/events/zhara.yaml и kids.yaml —
race_id общий для Жары и Детского забега, event: строка у Жары 5км,
список из 6 возрастных групп у Детского забега 1км. Организатор развёл
общий пресет "km_analytics" на три отдельных пресета по дистанциям
(km_zhara_5km_2026, km_kids_1km_2026, km_zhara_21km_2026) — у каждой
дистанции свои чекпоинты, живой fetch подтвердил реальные КТ."""
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
    assert cop["preset"] == "km_zhara_5km_2026"
    assert dist_cfg["checkpoint_distances"] == [0, 2.5, 5.0]


def test_zhara_21km_copernico_not_touched():
    """21.1 км ещё не создана в Copernico (race_id/event) — только preset
    прописан заранее (организатор уже создал его в Copernico)."""
    dist_cfg = _load_event_config(str(PROJECT_ROOT / "config/events/zhara.yaml"), "21.1 км")
    cop = dist_cfg["copernico"]
    assert cop["race_id"] is None
    assert cop["preset"] == "km_zhara_21km_2026"


def test_kids_1km_copernico_config_has_all_six_age_groups():
    dist_cfg = _load_event_config(str(PROJECT_ROOT / "config/events/kids.yaml"), "1 км")
    cop = dist_cfg["copernico"]
    assert cop["race_id"] == "--2026-6118"
    assert cop["event"] == [
        "1km-2020", "1km-2019", "1km-2018", "1km-2017", "1km-2016", "1km-2015",
    ]
    assert cop["preset"] == "km_kids_1km_2026"
    assert dist_cfg["checkpoint_distances"] == [0, 0.5, 1.0]


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


def test_km_zhara_5km_2026_preset_uses_only_the_2_5km_checkpoint():
    """Copernico отдаёт 2 поля КТ (2,5 и 4,5 км) — 4,5 км это отсечка для
    судей (видеть, кто подбегает к финишу), нам не нужна и намеренно не
    замаплена."""
    preset_path = PROJECT_ROOT / "config/copernico/km_zhara_5km_2026.yaml"
    assert preset_path.exists(), f"Preset-файл не найден: {preset_path}"

    preset = _yaml.safe_load(preset_path.read_text(encoding="utf-8"))

    assert preset["time_fields"]["gun_start"] == "times.official_:::start:::"
    assert preset["time_fields"]["gun_finish"] == "times.official_:::finish:::"
    assert preset["checkpoint_fields"] == {"kt1": "times.official_2,5"}


def test_km_kids_1km_2026_preset_has_500m_checkpoint():
    """Живой fetch (2026-08-21) подтвердил КТ на разворот 500м у
    Детского забега (times.official_500)."""
    preset_path = PROJECT_ROOT / "config/copernico/km_kids_1km_2026.yaml"
    assert preset_path.exists(), f"Preset-файл не найден: {preset_path}"

    preset = _yaml.safe_load(preset_path.read_text(encoding="utf-8"))

    assert preset["time_fields"]["gun_start"] == "times.official_:::start:::"
    assert preset["time_fields"]["gun_finish"] == "times.official_:::finish:::"
    assert preset["checkpoint_fields"] == {"kt1": "times.official_500"}


def test_km_zhara_21km_2026_preset_exists_unverified():
    """21.1 км ещё не создана в Copernico — checkpoint_fields намеренно
    пустой до живой проверки (см. описание в самом preset-файле)."""
    preset_path = PROJECT_ROOT / "config/copernico/km_zhara_21km_2026.yaml"
    assert preset_path.exists(), f"Preset-файл не найден: {preset_path}"

    preset = _yaml.safe_load(preset_path.read_text(encoding="utf-8"))

    assert preset["time_fields"]["gun_start"] == "times.official_:::start:::"
    assert preset["time_fields"]["gun_finish"] == "times.official_:::finish:::"
    assert preset["checkpoint_fields"] == {}
