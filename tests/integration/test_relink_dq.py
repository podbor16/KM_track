"""«Заявка и результат №N расходятся» (R-LEADFIX) и действие «Исправить заявку по протоколу» на локальной БД.
Тестовые данные — событие «Тест перепривязка» 2099, почты *@relink-test.local, фамилии «Тестрелинк…», журнал
done_by='relink-test'; фикстура убирает их до и после. UPDATE/DELETE — только по ним; apply_auto видит только находки
этих карточек (в локальной БД могут быть чужие)."""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import app
from src.analytics import dq_actions, dq_cases
from src.analytics.dq_actions import fix_lead_by_protocol, relink_row, undo_action
from src.analytics.dq_checks import load, load_scoped, run_checks
from src.core.auth import api_require_auth
from tests.integration.test_relink import (BD_DAUGHTER, BD_MAMA, BD_SON, SURNAME, USER, add_lead, add_result, card, db,  # noqa: F401
                                           fix, row_state)

BD_TYPO = date(1986, 5, 2)          # ДР мамы с опечаткой в одной цифре
PAIR_CODES = ("R-LEAD", "R-LEADFIX")


@pytest.fixture
def world(db):  # noqa: F811
    """cm — карточка «Мама» (заявка 9001 и ошибочная заявка 9500 с её ФИ+ДР). Результат №9500 исправлен в протоколе
    на «Сын» (ДР 2017) и переехал (relink_row) на новую карточку cs: заявка осталась со старыми ФИ/ДР на cm."""
    conn, cur = db
    cm = add_lead(cur, "Мама", BD_MAMA, 9001)
    lead = add_lead(cur, "Мама", BD_MAMA, 9500)
    res = add_result(cur, "Мама", BD_MAMA, cm["event_id"], 9500)
    conn.commit()
    assert lead["client_id"] == res["client_id"] == cm["client_id"]
    fix(conn, cur, "results", res["id"], name="Сын", birthday=BD_SON)
    moved = relink_row(conn, "results", res["id"], USER, "loader")
    assert moved["action"] == "new_card"
    return {"cm": cm["client_id"], "cs": moved["to_card"], "lead": lead["id"], "result": res["id"],
            "event_id": cm["event_id"]}


def pair_findings(conn, *cards):
    """Находки пары карточек (проверки по строкам этих карточек, как при открытии дела)."""
    cards = set(cards)
    return [f for f in run_checks(load_scoped(conn, cards), card_ids=cards) if f.code in PAIR_CODES]


def journal(cur):
    cur.execute("SELECT id, action, finding_key, details FROM dq_actions WHERE done_by = %s ORDER BY id", (USER,))
    return [{**r, "details": json.loads(r["details"])} for r in cur.fetchall()]


def test_finding_appears_instead_of_lead_on_other_card(db, world):  # noqa: F811
    conn, _ = db
    [f] = pair_findings(conn, world["cm"], world["cs"])
    assert f.code == "R-LEADFIX"
    assert f.client_ids == (world["cs"], world["cm"])
    assert (f.result_id, f.lead_id, f.event_id) == (world["result"], world["lead"], world["event_id"])
    assert "расходятся" in f.message and "№9500" in f.message


def test_scoped_finding_equals_full_run(db, world):  # noqa: F811
    """Дело открывается по карточкам без полной загрузки — находка та же, что у полного прогона."""
    conn, _ = db
    mine = {world["cm"], world["cs"]}
    full = {f.key for f in run_checks(load(conn)) if f.code in PAIR_CODES and set(f.client_ids) == mine}
    assert full == {f.key for f in pair_findings(conn, *mine)} and len(full) == 1


def test_question_offers_fix_by_protocol_and_not_merge(db, world):  # noqa: F811
    conn, _ = db
    case = dq_cases.get_case(conn, f'c{min(world["cm"], world["cs"])}')
    [q] = [x for x in case["questions"] if x["code"] == "R-LEADFIX"]
    answers = {a["id"]: a for a in q["answers"]}
    assert "merge" not in answers
    assert answers["fixlead"]["label"].startswith("Исправить заявку по протоколу")
    assert answers["fixlead"]["recommended"]
    assert {f'to:{world["cm"]}', "keep", "postpone"} <= set(answers)
    assert q["stage"] == 1


def test_fix_moves_lead_after_result_and_undo(db, world):  # noqa: F811
    conn, cur = db
    to_card, ids = fix_lead_by_protocol(conn, world["lead"], world["result"], USER, "k")
    assert to_card == world["cs"] and len(ids) == 2
    row = row_state(cur, "leads", world["lead"])
    assert (row["client_id"], row["name"], row["birthday"]) == (world["cs"], "Сын", BD_SON)
    assert row_state(cur, "results", world["result"])["client_id"] == world["cs"]
    cur.execute("SELECT COUNT(*) n FROM leads WHERE client_id = %s", (world["cm"],))
    assert cur.fetchone()["n"] == 1                      # заявка 9001 мамы на месте
    assert pair_findings(conn, world["cm"], world["cs"]) == []
    assert [j["action"] for j in journal(cur)][-2:] == ["edit", "move_result"]

    for action_id in reversed(ids):
        undo_action(conn, action_id, USER)
    row = row_state(cur, "leads", world["lead"])
    assert (row["client_id"], row["name"], row["birthday"]) == (world["cm"], "Мама", BD_MAMA)
    assert row_state(cur, "results", world["result"])["client_id"] == world["cs"]
    assert [f.code for f in pair_findings(conn, world["cm"], world["cs"])] == ["R-LEADFIX"]


def test_fix_only_birthday_differs(db):  # noqa: F811
    """Фамилия и имя те же, ДР в заявке не та: правится только ДР, заявка переезжает на карточку результата."""
    conn, cur = db
    anchor = add_lead(cur, "Дочь", BD_DAUGHTER, 9001)                  # даёт событие
    res = add_result(cur, "Мама", BD_SON, anchor["event_id"], 9701)    # карточка по ФИ+ДР результата
    lead = add_lead(cur, "Мама", BD_MAMA, 9701)                        # заявка — на своей карточке
    conn.commit()
    assert res["client_id"] != lead["client_id"]
    [f] = pair_findings(conn, lead["client_id"], res["client_id"])
    assert f.code == "R-LEADFIX"
    to_card, ids = fix_lead_by_protocol(conn, lead["id"], res["id"], USER, f.key)
    assert to_card == res["client_id"] and len(ids) == 2
    row = row_state(cur, "leads", lead["id"])
    assert (row["client_id"], row["name"], row["birthday"]) == (res["client_id"], "Мама", BD_SON)
    assert card(cur, lead["client_id"]) is None                        # опустевшая карточка удалена (как в «Перенести»)
    for action_id in reversed(ids):
        undo_action(conn, action_id, USER)
    assert row_state(cur, "leads", lead["id"])["client_id"] == lead["client_id"]


def test_fix_rejects_rows_that_do_not_diverge(db, world):  # noqa: F811
    conn, cur = db
    other = add_lead(cur, "Дочь", BD_SON, 9800)           # заявка с другим номером
    conn.commit()
    with pytest.raises(ValueError, match="номер"):
        fix_lead_by_protocol(conn, other["id"], world["result"], USER, "")
    fix_lead_by_protocol(conn, world["lead"], world["result"], USER, "")
    with pytest.raises(ValueError, match="одной карточке"):
        fix_lead_by_protocol(conn, world["lead"], world["result"], USER, "")


def test_fix_rejects_result_without_real_birthday(db, world):  # noqa: F811
    conn, cur = db
    fix(conn, cur, "results", world["result"], birthday="1900-01-01")
    with pytest.raises(ValueError, match="ДР"):
        fix_lead_by_protocol(conn, world["lead"], world["result"], USER, "")
    assert row_state(cur, "leads", world["lead"])["client_id"] == world["cm"]


def test_answer_fixlead_via_case(db, world):  # noqa: F811
    conn, cur = db
    key = f'c{min(world["cm"], world["cs"])}'
    [q] = [x for x in dq_cases.get_case(conn, key)["questions"] if x["code"] == "R-LEADFIX"]
    out = dq_cases.apply_answer(conn, key, q["id"], "fixlead", {}, USER)
    assert len(out["action_ids"]) == 2
    assert row_state(cur, "leads", world["lead"])["client_id"] == world["cs"]
    assert pair_findings(conn, world["cm"], world["cs"]) == []
    for action_id in reversed(out["action_ids"]):
        undo_action(conn, action_id, USER)
    assert row_state(cur, "leads", world["lead"])["client_id"] == world["cm"]


def test_answer_keep_dismisses_without_changes(db, world):  # noqa: F811
    conn, cur = db
    key = f'c{min(world["cm"], world["cs"])}'
    [q] = [x for x in dq_cases.get_case(conn, key)["questions"] if x["code"] == "R-LEADFIX"]
    try:
        dq_cases.apply_answer(conn, key, q["id"], "keep", {}, USER)
        assert row_state(cur, "leads", world["lead"])["client_id"] == world["cm"]
        assert dq_actions.load_decisions(conn)[q["id"]] == "keep"
    finally:
        cur.execute("DELETE FROM dq_decisions WHERE decided_by = %s", (USER,))
        conn.commit()


# ---- ни R-LEAD, ни ночная автосклейка такую пару не склеивают; опечатка — как раньше ----

@pytest.fixture
def only_mine(monkeypatch):
    """apply_auto видит только находки пары R-LEAD/R-LEADFIX с указанными карточками."""
    real = dq_actions.pending_findings

    def install(cards):
        def mine(conn_, event_ids=None):
            findings, data = real(conn_, event_ids)
            return [f for f in findings if f.code in PAIR_CODES and set(f.client_ids) <= set(cards)], data
        monkeypatch.setattr(dq_actions, "pending_findings", mine)
    return install


def test_apply_auto_does_not_merge_diverging_pair(db, world, only_mine):  # noqa: F811
    conn, cur = db
    only_mine({world["cm"], world["cs"]})
    findings, _ = dq_actions.pending_findings(conn)
    assert [f.code for f in findings] == ["R-LEADFIX"]

    done = dq_actions.apply_auto(conn, USER)

    assert done == {"deleted": [], "merged": [], "skipped": []}
    cur.execute("SELECT COUNT(*) n FROM clients WHERE id IN (%s, %s)", (world["cm"], world["cs"]))
    assert cur.fetchone()["n"] == 2
    assert row_state(cur, "leads", world["lead"])["client_id"] == world["cm"]


@pytest.fixture
def typo(db):  # noqa: F811
    """Результат с опечаткой в ДР (одна цифра) на своей карточке, заявка с тем же номером — на настоящей."""
    conn, cur = db
    res = add_result(cur, "Мама", BD_TYPO, add_lead(cur, "Дочь", BD_SON, 9001)["event_id"], 9600)
    lead = add_lead(cur, "Мама", BD_MAMA, 9600)
    conn.commit()
    assert res["client_id"] != lead["client_id"]
    return {"res_card": res["client_id"], "lead_card": lead["client_id"]}


def test_typo_stays_lead_on_other_card(db, typo):  # noqa: F811
    conn, _ = db
    [f] = pair_findings(conn, typo["res_card"], typo["lead_card"])
    assert (f.code, f.severity) == ("R-LEAD", "high")


def test_apply_auto_still_merges_typo(db, typo, only_mine):  # noqa: F811
    conn, cur = db
    only_mine({typo["res_card"], typo["lead_card"]})
    done = dq_actions.apply_auto(conn, USER)
    assert len(done["merged"]) == 1 and done["skipped"] == []
    cur.execute("SELECT COUNT(*) n FROM clients WHERE id IN (%s, %s)", (typo["res_card"], typo["lead_card"]))
    assert cur.fetchone()["n"] == 1


# ---- эндпоинт ----

@pytest.fixture
def api():
    app.dependency_overrides[api_require_auth] = lambda: USER
    yield TestClient(app)
    app.dependency_overrides.pop(api_require_auth, None)


def test_endpoint_fix_lead(db, world, api):  # noqa: F811
    conn, cur = db
    r = api.post("/api/admin/data-quality/fix-lead",
                 json={"lead_id": world["lead"], "result_id": world["result"], "key": "k"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["client_id"] == world["cs"] and len(body["action_ids"]) == 2
    assert row_state(cur, "leads", world["lead"])["client_id"] == world["cs"]


def test_endpoint_fix_lead_bad_pair_is_400(db, world, api):  # noqa: F811
    r = api.post("/api/admin/data-quality/fix-lead", json={"lead_id": world["lead"], "result_id": 0})
    assert r.status_code == 400


def test_endpoint_requires_auth(db, world):  # noqa: F811
    r = TestClient(app).post("/api/admin/data-quality/fix-lead",
                             json={"lead_id": world["lead"], "result_id": world["result"]})
    assert r.status_code == 401
