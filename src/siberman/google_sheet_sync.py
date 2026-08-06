"""
Live-синхронизация данных Siberman из Google-таблицы (альтернатива ручной
Excel-загрузке, переключается в админке) — источник байтов другой
(публичный .xlsx-экспорт Google Sheets вместо загруженного файла), но
формат и парсер — ТЕ ЖЕ, что для ручной загрузки (parser.py:parse_excel,
не изменён).

НЕ использует apply_to_db()/clear_race_year() — по тем же причинам, что и
copernico_run.py (autocommit=True делает DELETE видимым немедленно,
публичная страница "мигнула" бы пустой таблицей на каждом цикле опроса).
См. apply_parse_result_upsert() в service.py.

⚠ Пока live-синхронизация включена — не запускать ручную Excel-загрузку
для этого года (apply_to_db() полностью пересоздаёт участников и сотрёт
результат последнего цикла синхронизации). Это то же операционное
ограничение, что и для Copernico (copernico_run.py) — оба источника
переключаются одним и тем же принципом "включён только один одновременно".
"""
import hashlib
import logging
import re
from typing import Optional

import requests

from src.siberman.db import get_google_sheet_config, set_google_sheet_last_hash
from src.siberman.parser import parse_excel
from src.siberman.service import apply_parse_result_upsert

log = logging.getLogger(__name__)

_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")


def extract_sheet_id(url_or_id: str) -> str:
    """Принимает полный URL гугл-таблицы (.../spreadsheets/d/ID/edit...)
    или уже голый ID — возвращает чистый ID."""
    url_or_id = url_or_id.strip()
    m = _SHEET_ID_RE.search(url_or_id)
    return m.group(1) if m else url_or_id


def fetch_sheet_xlsx(sheet_id: str) -> bytes:
    """Скачать .xlsx-экспорт публичной (доступной по ссылке, без входа в
    аккаунт) Google-таблицы. Если доступ ограничен, Google вместо файла
    отдаёт HTML-страницу входа — ловим это по Content-Type и превращаем в
    понятную ошибку, а не в битый .xlsx, который молча провалит парсинг."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    resp = requests.get(url, timeout=(10, 30))
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    if "html" in content_type.lower():
        raise ValueError(
            "Google вернул страницу входа вместо .xlsx — таблица недоступна по "
            "ссылке. Откройте доступ: «Настройки доступа» → «Все, у кого есть "
            "ссылка» → «Читатель»."
        )
    return resp.content


def sync_google_sheet(conn, race_year: int) -> dict:
    """Проверить флаг в админке, скачать таблицу, применить в БД, если
    содержимое изменилось с прошлого успешного цикла (sha256 сравнивается
    с race_config.google_sheet_last_hash — хранится в БД, переживает
    рестарт поллер-процесса, чтобы не переприменять неизменившиеся данные
    на каждом цикле опроса)."""
    cfg = get_google_sheet_config(conn, race_year)
    if not cfg["enabled"]:
        return {"ok": True, "enabled": False, "changed": False}
    if not cfg["sheet_id"]:
        log.warning(f"google_sheet_sync включён для race_year={race_year}, но ID таблицы не задан")
        return {"ok": False, "error": "sheet_id not set"}

    try:
        xlsx_bytes = fetch_sheet_xlsx(cfg["sheet_id"])
    except Exception as e:
        log.warning(f"Не удалось скачать Google-таблицу: {e}")
        return {"ok": False, "error": str(e)}

    sheet_hash = hashlib.sha256(xlsx_bytes).hexdigest()
    if sheet_hash == cfg["last_hash"]:
        return {"ok": True, "enabled": True, "changed": False}

    result = parse_excel(xlsx_bytes, race_year)
    if result.errors:
        log.warning(f"Google-таблица {race_year}: {len(result.errors)} ошибок парсинга — применяю, что распозналось")

    apply_result = apply_parse_result_upsert(conn, result)
    set_google_sheet_last_hash(conn, race_year, sheet_hash)

    return {
        "ok": True,
        "enabled": True,
        "changed": True,
        "parse_errors": len(result.errors),
        **apply_result,
    }
