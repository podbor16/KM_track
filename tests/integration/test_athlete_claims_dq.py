"""Б1: привязки кабинета в склейках «Качества данных»: перенос в client_merge.apply (в т.ч. clean_clients), отмена
склейки и «Исправить ФИО» возвращает привязки, ночная автосклейка не меняет подтверждённую ДР."""
import json
from datetime import date

import pytest

from src.analytics import client_merge
from src.krasmarafon.services import athlete_claims as ac
from src.krasmarafon.services.athlete_claims import ClaimResult
# фикстуры db / cards / mail / merge_env и хелперы — из соседнего файла; сам он не меняется
from tests.integration.test_athlete_claims import (  # noqa: F401
    BD1, BD2, ME, MERGER, OTHER, SURNAME, add_lead, cards, claim_rows, db, journal, mail, merge_env)

BD_TYPO = date(1986, 5, 3)


def undo_details(cur, undo_id):
    cur.execute("SELECT details FROM dq_actions WHERE id = %s", (undo_id,))
    return json.loads(cur.fetchone()["details"])


# ---------------------------------------------------------------- client_merge.apply напрямую (clean_clients)

def test_apply_directly_moves_claim_like_clean_clients(merge_env, tmp_path):
    conn, cur, dq, c = merge_env
    assert ac.claim(ME, c["vanya"], BD1) == ClaimResult.OK
    moved = []

    client_merge.apply(conn, None, {c["c1"]: (SURNAME, "Иван", BD1.isoformat())}, {c["vanya"]: c["c1"]},
                       str(tmp_path / "b.json"), claims_out=moved)

    assert claim_rows(cur) == [{"client_id": c["c1"], "birthday": BD1}]
    assert moved == [{"client_id": c["vanya"], "email": ME, "moved_to": c["c1"]}]


def test_apply_directly_drops_claim_with_script_user(merge_env, tmp_path):
    conn, cur, dq, c = merge_env
    ac.claim(OTHER, c["c1"], BD1)
    ac.claim(ME, c["vanya"], BD1)

    client_merge.apply(conn, None, {c["c1"]: (SURNAME, "Иван", BD1.isoformat())}, {c["vanya"]: c["c1"]},
                       str(tmp_path / "b.json"))

    assert claim_rows(cur) == []
    assert journal(cur, "athlete_unclaim", c["vanya"]) == [({"email": ME, "reason": "merged"}, "script")]
    cur.execute("DELETE FROM dq_actions WHERE done_by = 'script' AND action = 'athlete_unclaim' "
                "AND finding_key = %s", (f"client:{c['vanya']}",))
    conn.commit()


# ---------------------------------------------------------------- отмена склейки / «Исправить ФИО»

def test_undo_merge_moves_claim_back(merge_env):
    conn, cur, dq, c = merge_env
    ac.claim(ME, c["vanya"], BD1)
    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)
    assert claim_rows(cur) == [{"client_id": c["c1"], "birthday": BD1}]

    undo_id = dq.undo_action(conn, action_id, MERGER)

    assert claim_rows(cur) == [{"client_id": c["vanya"], "birthday": BD1}]
    assert ac.claimed_cards(ME) == ([c["vanya"]], [])
    assert undo_details(cur, undo_id)["athlete_claims"] == [
        {"client_id": c["vanya"], "email": ME, "moved_back": True}]


def test_undo_merge_returns_dropped_claim_and_keeps_survivor_claim(merge_env):
    conn, cur, dq, c = merge_env
    ac.claim(OTHER, c["c1"], BD1)
    ac.claim(ME, c["vanya"], BD1)
    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)
    assert claim_rows(cur) == []

    undo_id = dq.undo_action(conn, action_id, MERGER)

    assert claim_rows(cur) == [{"client_id": c["vanya"], "birthday": BD1}]
    assert claim_rows(cur, OTHER) == [{"client_id": c["c1"], "birthday": BD1}]
    assert undo_details(cur, undo_id)["athlete_claims"] == [
        {"client_id": c["vanya"], "email": ME, "restored": True}]


def test_undo_merge_skips_dropped_claim_with_unconfirmed_birthday(merge_env):
    """Привязка со ставшей неактуальной ДР (stale) и записи без ДР не возвращаются — человек подтвердит заново."""
    conn, cur, dq, c = merge_env
    ac.claim(OTHER, c["c1"], BD1)
    ac.claim(ME, c["vanya"], BD1)
    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)
    cur.execute("SELECT details FROM dq_actions WHERE id = %s", (action_id,))
    d = json.loads(cur.fetchone()["details"])
    d["athlete_claims"] = [{"client_id": c["vanya"], "email": ME, "dropped": True, "stale": True}]
    cur.execute("UPDATE dq_actions SET details = %s WHERE id = %s", (json.dumps(d), action_id))
    conn.commit()

    dq.undo_action(conn, action_id, MERGER)

    assert claim_rows(cur) == []


def test_undo_merge_does_not_return_dropped_claim_with_other_birthday_than_account_has(merge_env):
    """Один человек — одна ДР: у почты уже есть действующая привязка с другой ДР — снятая при склейке не возвращается."""
    conn, cur, dq, c = merge_env
    ac.claim(OTHER, c["c1"], BD1)
    ac.claim(ME, c["vanya"], BD1)
    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)
    assert claim_rows(cur) == []
    assert ac.claim(ME, c["c2"], BD2) == ClaimResult.OK                 # привязок не осталось — вторая ДР допустима

    undo_id = dq.undo_action(conn, action_id, MERGER)

    assert claim_rows(cur) == [{"client_id": c["c2"], "birthday": BD2}]
    assert undo_details(cur, undo_id).get("athlete_claims", []) == []


def test_merge_marks_dropped_claim_with_changed_birthday_as_stale(merge_env):
    conn, cur, dq, c = merge_env
    ac.claim(OTHER, c["c1"], BD1)
    ac.claim(ME, c["vanya"], BD1)
    cur.execute("UPDATE clients SET birthday = %s WHERE id = %s", (BD_TYPO, c["vanya"]))
    conn.commit()

    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)

    cur.execute("SELECT details FROM dq_actions WHERE id = %s", (action_id,))
    assert json.loads(cur.fetchone()["details"])["athlete_claims"] == [
        {"client_id": c["vanya"], "email": ME, "dropped": True, "stale": True}]


def test_undo_merge_skips_claim_that_user_removed_meanwhile(merge_env):
    conn, cur, dq, c = merge_env
    ac.claim(ME, c["vanya"], BD1)
    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)
    ac.unclaim(ME, c["c1"])

    undo_id = dq.undo_action(conn, action_id, MERGER)

    assert claim_rows(cur) == []
    assert undo_details(cur, undo_id).get("athlete_claims", []) == []


def test_blocked_undo_keeps_claim_on_survivor(merge_env):
    conn, cur, dq, c = merge_env
    ac.claim(ME, c["vanya"], BD1)
    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)
    # ФИ+ДР прежней карточки заняты другой — отмена невозможна
    add_lead(cur, "Ваня", BD1, ME, 9011)
    conn.commit()

    with pytest.raises(ValueError):
        dq.undo_action(conn, action_id, MERGER)

    assert claim_rows(cur) == [{"client_id": c["c1"], "birthday": BD1}]


def test_undo_fix_fio_merge_moves_claim_back(merge_env):
    conn, cur, dq, c = merge_env
    ac.claim(ME, c["vanya"], BD1)
    cur.execute("SELECT id FROM results WHERE client_id = %s LIMIT 1", (c["c1"],))
    _, action_id = dq.fix_fio(conn, cur.fetchone()["id"], SURNAME, "Ваня", MERGER)
    assert claim_rows(cur) == [{"client_id": c["c1"], "birthday": BD1}]

    undo_id = dq.undo_action(conn, action_id, MERGER)

    assert claim_rows(cur) == [{"client_id": c["vanya"], "birthday": BD1}]
    assert undo_details(cur, undo_id)["athlete_claims"] == [
        {"client_id": c["vanya"], "email": ME, "moved_back": True}]


def test_undo_fix_fio_without_merge_leaves_claims_alone(merge_env):
    conn, cur, dq, c = merge_env
    ac.claim(ME, c["c1"], BD1)
    cur.execute("SELECT id FROM results WHERE client_id = %s LIMIT 1", (c["c1"],))
    _, action_id = dq.fix_fio(conn, cur.fetchone()["id"], SURNAME, "Ионн", MERGER)

    dq.undo_action(conn, action_id, MERGER)

    assert claim_rows(cur) == [{"client_id": c["c1"], "birthday": BD1}]


# ---------------------------------------------------------------- ночная автосклейка

@pytest.fixture
def twins(db, cards, mail, monkeypatch):
    """c1 (ДР 1986-05-01, результат с этой ДР) и typo — тот же человек с опечаткой в ДР (1986-05-03).
    apply_auto видит только находку этих двух карточек (в локальной БД могут быть чужие)."""
    from src.analytics import dq_actions

    conn, cur = db
    typo = add_lead(cur, "Иван", BD_TYPO, ME, 9020)["client_id"]
    conn.commit()
    mine = {cards["c1"], typo}
    real = dq_actions.pending_findings

    def only_mine(conn_, event_ids=None):
        findings, data = real(conn_, event_ids)
        return [f for f in findings if f.code == "C-TWIN" and set(f.client_ids) == mine], data

    monkeypatch.setattr(dq_actions, "pending_findings", only_mine)
    yield conn, cur, dq_actions, {**cards, "typo": typo}
    cur.execute("DELETE FROM dq_actions WHERE done_by = %s", (MERGER,))
    conn.commit()


def test_apply_auto_skips_when_bound_card_birthday_would_change(twins):
    conn, cur, dq, c = twins
    assert ac.claim(ME, c["typo"], BD_TYPO) == ClaimResult.OK

    done = dq.apply_auto(conn, MERGER)

    assert done["merged"] == []
    assert len(done["skipped"]) == 1 and "привязана к кабинету, ДР изменится" in done["skipped"][0]
    assert claim_rows(cur) == [{"client_id": c["typo"], "birthday": BD_TYPO}]
    cur.execute("SELECT COUNT(*) n FROM clients WHERE id IN (%s, %s)", (c["c1"], c["typo"]))
    assert cur.fetchone()["n"] == 2


def test_apply_auto_merges_when_final_birthday_equals_confirmed(twins):
    conn, cur, dq, c = twins
    assert ac.claim(ME, c["c1"], BD1) == ClaimResult.OK

    done = dq.apply_auto(conn, MERGER)

    assert len(done["merged"]) == 1 and done["skipped"] == []
    assert claim_rows(cur) == [{"client_id": c["c1"], "birthday": BD1}]
    assert ac.claimed_cards(ME) == ([c["c1"]], [])


def test_apply_auto_merges_unclaimed_cards_as_before(twins):
    conn, cur, dq, c = twins
    done = dq.apply_auto(conn, MERGER)
    assert len(done["merged"]) == 1 and done["skipped"] == []


def test_apply_auto_skips_group_with_two_claimed_cards(db, cards, mail, monkeypatch):
    """Две заявленные карточки в группе (разными почтами) с одной итоговой ДР: слить без потери одной привязки нельзя."""
    from src.analytics import dq_actions
    from src.analytics.dq_checks import Finding

    conn, cur = db
    assert ac.claim(OTHER, cards["c1"], BD1) == ClaimResult.OK
    assert ac.claim(ME, cards["vanya"], BD1) == ClaimResult.OK
    finding = Finding("C-TWIN", "high", "тест", (cards["c1"], cards["vanya"]))
    real = dq_actions.pending_findings
    monkeypatch.setattr(dq_actions, "pending_findings", lambda conn_, event_ids=None: ([finding], real(conn_, event_ids)[1]))
    monkeypatch.setattr(dq_actions, "merge_blockers", lambda ids, data: [])     # «Иван»/«Ваня» иначе остановят раньше

    done = dq_actions.apply_auto(conn, MERGER)

    assert done["merged"] == []
    assert len(done["skipped"]) == 1 and "несколько карточек привязаны к кабинету" in done["skipped"][0]
    assert claim_rows(cur, OTHER) == [{"client_id": cards["c1"], "birthday": BD1}]
    assert claim_rows(cur) == [{"client_id": cards["vanya"], "birthday": BD1}]
    cur.execute("SELECT COUNT(*) n FROM clients WHERE id IN (%s, %s)", (cards["c1"], cards["vanya"]))
    assert cur.fetchone()["n"] == 2
    cur.execute("DELETE FROM dq_actions WHERE done_by = %s", (MERGER,))
    conn.commit()
