"""Подготовка непишущего в БД черновика шансов жеребьёвки Siberman."""
import io
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.siberman.draw.importer import (
    CALCULATION_APPROVED, CALCULATION_CHECK, COL_CITY, COL_FORMAT, COL_NAME, COL_SEX, COL_TOTAL, COL_EXTRA, COL_WILDCARD,
    EXTRA_COLS, RELAY_COLS,
)

READY_COLUMN = CALCULATION_CHECK
READY_VALUE = CALCULATION_APPROVED
NOT_READY_VALUE = "ПРОВЕРИТЬ"
LOCALITIES_PATH = Path(__file__).resolve().parents[3] / "data" / "siberman" / "draw_localities.json"

MAIN_COLUMNS = (COL_FORMAT, COL_NAME, COL_SEX, COL_CITY, COL_WILDCARD,
                *EXTRA_COLS.values(), COL_EXTRA, COL_TOTAL, *RELAY_COLS.values(), READY_COLUMN)
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


def build_workbook(rows: list[dict], global_issues: list[str]) -> bytes:
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
                   "Источник", "Результат проверки"])
    for cell in review[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    warn_fill = PatternFill("solid", fgColor="FFF2CC")
    bad_fill = PatternFill("solid", fgColor="FCE4D6")
    ready_fill = PatternFill("solid", fgColor="E2F0D9")
    for item in rows:
        checks = list(global_issues) + list(item.get("issues", []))
        extras = item["extras"]
        complete = not checks and all(as_count(extras.get(k)) is not None for k in EXTRA_COLS)
        total_extra = sum(as_count(extras[k]) for k in EXTRA_COLS) if complete else None
        values = {
            COL_FORMAT: "Эстафетная команда" if item["format"] == "relay" else "Индивидуальное участие",
            COL_NAME: item["fio"], COL_SEX: {"M": "Мужской", "F": "Женский"}.get(item.get("gender"), ""),
            COL_CITY: item.get("city") or "", COL_WILDCARD: "",
            COL_EXTRA: total_extra, COL_TOTAL: total_extra + 1 if total_extra is not None else None,
            READY_COLUMN: READY_VALUE if complete else NOT_READY_VALUE,
        }
        values.update({EXTRA_COLS[k]: as_count(extras.get(k)) for k in EXTRA_COLS})
        values.update({RELAY_COLS[k]: item.get(f"relay_{k}") or "" for k in RELAY_COLS})
        ws.append([values.get(col, "") for col in MAIN_COLUMNS])
        for cell in ws[ws.max_row]:
            if cell.data_type == "f":
                cell.data_type = "s"
        ready_cell = ws.cell(row=ws.max_row, column=MAIN_COLUMNS.index(READY_COLUMN) + 1)
        ready_cell.fill = ready_fill if complete else bad_fill

        for key, label in EXTRA_LABELS.items():
            result = as_count(extras.get(key))
            reported = item.get("reported", {}).get(key)
            source = item.get("sources", {}).get(key, "неизвестно")
            messages = list(item.get("issues", []))
            if global_issues:
                messages.extend(global_issues)
            if result is None:
                verdict = "НЕТ ДАННЫХ"
            elif reported is not None and reported != result:
                verdict = f"РАСХОЖДЕНИЕ: {reported} → {result}"
            elif messages:
                verdict = "ПРОВЕРИТЬ"
            else:
                verdict = "совпадает / рассчитано"
            review.append([item["fio"], values[COL_FORMAT], label, result if result is not None else "",
                           reported if reported is not None else "", source, "; ".join(messages) or verdict])
            row_no = review.max_row
            if result is None or messages or (reported is not None and reported != result):
                for cell in review[row_no]:
                    cell.fill = bad_fill if result is None else warn_fill

    for i, title in enumerate(MAIN_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = min(42, max(14, len(title) + 3))
    for i, width in enumerate((28, 22, 36, 14, 20, 32, 60), start=1):
        review.column_dimensions[get_column_letter(i)].width = width
    for sheet in (ws, review):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    wb.calculation.fullCalcOnLoad = True
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
