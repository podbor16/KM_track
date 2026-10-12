"""malloc_trim (src/common/memory.py): на glibc зовёт malloc_trim(0), без glibc — ничего не делает."""
from unittest.mock import MagicMock, patch

from src.common import memory


def test_trim_calls_malloc_trim_on_glibc():
    lib = MagicMock()
    lib.malloc_trim.return_value = 1
    with patch.object(memory, "_libc", lib):
        assert memory.trim() is True
    lib.malloc_trim.assert_called_once_with(0)


def test_trim_is_noop_without_glibc():
    with patch.object(memory, "_libc", False):
        assert memory.trim() is False


def test_trim_does_not_fail_on_this_platform():
    memory._libc = None
    assert memory.trim() in (True, False)
