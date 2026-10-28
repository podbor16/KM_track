"""Медали Siberman за финиши (спецификация hall §9) — одно место для правила «N-й финиш → медаль».
1–5 — круглые, 6–10 — шестигранники тех же цветов в том же порядке; 11-й и дальше — пока как 10-й.
Картинка — static/img/siberman/medals/{key}.webp, если файл есть (новый файл — после перезапуска); иначе страница рисует кружок цвета медали."""
import functools
from pathlib import Path
from typing import Optional

MEDALS_DIR = Path(__file__).resolve().parents[2] / "static" / "img" / "siberman" / "medals"

_COLORS = (("silver", "Серебряная", "Серебряный", "#a9a9a9"),
           ("black", "Чёрная", "Чёрный", "#222222"),
           ("gold", "Золотая", "Золотой", "#d4a017"),
           ("copper", "Медная", "Медный", "#b06a3b"),
           ("chameleon", "Хамелеон", "Хамелеон", "linear-gradient(135deg, #6a3cbc, #1fa3a3, #c2b21f)"))
INDIVIDUAL = {
    **{i: (key, disc, color) for i, (key, disc, _, color) in enumerate(_COLORS, start=1)},
    **{i: (f"hex_{key}", f"{hex_} шестигранник", color) for i, (key, _, hex_, color) in enumerate(_COLORS, start=6)},
}
LAST = INDIVIDUAL[max(INDIVIDUAL)]
RELAY = ("relay_silver", "Серебряная", "#a9a9a9")


@functools.lru_cache(maxsize=None)
def _image(medals_dir: Path, key: str):
    return f"/static/img/siberman/medals/{key}.webp" if (medals_dir / f"{key}.webp").exists() else None


def medal_for(finish_no: Optional[int], relay: bool = False) -> Optional[dict]:
    """Медаль за finish_no-й финиш в личном зачёте; relay=True — эстафетная. Нет финиша → None."""
    if relay:
        key, name, color = RELAY
    elif not finish_no or finish_no < 1:
        return None
    else:
        key, name, color = INDIVIDUAL.get(finish_no, LAST)
    return {"key": key, "name": name, "color": color, "image": _image(MEDALS_DIR, key)}
