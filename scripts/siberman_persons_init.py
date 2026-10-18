"""
Реестр людей Siberman: первичное заполнение по архиву и загрузка выгрузок заявок Тильды.

    python scripts/siberman_persons_init.py                      # только синхронизация
    python scripts/siberman_persons_init.py заявки1.csv заявки2.csv

Печатает только числа (без ФИО и дат рождения).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)  # локально — MySQL на 3308, на проде файла нет

from src.siberman.persons import service  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="*", help="CSV-выгрузки заявок Тильды")
    args = ap.parse_args()
    for path in args.csv:
        print(path, service.import_applicants(Path(path).read_bytes()))
    if not args.csv:
        print(service.sync_now())


if __name__ == "__main__":
    main()
