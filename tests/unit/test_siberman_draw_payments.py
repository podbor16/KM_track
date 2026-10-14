import datetime

from src.siberman.draw.payments import PAYMENT_ICONS, auto_invite_allowed, next_invitee


def row(pos, section, status="none"):
    return {"position": pos, "section": section, "payment_status": status, "applicant_id": pos}


def test_next_invitee_first_waitlist_without_status():
    rows = [row(1, "winner", "unpaid"), row(2, "waitlist", "pending"), row(3, "waitlist"), row(4, "waitlist")]
    assert next_invitee(rows)["position"] == 3
    assert next_invitee([row(1, "winner")]) is None


def test_auto_invite_deadline():
    until = datetime.date(2027, 1, 1)
    assert auto_invite_allowed(until, datetime.date(2026, 12, 31)) is True
    assert auto_invite_allowed(until, datetime.date(2027, 1, 1)) is False
    # NULL-дата = автопередача выключена (раньше значила бессрочную — опасно при частичном сохранении)
    assert auto_invite_allowed(None, datetime.date(2030, 1, 1)) is False


def test_icons():
    assert PAYMENT_ICONS == {"none": "", "pending": "⏳", "paid": "✅", "unpaid": "❌"}
