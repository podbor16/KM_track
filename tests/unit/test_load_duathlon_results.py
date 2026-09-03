"""Тесты для load_duathlon_results.py::_load_preset().

Регрессия (2026-09-03, прод): _load_preset() ошибочно принимала
cop["preset"] (имя пресета В САМОМ COPERNICO, напр. "222_2026" — просто
идентификатор для URL API) как имя ЛОКАЛЬНОГО YAML-файла с
field-маппингом. У tri_24h оба имени случайно совпадали ("tri_24h_2026"),
у Дуатлона 222 организатор назвал пресет в Copernico UI иначе, чем наш
файл конфига ("duathlon_222_2026.yaml") — FileNotFoundError при
Инициализации/Пересинхронизации через админку.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from load_duathlon_results import _load_preset, PRESET_CONFIG_PATH


def test_load_preset_reads_local_config_without_arguments():
    field_map, stage_fields, stage_lap_fields, transition_fields = _load_preset()
    assert field_map["start_number"] == "dorsal"
    assert "run1" in stage_fields
    assert "run1" in stage_lap_fields
    assert "t1_start" in transition_fields
    assert "t2_start" in transition_fields


def test_preset_config_path_independent_of_real_copernico_preset_name():
    """Имя пресета в Copernico ("222_2026") и имя нашего локального файла
    ("duathlon_222_2026") реально разные — _load_preset() не должен
    зависеть от cop["preset"], иначе снова FileNotFoundError на проде."""
    with open("config/events/duathlon_222.yaml", encoding="utf-8") as f:
        event_cfg = yaml.safe_load(f)
    real_copernico_preset_name = event_cfg["distances"][0]["copernico"]["preset"]

    assert real_copernico_preset_name != Path(PRESET_CONFIG_PATH).stem
    field_map, _, _, _ = _load_preset()
    assert field_map
