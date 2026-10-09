"""
Количество ФИНИШЕЙ Siberman в личном зачёте ДО конкретного года гонки.

Считается только из БД (все годы с 2016 — архив загружен
scripts/siberman_import_history.py): годы, где личник дошёл до финиша
бега (см. db.get_finished_years_by_name). Год просмотра и более поздние
не считаются — при просмотре архива 2025 сам 2025 ещё не "прошлый" финиш.

Связи по ID между годами нет — человек узнаётся по "фамилия имя"
(person_key). PERSON_ALIASES — один человек под разными написаниями в
протоколах разных лет (смена фамилии и т.п.).
"""

PERSON_ALIASES: dict[str, str] = {
    # Сменила фамилию: 2024 — «Заволокина Олеся», в рейтинге организатора —
    # «Князева (Заволокина) Олеся».
    "заволокина олеся": "князева олеся",
    "князева заволокина олеся": "князева олеся",
}


def person_key(surname: str, name: str) -> str:
    """"фамилия имя": нижний регистр, ё→е, без скобок и лишних пробелов,
    с учётом PERSON_ALIASES."""
    raw = f"{surname} {name}".lower().replace("ё", "е").replace("(", " ").replace(")", " ")
    key = " ".join(raw.split())
    return PERSON_ALIASES.get(key, key)


def get_finish_count(
    surname: str,
    name: str,
    race_year: int,
    finished_years_by_name: dict[str, set[int]],
) -> int:
    """Сколько раз участник финишировал ДО race_year — годы из
    finished_years_by_name (ключ — person_key), строго меньше race_year."""
    years = finished_years_by_name.get(person_key(surname, name), ())
    return sum(1 for y in years if y < race_year)
