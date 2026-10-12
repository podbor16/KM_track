"""
Возврат свободной памяти распределителя glibc системе (2026-10-12).

Тяжёлая работа воркеров (сборка результатов, MySQL C-драйвер, JSON) идёт в пуле потоков;
glibc раздаёт потокам отдельные арены и почти не отдаёт из них освобождённые страницы —
воркер 80 МБ → 370–510 МБ за двое суток при отсутствии утечки объектов Python (tracemalloc
не растёт, ~360 МБ — в 8 аренах по 64 МБ). Лечение: MALLOC_ARENA_MAX=2 в km_track.service
и malloc_trim(0) раз в минуту (_metrics_flusher в app.py).
"""

import ctypes
import ctypes.util

_libc = None


def _load_libc():
    global _libc
    if _libc is None:
        name = ctypes.util.find_library("c")
        try:
            lib = ctypes.CDLL(name) if name else None
            _libc = lib if lib is not None and hasattr(lib, "malloc_trim") else False
        except OSError:
            _libc = False
    return _libc


def trim() -> bool:
    """malloc_trim(0): отдать системе свободные страницы всех арен. Не glibc (Windows, musl) —
    ничего не делает. -> True, если glibc что-то вернула."""
    lib = _load_libc()
    if not lib:
        return False
    return bool(lib.malloc_trim(0))
