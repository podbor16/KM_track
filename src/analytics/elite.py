"""
«Элита» — элитный кластер (решения пользователя 2026-10-06). Пока только Жара 21,1 км.

У элитного спортсмена настоящий уникальный номер (по нему открывается диплом), на сайте
вместо номера — «Элита» (results.is_elite / leads.is_elite). Результат — элита, если в bib
Copernico «Элита» (или фамилия — именной номер, Жара 2025: номер тогда служебный, как у
замыкающих) или номер вне основных диапазонов дистанции из «Присвоить номера» (bib_ranges).
Диапазоны не заданы — по номеру элита не определяется.
"""

ELITE_DISTANCES = {("Жара", "21.1 км")}


def distance_label(km) -> str:
    """events.event_distance (21.1) → формат leads/bib_ranges («21.1 км»)."""
    return f"{float(km):g} км"


def is_elite_text(dorsal) -> bool:
    return "элит" in str(dorsal or "").lower()


def main_ranges(cur, event_name, distance) -> list:
    """[(start, end)] — основные диапазоны номеров дистанции; [] — не элитный кластер или не заданы."""
    if (event_name, distance) not in ELITE_DISTANCES:
        return []
    cur.execute("SELECT range_start, range_end FROM bib_ranges WHERE event_name = %s AND distance = %s",
                (event_name, distance))
    return [(int(r[0]), int(r[1])) if not isinstance(r, dict) else (int(r["range_start"]), int(r["range_end"]))
            for r in cur.fetchall()]


def _norm(text) -> str:
    return str(text or "").strip().lower().replace("ё", "е")


def is_elite(dorsal, ranges, surname=None) -> bool:
    """dorsal — bib из Copernico/протокола как есть; ranges — main_ranges(). Текст в bib —
    элита, только если это «Элита» или фамилия участника (именной номер); «Зам» (замыкающий) — нет."""
    raw = str(dorsal or "").strip()
    if not raw.isdigit():
        return is_elite_text(raw) or (bool(surname) and _norm(raw) == _norm(surname))
    return bool(ranges) and not any(s <= int(raw) <= e for s, e in ranges)
