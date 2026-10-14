import io

import openpyxl
import pytest

from src.siberman.draw.importer import import_report, parse_applicants

HEADER = [
    "format", "surname Name", "sex", "city (исправлено)", "Wildcard",
    "Старты на гонке (индивидуально)", "Старты на гонке (эстафета)",
    "Накопленные шансы за участия в жеребьёвке", "Карточка для местных атлетов",
    "Участие в 222 Дуатлоне", "Участие в суточной велогонке 24часа", "Тату Siberman",
    "Сумма дополнительных шансов", "Общая сумма шансов", "Участвует 2027", "wildcard_reason",
    "Расскажите_о_ваших_результатах", "surname_swim", "name_swim", "surname_bike", "name_bike",
    "surname_run", "name_run",
]


def _row(fmt, full, sex, wc=None, starts=0, relay_starts="", accum="", extra_sum=None, total=None, swim=("", "")):
    extra = sum(v for v in (starts, relay_starts, accum) if isinstance(v, int))  # «два» — проверка ошибки
    extra_sum = extra if extra_sum is None else extra_sum
    total = extra_sum + 1 if total is None else total
    return [fmt, full, sex, "Красноярск", wc, starts or "", relay_starts, accum, None, "", "", "",
            extra_sum, total, None, "причина" if wc else None, "результаты",
            swim[0], swim[1], "Вело", "Велосипедист", "Бег", "Бегун"]


def _xlsx(rows, header=HEADER):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Спец вставка"
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_pools_and_fields():
    apps, errors = parse_applicants(_xlsx([
        _row("Индивидуальное участие", "Русскин Дмитрий", "Мужской", wc="Wildcard", starts=7),
        _row("Индивидуальное участие", "Акулич Степан", "Мужской", starts=3, accum=1),
        _row("Индивидуальное участие", "Новикова Анна", "Женский"),
        _row("Эстафетная команда", "Летницкий Дмитрий", None, relay_starts=2, swim=("Летницкий", "Дмитрий")),
        _row("Индивидуальное участие", "Баранов Роман", "Мужской", wc="!", starts=1),
    ]))
    assert errors == []
    by = {a["surname"]: a for a in apps}
    assert by["Русскин"]["pool"] == "wildcard" and by["Русскин"]["is_wildcard"] is True
    assert by["Акулич"]["pool"] == "repeat" and by["Акулич"]["chances"] == 5
    assert by["Новикова"]["pool"] == "novice" and by["Новикова"]["gender"] == "F"
    assert by["Летницкий"]["pool"] == "relay" and by["Летницкий"]["gender"] is None
    assert by["Летницкий"]["relay_swim"] == "Летницкий Дмитрий"
    assert by["Летницкий"]["relay_bike"] == "Вело Велосипедист"
    # «!» — организаторы решили не давать wild card: обычный участник
    assert by["Баранов"]["pool"] == "repeat" and by["Баранов"]["is_wildcard"] is False
    assert by["Акулич"]["name"] == "Степан" and by["Акулич"]["results_text"] == "результаты"


def test_chances_mismatch_is_error():
    apps, errors = parse_applicants(_xlsx([
        _row("Индивидуальное участие", "Иванов Иван", "Мужской", starts=2, total=5),
    ]))
    assert apps == [] and "шансы не сходятся" in errors[0]


def test_missing_sex_duplicate_and_bad_number():
    apps, errors = parse_applicants(_xlsx([
        _row("Индивидуальное участие", "Без Пола", None),
        _row("Индивидуальное участие", "Дубль Один", "Мужской"),
        _row("Индивидуальное участие", "Дубль Один", "Мужской"),
        _row("Индивидуальное участие", "Кривой Номер", "Мужской", starts="два"),
    ]))
    assert [a["surname"] for a in apps] == ["Дубль"]
    joined = " | ".join(errors)
    assert "пол" in joined and "повтор заявки" in joined and "не целое число" in joined


def test_missing_column():
    apps, errors = parse_applicants(_xlsx([], header=HEADER[:5]))
    assert apps == [] and errors[0].startswith("нет колонок")


def test_report_counts_people_and_balls():
    apps, _ = parse_applicants(_xlsx([
        _row("Индивидуальное участие", "Акулич Степан", "Мужской", starts=3),
        _row("Индивидуальное участие", "Новикова Анна", "Женский"),
        _row("Эстафетная команда", "Капитан Один", None),
    ]))
    rep = import_report(apps)
    assert rep["total"] == 3
    assert rep["groups"] == {"repeat_M": {"people": 1, "balls": 4},
                             "novice_F": {"people": 1, "balls": 1},
                             "relay": {"people": 1, "balls": 1}}


IND = "Индивидуальное участие"


@pytest.mark.parametrize("wc", ["Wildcard", "wildcard", "Wild card", "WILDCARD", " wild  card "])
def test_wildcard_case_and_spaces(wc):
    apps, errors = parse_applicants(_xlsx([_row(IND, "Иванов Иван", "Мужской", wc=wc)]))
    assert errors == [] and apps[0]["is_wildcard"] is True and apps[0]["pool"] == "wildcard"


def test_wildcard_unknown_value_is_error():
    apps, errors = parse_applicants(_xlsx([_row(IND, "Иванов Иван", "Мужской", wc="возможно")]))
    assert apps == [] and "«Wildcard» — непонятное значение «возможно»" in errors[0]


def test_number_error_names_column():
    _, errors = parse_applicants(_xlsx([_row(IND, "Кривой Номер", "Мужской", starts="два")]))
    assert errors == ["строка 2 «Кривой Номер»: «Старты на гонке (индивидуально)» — не целое число: «два»"]


def test_number_error_in_total_column():
    row = _row(IND, "Кривой Номер", "Мужской", total="много")
    _, errors = parse_applicants(_xlsx([row]))
    assert "«Общая сумма шансов» — не целое число: «много»" in errors[0]


def test_blank_float_whole_values_ok():
    row = _row(IND, "Иванов Иван", "Мужской", starts=2.0, accum="   ", extra_sum=2, total=3)
    apps, errors = parse_applicants(_xlsx([row]))
    assert errors == [] and apps[0]["starts_individual"] == 2 and apps[0]["draw_accumulated"] == 0


@pytest.mark.parametrize("bad", [2.5, -1, "-1", "2.5"])
def test_fractional_and_negative_are_errors(bad):
    row = _row(IND, "Иванов Иван", "Мужской", starts=bad, extra_sum=0, total=1)
    apps, errors = parse_applicants(_xlsx([row]))
    assert apps == [] and "не целое число ≥ 0" in errors[0]


def test_total_below_one_is_error():
    row = _row(IND, "Иванов Иван", "Мужской", extra_sum=-1, total=0)
    apps, errors = parse_applicants(_xlsx([row]))
    assert apps == [] and errors


def test_total_zero_is_error():
    row = _row(IND, "Иванов Иван", "Мужской", extra_sum=0, total=0)
    apps, errors = parse_applicants(_xlsx([row]))
    assert apps == [] and errors


def test_duplicate_ignores_yo_and_case():
    apps, errors = parse_applicants(_xlsx([
        _row(IND, "Королёв Пётр", "Мужской"),
        _row(IND, "королев петр", "Мужской"),
    ]))
    assert len(apps) == 1 and "повтор заявки" in errors[0]


def test_single_word_name_is_error():
    apps, errors = parse_applicants(_xlsx([_row(IND, "Иванов", "Мужской")]))
    assert apps == [] and "нет имени" in errors[0]


def test_inner_spaces_collapsed():
    apps, _ = parse_applicants(_xlsx([_row(IND, "Иванов   Иван", "Мужской")]))
    assert apps[0]["surname"] == "Иванов" and apps[0]["name"] == "Иван"


def test_not_xlsx():
    assert parse_applicants(b"not a zip") == (
        [], ["файл не похож на .xlsx — сохраните таблицу в формате Excel"])
