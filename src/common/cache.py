"""
Вытеснение устаревших записей из кешей «словарь значений + словарь отметок времени».

Кеши в воркерах gunicorn (результаты, ответы /api/event-results, сегменты, стартовые
списки) хранились вечно: TTL проверялся только при чтении, и каждый когда-либо
запрошенный забег оставался в памяти (~7 МБ на забег, 3 воркера — до 1,6 ГБ на
сервере 3 ГБ, 2026-10-07). prune() перед записью удаляет записи старше max_age.
"""

import time


def prune(ts: dict, max_age: float, *stores: dict, now: float | None = None) -> int:
    """Удалить из ts и всех stores ключи, чья отметка в ts старше max_age секунд.
    max_age не меньше окна чтения кеша — свежая запись не пропадёт у читателя из
    другого потока. -> число удалённых ключей."""
    now = time.time() if now is None else now
    stale = [k for k, t in list(ts.items()) if now - t > max_age]
    for k in stale:
        ts.pop(k, None)
        for store in stores:
            store.pop(k, None)
    return len(stale)
