"""Подготовка непишущего в БД черновика шансов жеребьёвки Siberman."""
import io
import json
from collections.abc import Set
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.siberman.draw.importer import (
    CALCULATION_APPROVED, CALCULATION_CHECK, COL_CITY, COL_FORMAT, COL_NAME, COL_SEX, COL_TOTAL, COL_EXTRA, COL_WILDCARD,
    COL_ENTRY_ID, EXTRA_COLS, RELAY_COLS,
)
from src.siberman.persons.linking import plain_key

READY_COLUMN = CALCULATION_CHECK
READY_VALUE = CALCULATION_APPROVED
NOT_READY_VALUE = "ПРОВЕРИТЬ"
LOCALITIES_PATH = Path(__file__).resolve().parents[3] / "data" / "siberman" / "draw_localities.json"

MAIN_COLUMNS = (COL_FORMAT, COL_NAME, COL_SEX, COL_CITY, COL_WILDCARD,
                *EXTRA_COLS.values(), COL_EXTRA, COL_TOTAL, *RELAY_COLS.values(), READY_COLUMN, COL_ENTRY_ID)
EXTRA_LABELS = {"starts_individual": EXTRA_COLS["starts_individual"],
                "starts_relay": EXTRA_COLS["starts_relay"],
                "draw_accumulated": EXTRA_COLS["draw_accumulated"],
                "is_local": EXTRA_COLS["is_local"],
                "duathlon_222": EXTRA_COLS["duathlon_222"],
                "race_24h": EXTRA_COLS["race_24h"],
                "tattoo": EXTRA_COLS["tattoo"]}


def norm_city(value: str) -> str:
    text = (value or "").lower().replace("ё", "е").strip()
    for prefix in ("город ", "г. ", "г "):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return " ".join(text.split())


def load_localities(path: Path = LOCALITIES_PATH) -> dict:
    """Curated locality-to-subject data. Unknown and explicitly ambiguous values stay unresolved."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for region, rows in raw.get("regions", {}).items():
        for row in rows:
            for alias in (row["name"], *row.get("aliases", [])):
                out[norm_city(alias)] = region
    for name in raw.get("known_nonlocal", []):
        out[norm_city(name)] = "other"
    for name in raw.get("review", []):
        out[norm_city(name)] = None
    return out


def local_value(city: str, regions: dict) -> tuple[int | None, str]:
    key = norm_city(city)
    if not key:
        return None, "город не указан"
    region = regions.get(key, "__unknown__")
    if region == "Красноярский край" or region == "Хакасия":
        return 1, region
    if region == "other":
        return 0, "населённый пункт вне целевых регионов"
    if region is None:
        return None, "неоднозначное написание города"
    return None, "населённый пункт не классифицирован"


def as_count(value) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return int(value)
        if value.endswith(".0") and value[:-2].isdigit():
            return int(value[:-2])
    return None


def form_reported(raw: dict, key: str) -> int | None:
    """Read only the explicit scalar self-report fields from the stored Tilda payload."""
    return as_count(raw.get(key))


def external_start_bonus(rows: list[dict] | None, *, race: str, name_key: str, birthdate: date | None,
                         reported: int | None, through_year: int,
                         links: Set[tuple[int, int]] = frozenset(),
                         assigned_elsewhere: Set[tuple[int, int]] = frozenset()) -> tuple[int | None, str, str | None]:
    if rows is None:
        return None, race, f"{race}: база результатов недоступна"
    history = [row for row in rows if row["race_year"] is not None and int(row["race_year"]) <= through_year]
    years = ", ".join(str(year) for year in sorted({int(row["race_year"]) for row in history}))
    source = f"{race}, протоколы: {years}" if years else race
    if not history:
        return None, source, f"{race}: нет протоколов до года жеребьёвки включительно"
    linked = {row["event_id"]: int(row["race_year"]) for row in history
              if (row["event_id"], row.get("result_id")) in links}
    if birthdate is None and not linked:
        return None, source, f"{race}: нужна подтверждённая личность с датой рождения"

    matches = []
    identity_conflict = False
    for row in history:
        if plain_key(row["surname"], row["name"]) != name_key:
            continue
        if not row.get("is_team") and (row["event_id"], row.get("result_id")) in assigned_elsewhere:
            identity_conflict |= birthdate is not None and row["birthdate"] == birthdate
        else:
            matches.append(row)
    confirmed = {row["event_id"]: int(row["race_year"]) for row in matches
                 if birthdate is not None and row["birthdate"] == birthdate}
    confirmed.update(linked)
    uncertain = [row for row in matches if (birthdate is None or row["birthdate"] is None)
                 and row["event_id"] not in confirmed]
    count = len(confirmed)
    source += f"; подтверждено стартов: {count}"
    if confirmed:
        source += ". Подтверждены старты за " + ", ".join(map(str, sorted(confirmed.values())))
    if linked:
        source += ". По подтверждённой связи с карточкой: " + ", ".join(map(str, sorted(linked.values())))
    if links - {(row["event_id"], row.get("result_id")) for row in rows}:
        return None, source, f"{race}: отсутствует ранее подтверждённый результат"
    if identity_conflict:
        return None, source, f"{race}: личный результат с совпадающей датой рождения привязан к другой карточке"
    if uncertain:
        pending_years = ", ".join(str(year) for year in sorted({int(row["race_year"]) for row in uncertain}))
        if all(row.get("relay_member") for row in uncertain):
            return None, source, f"{race}: найдено совпадение в составе эстафеты за {pending_years}; подтвердите личность"
        return None, source, f"{race}: возможные старты без даты рождения за {pending_years}"
    if reported is not None and reported != count:
        return (count or None), source, f"{race}: в заявке {reported}, в протоколах подтверждено {count}"
    if count:
        return count, source, None
    if reported == 0:
        return 0, source + "; в заявке указано 0", None
    return None, source, f"{race}: совпадений нет и в заявке не указано число стартов"


def next_accumulated(current: int, section: str | None, invited: bool, payment_status: str,
                     started: bool | None) -> tuple[int | None, str]:
    """Apply one completed lottery outcome. started=None means the race result is not covered."""
    if section == "winner" or invited:
        if payment_status == "unpaid":
            return current, "победил/получил предложение, не оплатил — без изменения"
        if payment_status != "paid":
            return None, "победил/получил предложение, итог оплаты не зафиксирован"
        if started is None:
            return None, "оплата есть, но факт старта не установлен"
        return (0, "оплатил и стартовал — накопленное обнулено") if started else (
            current + 1, "оплатил, но не стартовал — +1")
    return current + 1, "не выиграл / слот не предложен — +1"


def build_workbook(rows: list[dict]) -> bytes:
    """Create organizer-compatible main sheet plus a source/mismatch audit sheet."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Спец вставка"
    ws.append(list(MAIN_COLUMNS))
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=1, column=MAIN_COLUMNS.index(READY_COLUMN) + 1).comment = Comment(
        "Пока стоит ПРОВЕРИТЬ, этот файл не загрузится в жеребьёвку. Заполните пропуски и поставьте "
        "ПРОВЕРЕНО после проверки источников.", "KM_track")

    review = wb.create_sheet("Проверка расчёта")
    review.append(["Участник", "Формат", "Показатель", "Расчёт", "Ответ в заявке / прежняя таблица",
                   "Источник", "Результат проверки", COL_ENTRY_ID])
    for cell in review[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    warn_fill = PatternFill("solid", fgColor="FFF2CC")
    bad_fill = PatternFill("solid", fgColor="FCE4D6")
    ready_fill = PatternFill("solid", fgColor="E2F0D9")
    bonus_columns = {key: MAIN_COLUMNS.index(label) + 1 for key, label in EXTRA_COLS.items()}
    first_bonus = get_column_letter(min(bonus_columns.values()))
    last_bonus = get_column_letter(max(bonus_columns.values()))
    extra_col = MAIN_COLUMNS.index(COL_EXTRA) + 1
    total_col = MAIN_COLUMNS.index(COL_TOTAL) + 1
    for item in rows:
        checks = item.get("issues", [])
        extras = item["extras"]
        complete = not checks and all(as_count(extras.get(k)) is not None for k in EXTRA_COLS)
        values = {
            COL_FORMAT: "Эстафетная команда" if item["format"] == "relay" else "Индивидуальное участие",
            COL_NAME: item["fio"], COL_SEX: {"M": "Мужской", "F": "Женский"}.get(item.get("gender"), ""),
            COL_CITY: item.get("city") or "", COL_WILDCARD: "",
            READY_COLUMN: READY_VALUE if complete else NOT_READY_VALUE,
            COL_ENTRY_ID: item.get("entry_id"),
        }
        values.update({EXTRA_COLS[k]: as_count(extras.get(k)) for k in EXTRA_COLS})
        values.update({RELAY_COLS[k]: item.get(f"relay_{k}") or "" for k in RELAY_COLS})
        ws.append([values.get(col, "") for col in MAIN_COLUMNS])
        for cell in ws[ws.max_row]:
            if cell.data_type == "f":
                cell.data_type = "s"
        row_no = ws.max_row
        bonus_range = f"{first_bonus}{row_no}:{last_bonus}{row_no}"
        extra_cell = ws.cell(row=row_no, column=extra_col)
        extra_cell.value = f'=IF(COUNT({bonus_range})={len(bonus_columns)},SUM({bonus_range}),"")'
        extra_cell.comment = Comment(
            "Сумма дополнительных шансов. Формула считает сумму после заполнения всех колонок с бонусами.",
            "KM_track",
        )
        total_cell = ws.cell(row=row_no, column=total_col)
        total_cell.value = f'=IF(ISNUMBER({extra_cell.coordinate}),{extra_cell.coordinate}+1,"")'
        total_cell.comment = Comment("Один базовый шанс плюс сумма дополнительных шансов.", "KM_track")
        ready_cell = ws.cell(row=row_no, column=MAIN_COLUMNS.index(READY_COLUMN) + 1)
        ready_cell.fill = ready_fill if complete else bad_fill
        ready_cell.comment = Comment(
            "Все показатели рассчитаны и сверены." if complete else "\n".join(checks) or "Заполните недостающие показатели.",
            "KM_track",
        )

        for key, label in EXTRA_LABELS.items():
            result = as_count(extras.get(key))
            reported = item.get("reported", {}).get(key)
            source = item.get("sources", {}).get(key, "неизвестно")
            reason = item.get("field_issues", {}).get(key)
            confirmation = item.get("review_notes", {}).get(key)
            note = source
            if reason:
                note += f"\nНа проверке — {reason}."
            if reported is not None and reported != result:
                note += f"\nСверка с анкетой: указано {reported}, в базе подтверждено {result if result is not None else 'нет данных'}."
            if confirmation:
                note += f"\nРешение организатора: {confirmation}."
            ws.cell(row_no, bonus_columns[key]).comment = Comment(note, "KM_track", width=350, height=120)
            if result is None:
                verdict = "НЕТ ДАННЫХ" + (f": {reason}" if reason else "")
            elif confirmation:
                verdict = f"ПОДТВЕРЖДЕНО: в анкете {reported}, по БД {result}. {confirmation}"
            elif reported is not None and reported != result:
                verdict = f"РАСХОЖДЕНИЕ: {reported} → {result}"
            elif reason:
                verdict = f"ПРОВЕРИТЬ: {reason}"
            else:
                verdict = "совпадает / рассчитано"
            review.append([item["fio"], values[COL_FORMAT], label, result if result is not None else "",
                           reported if reported is not None else "", source, verdict,
                           item.get("entry_id")])
            if result is None or reason or (reported is not None and reported != result):
                for cell in review[review.max_row]:
                    cell.fill = bad_fill if result is None else warn_fill

    for i, title in enumerate(MAIN_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = min(42, max(14, len(title) + 3))
    for i, width in enumerate((28, 22, 36, 14, 20, 32, 60, 19), start=1):
        review.column_dimensions[get_column_letter(i)].width = width
    for sheet in (ws, review):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    wb.calculation.fullCalcOnLoad = True
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
