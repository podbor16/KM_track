"""
Заполняет пустой чистый шаблон (excel_template_raw.xlsx, скопированный в DST)
реальными данными гонки 2025 года, извлечёнными из уже смигрированного файла
2025_import_ready.xlsx, эмулируя работу судей на новом шаблоне. Плюс
добавляет тестового участника для ручной проверки после загрузки через
/siberman/admin.

Использование:
    python docs/siberman/fill_template_from_2025.py <src 2025_import_ready.xlsx> <dst пустой шаблон.xlsx>
"""
import random
import sys
from typing import Optional
import openpyxl

from src.siberman.parser import parse_excel

STAGE_SEQ_COUNT = {"swim": 7, "bike_day1": 6, "bike_day2": 8, "run": 12}

# Колонки шаблона (1-based) по каждому этапу/seq
SWIM_COL = {1: 15, 2: 16, 3: 17, 4: 18, 5: 19, 6: 20, 7: 21}
BIKE1_COL = {1: 22, 2: 23, 3: 24, 4: 25, 5: 26, 6: 27}
HANDICAP_COL = 28
BIKE2_COL = {1: 29, 2: 30, 3: 31, 4: 32, 5: 33, 6: 34, 7: 35, 8: 36}
RUN_COL = {i: 36 + i for i in range(1, 13)}  # 37..48

CP_COL = {}
for (stage, seq), col in [(("swim", s), SWIM_COL[s]) for s in SWIM_COL]:
    CP_COL[(stage, seq)] = col
for s, col in BIKE1_COL.items():
    CP_COL[("bike_day1", s)] = col
for s, col in BIKE2_COL.items():
    CP_COL[("bike_day2", s)] = col
for s, col in RUN_COL.items():
    CP_COL[("run", s)] = col


def hms(seconds) -> str:
    if seconds is None:
        return ""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def main(SRC: str, DST: str):
    with open(SRC, "rb") as f:
        data = f.read()
    result = parse_excel(data, 2025)

    wb = openpyxl.load_workbook(DST)
    ws = wb["Результаты"]

    row_i = 3

    # --- Личники ---
    for p in result.participants:
        if p["format"] != "individual":
            continue
        cp = result.checkpoint_times.get(p["_cp_key"], {})
        handicap = result.handicaps.get(p["_cp_key"])

        ws.cell(row=row_i, column=1, value="Лично")
        ws.cell(row=row_i, column=2, value=p["bib"])
        ws.cell(row=row_i, column=3, value=p["surname"])
        ws.cell(row=row_i, column=4, value=p["name"])
        ws.cell(row=row_i, column=5, value={"M": "М", "F": "Ж"}.get(p["gender"], p["gender"]))
        ws.cell(row=row_i, column=13, value=p["country"])
        ws.cell(row=row_i, column=14, value=p["city"])
        for (stage, seq), col in CP_COL.items():
            v = cp.get((stage, seq))
            if v is not None:
                ws.cell(row=row_i, column=col, value=hms(v))
        if handicap is not None:
            ws.cell(row=row_i, column=HANDICAP_COL, value=hms(handicap))
        row_i += 1

    # --- Эстафеты: группируем 3 записи (swim/bike/run) по bib в одну строку ---
    relay_by_bib: dict[str, dict] = {}
    for p in result.participants:
        if p["format"] != "relay":
            continue
        relay_by_bib.setdefault(p["bib"], {})[p["relay_stage"]] = p

    def _full_name(m: Optional[dict]) -> str:
        return f"{m['surname']} {m['name']}".strip() if m else ""

    def _gender_ru(m: Optional[dict]) -> str:
        if not m:
            return ""
        return {"M": "М", "F": "Ж"}.get(m.get("gender"), "")

    for bib, members in relay_by_bib.items():
        any_member = next(iter(members.values()))
        ws.cell(row=row_i, column=1, value="Эстафета")
        ws.cell(row=row_i, column=2, value=bib)
        ws.cell(row=row_i, column=6, value=any_member["relay_team_name"])
        ws.cell(row=row_i, column=7, value=_full_name(members.get("swim")))
        ws.cell(row=row_i, column=8, value=_gender_ru(members.get("swim")))
        ws.cell(row=row_i, column=9, value=_full_name(members.get("bike")))
        ws.cell(row=row_i, column=10, value=_gender_ru(members.get("bike")))
        ws.cell(row=row_i, column=11, value=_full_name(members.get("run")))
        ws.cell(row=row_i, column=12, value=_gender_ru(members.get("run")))
        ws.cell(row=row_i, column=13, value=any_member["country"])
        ws.cell(row=row_i, column=14, value=any_member["city"])

        for stage_name, cp_key_suffix in (("swim", "swim"), ("bike_day1", "bike"), ("bike_day2", "bike"), ("run", "run")):
            cp = result.checkpoint_times.get(f"{bib}:{cp_key_suffix}", {})
            for seq in range(1, STAGE_SEQ_COUNT[stage_name] + 1):
                v = cp.get((stage_name, seq))
                if v is not None:
                    ws.cell(row=row_i, column=CP_COL[(stage_name, seq)], value=hms(v))

        handicap = result.handicaps.get(f"{bib}:bike")
        if handicap is not None:
            ws.cell(row=row_i, column=HANDICAP_COL, value=hms(handicap))
        row_i += 1

    # --- Тестовый участник для ручной проверки после загрузки ---
    random.seed(42)
    swim_base = 0
    swim_times = []
    for _ in range(7):
        swim_base += random.randint(280, 340)
        swim_times.append(swim_base)
    bike1_base = swim_base
    bike1_times = []
    for _ in range(6):
        bike1_base += random.randint(400, 3600)
        bike1_times.append(bike1_base)
    bike2_base = 0
    bike2_times = []
    for _ in range(8):
        bike2_base += random.randint(1800, 3600)
        bike2_times.append(bike2_base)
    run_base = 0
    run_times = []
    for _ in range(12):
        run_base += random.randint(2000, 2400)
        run_times.append(run_base)

    ws.cell(row=row_i, column=1, value="Лично")
    ws.cell(row=row_i, column=2, value=9999)
    ws.cell(row=row_i, column=3, value="Подборский")
    ws.cell(row=row_i, column=4, value="Матвей")
    ws.cell(row=row_i, column=5, value="М")
    ws.cell(row=row_i, column=13, value="Россия")
    ws.cell(row=row_i, column=14, value="Красноярск")
    for seq, v in enumerate(swim_times, start=1):
        ws.cell(row=row_i, column=SWIM_COL[seq], value=hms(v))
    for seq, v in enumerate(bike1_times, start=1):
        ws.cell(row=row_i, column=BIKE1_COL[seq], value=hms(v))
    ws.cell(row=row_i, column=HANDICAP_COL, value=hms(8 * 3600 + 6 * 60))  # 8:06:00
    for seq, v in enumerate(bike2_times, start=1):
        ws.cell(row=row_i, column=BIKE2_COL[seq], value=hms(v))
    for seq, v in enumerate(run_times, start=1):
        ws.cell(row=row_i, column=RUN_COL[seq], value=hms(v))

    wb.save(DST)
    print(f"Saved {row_i - 3 + 1} rows (incl. test participant) to {DST}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
