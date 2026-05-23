"""
Скачивает статические JS/CSS библиотеки с CDN в static/lib/.
Запускать перед деплоем или добавить вызов в deploy/update.sh.

Добавить новую библиотеку → добавить строку в LIBS.
Файлы НЕ хранятся в git (static/lib/ в .gitignore).
"""

import urllib.request
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LIB_DIR = BASE_DIR / "static" / "lib"

LIBS = {
    # Leaflet 1.9.4
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css":
        "leaflet-1.9.4/leaflet.css",
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js":
        "leaflet-1.9.4/leaflet.js",
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png":
        "leaflet-1.9.4/images/marker-icon.png",
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png":
        "leaflet-1.9.4/images/marker-icon-2x.png",
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png":
        "leaflet-1.9.4/images/marker-shadow.png",

    # Chart.js v4 (для results.html)
    "https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js":
        "chart4/chart.umd.min.js",

    # Chart.js v3.9.1 (для athlete-profile.html, race-analysis.html)
    "https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js":
        "chart3/chart.min.js",
}

HEADERS = {"User-Agent": "Mozilla/5.0 KM_track-deploy/1.0"}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  skip  {dest.relative_to(BASE_DIR)}")
        return
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())
    size_kb = dest.stat().st_size // 1024
    print(f"  OK    {dest.relative_to(BASE_DIR)} ({size_kb} KB)")


def main() -> None:
    print(f"Скачиваем библиотеки в {LIB_DIR.relative_to(BASE_DIR)}/")
    errors = []
    for url, rel_path in LIBS.items():
        dest = LIB_DIR / rel_path
        try:
            download(url, dest)
        except Exception as exc:
            print(f"  FAIL  {rel_path}: {exc}")
            errors.append(rel_path)

    if errors:
        print(f"\nОшибки при скачивании ({len(errors)} файлов):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\nГотово.")


if __name__ == "__main__":
    main()
