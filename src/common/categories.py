"""
Единый краткий вид возрастных категорий результатов (решение пользователя 2026-10-06).

Copernico и протоколы организаторов называют одно и то же по-разному: «мужчины до 49 лет
(1976 г.р. и младше)», «М 49», «женщины 65 лет и старше (1960 г.р. и старше)», «Ж 50-59».
Канон — как у Жары и возрастных групп /admin: «М49», «Ж50-59», «Ж65+», «М12-49».
Не меняются: детские «Мальчики 2015 г.р.» (как в Copernico, решение 2026-10-06),
«Женщины»/«Мужчины» (Снежная семёрка — зачёт только по полу), «Unknown», пусто.
Годы в скобках отбрасываются — они бывают ошибочными, возраст однозначен.
"""

import re

_PARENS = re.compile(r"\s*\(.*?\)")
_KIDS = re.compile(r"^(мальчики|девочки)\s*(\d{4})\s*г\.?\s*р\.?$", re.I)
_AGE = re.compile(r"^(мужчины|женщины|м|ж|m)\s*(до\s*)?(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s*(?:лет|года|год)?\s*(и\s*старше|\+)?$")


def canonical_category(category) -> str:
    raw = str(category or "").strip()
    base = _PARENS.sub("", raw).strip()
    low = base.lower()
    if low in ("", "unknown"):
        return raw
    if m := _KIDS.match(base):
        return f"{m.group(1).capitalize()} {m.group(2)} г.р."
    if low in ("женщины", "мужчины"):
        return low.capitalize()
    m = _AGE.match(low)
    if not m:
        return raw
    sex = "Ж" if low.startswith("ж") else "М"
    low_age, high_age = m.group(3), m.group(4)
    if m.group(5):
        return f"{sex}{low_age}+"
    return f"{sex}{low_age}-{high_age}" if high_age else f"{sex}{low_age}"


# Группы по возрасту в год старта для протоколов без категорий (Женская семёрка 2025) —
# как в Copernico 2026 у той же дистанции
def age_category(sex_letter: str, age: int, bounds=(49, 59, 64, 69, 74, 79)) -> str:
    if age <= bounds[0]:
        return f"{sex_letter}{bounds[0]}"
    lo = bounds[0] + 1
    for hi in bounds[1:]:
        if age <= hi:
            return f"{sex_letter}{lo}-{hi}"
        lo = hi + 1
    return f"{sex_letter}{lo}+"
