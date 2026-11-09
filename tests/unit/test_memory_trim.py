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


def test_rss_mb_reads_resident_pages_from_statm(tmp_path, monkeypatch):
    """/proc/self/statm: второе число — резидентные страницы; страница 4 КБ → 25600 стр. = 100 МБ."""
    statm = tmp_path / "statm"
    statm.write_text("90000 25600 3000 100 0 20000 0\n")
    monkeypatch.setattr(memory, "_STATM", str(statm))
    monkeypatch.setattr(memory, "_PAGE_MB", 4096 / 1048576)
    assert memory.rss_mb() == 100.0


def test_rss_mb_is_none_without_proc(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "_STATM", str(tmp_path / "missing"))
    assert memory.rss_mb() is None
