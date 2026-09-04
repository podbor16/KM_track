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
from unittest.mock import MagicMock

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from load_duathlon_results import _load_preset, PRESET_CONFIG_PATH, _prune_removed_participants


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


def test_prune_removed_participants_deletes_ids_not_in_touched_set():
    """Регрессия (2026-09-04, прод): участник, снятый/удалённый в Copernico
    (15 -> 14), навсегда оставался в БД — ни --init, ни --resync его не
    убирали, только insert/update (_get_or_create_participant). resync()
    сбрасывает этапы, но не сам список участников."""
    cursor = MagicMock()
    cursor.rowcount = 1

    removed = _prune_removed_participants(cursor, event_id=1, touched_pids={10, 11, 12})

    assert removed == 1
    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args[0]
    assert "DELETE FROM participants" in sql
    assert "NOT IN" in sql
    assert params[0] == 1
    assert set(params[1:]) == {10, 11, 12}


def test_prune_removed_participants_noop_on_empty_touched_set():
    """Пустой touched_pids (сломанный/пустой ответ Copernico) не должен
    стирать весь список участников события."""
    cursor = MagicMock()

    removed = _prune_removed_participants(cursor, event_id=1, touched_pids=set())

    assert removed == 0
    cursor.execute.assert_not_called()
