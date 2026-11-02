"""Проверки собранного сайта: ПДн, битые ссылки, неперехваченные /api/ (спека, п. 7)."""
import gzip
import re
from pathlib import Path

from tools.demo.anonymize import _FEMALE, _MALE, _SURNAMES

_TEXT = {'.html', '.js', '.css', '.json'}
_ALLOWED_API = ('/api/current-event', '/api/event-results', '/api/sse/tracker', '/api/siberman/results',
                '/api/tri/', '/api/duathlon222_')   # страницы Дуатлона строят URL из ${YEAR}; демо перехватывает только 2026
_UESC = re.compile(r'\\u([0-9a-fA-F]{4})')


def _texts(root: Path):
    for p in sorted(root.rglob('*')):
        if p.suffix in _TEXT:
            yield p, p.read_text(encoding='utf-8', errors='replace')
        elif p.name.endswith('.json.gz'):
            yield p, gzip.decompress(p.read_bytes()).decode('utf-8')


def _unescape(text: str) -> str:
    return _UESC.sub(lambda m: chr(int(m.group(1), 16)), text)


def pii_words(surnames: set[str]) -> set[str]:
    """Реальные фамилии для проверки: >= 4 букв, без слов из словарей генераторов (Жара и Siberman)."""
    from tools.demo.siberman.anonymize import GENERATOR_SURNAMES
    fake = set(_SURNAMES) | {s + 'а' for s in _SURNAMES} | set(_MALE) | set(_FEMALE)
    return {s for s in surnames if s and len(s) >= 4 and s not in fake and s.lower() not in GENERATOR_SURNAMES}


def check_pii(root: Path, surnames: set[str], phrases: set[str] | None = None,
              scope: tuple[str, ...] = (), phrases_skip_html: bool = False) -> list[str]:
    """Реальные фамилии (≥ 4 букв) целым словом в данных и страницах сайта. Слова из словарей
    генератора (фамилии, их женские формы, имена) пропускаются: фейковая «Соколова» или «Роман»
    в демо ничего не раскрывает, а реальные фамилии пересекаются со словарями (ложные срабатывания).
    phrases - полные имена, города, команды: целиком, без учёта регистра, не внутри слова.
    phrases_skip_html - фразы не ищутся в .html (страницы без данных: «Красноярск», «Россия» - текст шаблона).
    scope - если задан, проверяются только файлы с этими префиксами пути.
    Статика трекера (static/**) не проверяется: это исходники репозитория без данных участников.
    JSON проверяется и с раскрытыми \\u-последовательностями, независимо от ensure_ascii."""
    found = []
    phr = {x.strip() for x in (phrases or ()) if x and len(x.strip()) >= 4}
    words = pii_words(surnames)
    pats = [(ph, re.compile(r'(?<!\w)' + re.escape(ph) + r'(?!\w)', re.I)) for ph in sorted(phr)]
    for p, text in _texts(root):
        rel = p.relative_to(root).as_posix()
        if rel.startswith('static/') or (scope and not rel.startswith(scope)):
            continue
        plain = _unescape(text) if '\\u' in text else text
        tokens = set(re.findall(r'[\w-]+', text)) | set(re.findall(r'[\w-]+', plain))
        found.extend(f"{rel}: {s}" for s in sorted(words & tokens))
        if not (phrases_skip_html and p.suffix == '.html'):
            found.extend(f"{rel}: {ph}" for ph, rx in pats if rx.search(plain))
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
