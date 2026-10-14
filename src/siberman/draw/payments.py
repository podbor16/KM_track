"""
Статусы оплаты победителей жеребьёвки. Директор ставит ❌ → система ставит ⏳ первому
в листе ожидания того же зачёта без статуса (предложение пользователя 2026-10-14);
только до auto_invite_until (правила: передача очереди до 1 января), дальше — вручную.
"""
import datetime

PAYMENT_ICONS = {"none": "", "pending": "⏳", "paid": "✅", "unpaid": "❌"}


def next_invitee(rows: list[dict]) -> dict | None:
    """Первый в листе ожидания зачёта без статуса оплаты."""
    return next((r for r in rows if r["section"] == "waitlist" and r["payment_status"] == "none"), None)


def auto_invite_allowed(until: datetime.date | None, today: datetime.date) -> bool:
    return until is None or today < until
