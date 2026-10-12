"""Категории по ДР (scripts/normalize_result_categories.py) — группы Жары 2027 на все годы (2026-10-12)."""
import datetime
from unittest.mock import MagicMock

from scripts.normalize_result_categories import categories_from_birthday

ZHARA_5_10 = (13, 15, 17, 49, 59, 64, 69, 74, 79)


def test_zhara_groups_from_birthday_skip_placeholder_and_same():
    cur = MagicMock()
    cur.fetchone.return_value = (2023,)
    cur.fetchall.return_value = [
        (1, datetime.date(2010, 5, 1), "Женщина", "Ж12-13"),      # уже верно — не меняется
        (2, datetime.date(1990, 1, 1), "Мужчина", "М18+"),        # 33 года → М18-49
        (3, datetime.date(1945, 3, 3), "Женщина", "Ж18+"),        # 78 → Ж75-79
        (4, datetime.date(1940, 3, 3), "Мужчина", "М18+"),        # 83 → М80+
        (5, datetime.date(1900, 1, 1), "Мужчина", "М18+"),        # заглушка — не трогаем
    ]
    out = categories_from_birthday(cur, 220, ZHARA_5_10, 12)
    assert out == [(2, "М18-49"), (3, "Ж75-79"), (4, "М80+")]
    assert "is_pacer = 0" in cur.execute.call_args_list[1].args[0]
