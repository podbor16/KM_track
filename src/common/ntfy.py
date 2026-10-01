"""Уведомления ntfy (NTFY_URL из .env).

urllib/http.client кодируют заголовки в latin-1 — кириллица в Title падает с
UnicodeEncodeError ещё до отправки (так молча терялись алерты мониторинга).
ntfy понимает RFC 2047: «=?UTF-8?B?…?=».
"""

import base64
import logging
import os
import urllib.request

_log = logging.getLogger(__name__)


def header_value(text: str) -> str:
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return "=?UTF-8?B?" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "?="


def send(title: str, lines, tags: str = "warning", priority: str = "default") -> bool:
    """Отправить уведомление; без NTFY_URL или при ошибке сети — False (не бросает)."""
    url = os.environ.get("NTFY_URL", "")
    if not url:
        _log.info("ntfy: NTFY_URL не задан — уведомление не отправлено")
        return False
    req = urllib.request.Request(url, data="\n".join(lines).encode("utf-8"), method="POST")
    req.add_header("Title", header_value(title))
    req.add_header("Tags", tags)
    req.add_header("Priority", priority)
    req.add_header("Content-Type", "text/plain; charset=utf-8")
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        _log.warning(f"ntfy: ошибка отправки: {e}")
        return False
