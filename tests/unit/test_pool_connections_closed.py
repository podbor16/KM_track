"""Каждая функция, берущая соединение из пула, закрывает его в finally.

PooledMySQLConnection без close() в пул не возвращается (__del__ нет) — 26–27.09.2026
так исчерпывался пул воркера до рестарта, а вебхуки Tilda терялись («db error»).
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# возвращают соединение вызывающему — закрывает он
EXEMPT = {("src/analytics/db_results.py", "create_connection"), ("src/analytics/db_pool.py", "get_pooled_connection")}


def _calls_pool(node):
    return any(isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "get_pooled_connection"
               for n in ast.walk(node))


def _leaks():
    out = []
    files = [ROOT / "app.py", *(ROOT / "src").rglob("*.py")]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT).as_posix()
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or (rel, fn.name) in EXEMPT:
                continue
            own = [n for n in fn.body]                    # без вложенных функций — они проверяются отдельно
            assigned = {t.id for stmt in own for n in ast.walk(stmt)
                        if isinstance(n, ast.Assign) and _calls_pool(n.value) and not _inside_nested(fn, n)
                        for t in n.targets if isinstance(t, ast.Name)}
            if not assigned:
                continue
            closed = {m.func.value.id for n in ast.walk(fn) if isinstance(n, ast.Try) and n.finalbody
                      for m in ast.walk(ast.Module(body=n.finalbody, type_ignores=[]))
                      if isinstance(m, ast.Call) and getattr(m.func, "attr", "") == "close"
                      and isinstance(m.func.value, ast.Name)}
            for name in sorted(assigned - closed):
                out.append(f"{rel}:{fn.lineno} {fn.name}() — {name} не закрывается в finally")
    return out


def _inside_nested(fn, node):
    for inner in ast.walk(fn):
        if inner is not fn and isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            if any(n is node for n in ast.walk(inner)):
                return True
    return False


def test_pooled_connections_closed_in_finally():
    assert _leaks() == []
