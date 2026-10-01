"""Уведомления ntfy: значения заголовков HTTP.

urllib/http.client кодируют заголовки в latin-1 — кириллица в Title падает с
UnicodeEncodeError ещё до отправки (так молча терялись алерты мониторинга).
ntfy понимает RFC 2047: «=?UTF-8?B?…?=».
"""

import base64


def header_value(text: str) -> str:
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return "=?UTF-8?B?" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "?="
