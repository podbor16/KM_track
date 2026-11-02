"""Публикация dist/race-tracker-demo/ в репозиторий podbor16/race-tracker-demo (GitHub Pages, ветка main)."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "dist" / "race-tracker-demo"
REPO = "https://github.com/podbor16/race-tracker-demo.git"


def run(*cmd, cwd=None):
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    if not (SRC / "index.html").exists():
        print("Нет сборки: сначала python tools/demo/build.py …")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "site"
        run("git", "clone", "--depth", "1", REPO, str(work))
        for p in work.iterdir():
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
        shutil.copytree(SRC, work, dirs_exist_ok=True)
        run("git", "add", "-A", cwd=work)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=work).returncode == 0:
            print("Изменений нет")
            return 0
        run("git", "commit", "-m", "Обновление демо", cwd=work)
        run("git", "push", "origin", "HEAD:main", cwd=work)
    print("Опубликовано: https://podbor16.github.io/race-tracker-demo/ (Pages обновится за 1–2 мин)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
