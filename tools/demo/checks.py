"""Проверки собранного сайта: ПДн, битые ссылки, неперехваченные /api/ (спека, п. 7)."""
import gzip
import re
from pathlib import Path

from tools.demo.anonymize import _FEMALE, _MALE, _SURNAMES

_TEXT = {'.html', '.js', '.css', '.json'}
_ALLOWED_API = ('/api/current-event', '/api/event-results', '/api/sse/tracker')
_UESC = re.compile(r'\\u([0-9a-fA-F]{4})')


def _texts(root: Path):
    for p in sorted(root.rglob('*')):
        if p.suffix in _TEXT:
            yield p, p.read_text(encoding='utf-8', errors='replace')
        elif p.name.endswith('.json.gz'):
            yield p, gzip.decompress(p.read_bytes()).decode('utf-8')


def _unescape(text: str) -> str:
    return _UESC.sub(lambda m: chr(int(m.group(1), 16)), text)


def check_pii(root: Path, surnames: set[str]) -> list[str]:
    """Реальные фамилии (≥ 4 букв) целым словом в данных и страницах сайта. Слова из словарей
    генератора (фамилии, их женские формы, имена) пропускаются: фейковая «Соколова» или «Роман»
    в демо ничего не раскрывает, а реальные фамилии пересекаются со словарями (ложные срабатывания).
    Статика трекера (static/**) не проверяется: это исходники репозитория без данных участников.
    JSON проверяется и с раскрытыми \\u-последовательностями, независимо от ensure_ascii."""
    found = []
    fake = set(_SURNAMES) | {s + 'а' for s in _SURNAMES} | set(_MALE) | set(_FEMALE)
    words = {s for s in surnames if s and len(s) >= 4 and s not in fake}
    for p, text in _texts(root):
        rel = p.relative_to(root).as_posix()
        if rel.startswith('static/'):
            continue
        tokens = set(re.findall(r'[\w-]+', text))
        if '\\u' in text:
            tokens |= set(re.findall(r'[\w-]+', _unescape(text)))
        found.extend(f"{rel}: {s}" for s in sorted(words & tokens))
    return found


def check_links(root: Path, base: str) -> list[str]:
    bad = []
    for p, text in _texts(root):
        if p.suffix not in ('.html', '.css'):
            continue
        for ref in re.findall(rf'{re.escape(base)}static/[\w./-]+', text):
            if not (root / ref[len(base):]).exists():
                bad.append(f"{p.relative_to(root).as_posix()}: {ref}")
    return bad


def check_api(root: Path) -> list[str]:
    bad = []
    for p, text in _texts(root):
        if p.suffix not in ('.html', '.js'):
            continue
        for ref in re.findall(r"/api/[\w/-]+", text):
            if not ref.startswith(_ALLOWED_API):
                bad.append(f"{p.relative_to(root).as_posix()}: {ref}")
    return bad
