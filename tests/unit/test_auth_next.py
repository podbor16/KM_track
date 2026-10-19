import pytest

from src.core.auth import safe_next


@pytest.mark.parametrize("target,expected", [
    ("/admin/draw", "/admin/draw"),
    ("/admin/draw?year=2028", "/admin/draw?year=2028"),
    ("//evil.example/x", None),          # протокол-относительный адрес — чужой сайт
    ("/\\evil.example", None),
    ("https://evil.example/", None),
    ("admin", None),
    ("", None),
    (None, None),
])
def test_safe_next_only_same_site_paths(target, expected):
    assert safe_next(target) == expected
