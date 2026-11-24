from datetime import date, datetime


def parse_race_birthdate(value: object) -> date | None:
    """Accept an ISO date/timestamp or DD.MM.YYYY from race imports."""
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        raw = value.strip()
        try:
            if "." in raw and len(raw) == 10:
                value = datetime.strptime(raw, "%d.%m.%Y").date()
            else:
                value = datetime.fromisoformat(raw).date()
        except ValueError:
            return None
    if isinstance(value, date) and 1000 <= value.year and value <= date.today():
        return value
    return None
