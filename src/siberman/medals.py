"""Медали Siberman за финиши (спецификация hall §9) — одно место для правила «N-й финиш → медаль».
8-й и дальше — пока как 7-й. Картинки медалей добавит страница спортсмена (план 4)."""
from typing import Optional

INDIVIDUAL = {
    1: ("silver", "Античное серебро", "#a9a9a9"),
    2: ("black", "Матовая чёрная", "#222222"),
    3: ("gold", "Золотая", "#d4a017"),
    4: ("copper", "Античная медь", "#b06a3b"),
    5: ("chameleon", "Хамелеон", "linear-gradient(135deg, #6a3cbc, #1fa3a3, #c2b21f)"),
    6: ("hex_black", "Чёрный шестигранник", "#111111"),
}
SEVENTH_AND_LATER = ("hex_silver_red", "Серебряный шестигранник с красной плашкой", "#c0c0c0")
RELAY = ("relay_silver", "Античное серебро 70 мм (эстафета)", "#a9a9a9")


def medal_for(finish_no: Optional[int], relay: bool = False) -> Optional[dict]:
    """Медаль за finish_no-й финиш в личном зачёте; relay=True — эстафетная. Нет финиша → None."""
    if relay:
        key, name, color = RELAY
    elif not finish_no or finish_no < 1:
        return None
    else:
        key, name, color = INDIVIDUAL.get(finish_no, SEVENTH_AND_LATER)
    return {"key": key, "name": name, "color": color}
