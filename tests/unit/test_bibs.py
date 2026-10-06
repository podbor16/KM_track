"""Присвоение стартовых номеров: правила по решениям пользователя 2026-10-05."""
from src.analytics.bibs import build_groups, plan

EV = "Снежная семерка"


def L(i, client, dist="7 км", created="2026-10-01 10:00:00", bib=None, bd="1990-01-01", event_id=None, main=0):
    return {"id": i, "client_id": client, "event_id": event_id or (119 if dist == "7 км" else 120),
            "event_distance": dist, "birthday": bd, "created_at": created, "start_number": bib, "dup_main": main}


def run(leads, ranges, event=EV):
    groups, taken = build_groups(event, leads)
    return plan(groups, ranges, taken)


def test_order_by_application_time():
    leads = [L(1, 10, created="2026-10-03"), L(2, 11, created="2026-10-01"), L(3, 12, created="2026-10-02")]
    _, assign, ok = run(leads, {("7 км", ""): (1, 100)})
    assert ok and assign == [(2, 1), (3, 2), (1, 3)]


def test_existing_bibs_kept_and_taken():
    leads = [L(1, 10, bib=1, created="2026-10-01"), L(2, 11, created="2026-10-02"), L(3, 12, bib=3, created="2026-10-03"),
             L(4, 13, created="2026-10-04")]
    _, assign, ok = run(leads, {("7 км", ""): (1, 100)})
    assert ok and assign == [(2, 2), (4, 4)]           # 1 и 3 заняты — первые свободные


def test_duplicates_one_bib_per_person_latest():
    # основная заявка — самая поздняя (решение 2026-10-06); номера — по времени основных заявок
    leads = [L(1, 10, created="2026-10-05"), L(2, 10, created="2026-10-01"), L(3, 11, created="2026-10-02")]
    rows, assign, ok = run(leads, {("7 км", ""): (1, 100)})
    assert assign == [(3, 1), (1, 2)] and rows[0]["duplicates"] == 1


def test_manual_main_lead_wins_over_latest():
    leads = [L(1, 10, created="2026-10-05"), L(2, 10, created="2026-10-01", main=1)]
    _, assign, ok = run(leads, {("7 км", ""): (1, 100)})
    assert ok and assign == [(2, 1)]


def test_person_with_bib_on_other_lead_gets_none():
    leads = [L(1, 10, bib=5, created="2026-10-05"), L(2, 10, created="2026-10-01")]
    rows, assign, ok = run(leads, {("7 км", ""): (1, 100)})
    assert ok and assign == [] and rows[0]["with_bib"] == 1


def test_not_enough_numbers_writes_nothing():
    leads = [L(1, 10), L(2, 11, dist="2 км"), L(3, 12, dist="2 км"), L(4, 13, dist="2 км")]
    rows, assign, ok = run(leads, {("7 км", ""): (1, 10), ("2 км", ""): (2000, 2001)})
    assert not ok and assign == []
    assert "нужно 3, свободно 2" in next(r for r in rows if r["distance"] == "2 км")["error"]


def test_missing_and_overlapping_ranges():
    leads = [L(1, 10), L(2, 11, dist="2 км")]
    rows, _, ok = run(leads, {("7 км", ""): (1, 100)})
    assert not ok and next(r for r in rows if r["distance"] == "2 км")["error"] == "не задан диапазон"
    rows, _, ok = run(leads, {("7 км", ""): (1, 100), ("2 км", ""): (50, 150)})
    assert not ok and "пересекается" in rows[0]["error"]


def test_bib_unique_across_distances():
    leads = [L(1, 10, dist="2 км", bib=2000), L(2, 11, created="2026-10-02")]
    _, assign, ok = run(leads, {("7 км", ""): (1999, 2001), ("2 км", ""): (2002, 2100)})
    assert ok and assign == [(2, 1999)]
    leads = [L(1, 10, dist="2 км", bib=1)]  + [L(2, 11)]
    _, assign, ok = run(leads, {("7 км", ""): (1, 100), ("2 км", ""): (2000, 2100)})
    assert assign == [(2, 2)]                                       # «1» занят заявкой другой дистанции


def test_kids_by_birth_year_and_500m_skipped():
    k = "Детский забег"
    leads = [L(1, 10, dist="1 км", bd="2019-05-01", event_id=1, created="2026-08-01"),
             L(2, 11, dist="1 км", bd="2018-02-01", event_id=1, created="2026-08-02"),
             L(3, 12, dist="1 км", bd="2019-07-01", event_id=1, created="2026-08-03"),
             L(4, 13, dist="500 м", bd="2022-01-01", event_id=2, bib=1)]
    rows, assign, ok = run(leads, {("1 км", "2019"): (9000, 9999), ("1 км", "2018"): (8000, 8999)}, event=k)
    assert ok and sorted(assign) == [(1, 9000), (2, 8000), (3, 9001)]
    assert {r["label"] for r in rows} == {"1 км, 2018 г.р.", "1 км, 2019 г.р."}  # 500 м — без номеров


def test_nothing_to_assign_needs_no_range():
    rows, assign, ok = run([L(1, 10, bib=7)], {})
    assert ok and assign == []


def test_main_lead_per_person_keeps_people_with_duplicates():
    # раньше экспорт брал is_duplicate=0 и выкидывал человека с дублем целиком
    from src.analytics.bibs import main_lead_per_person
    leads = [L(1, 10, created="2026-10-05"), L(2, 10, created="2026-10-01"), L(3, 11, created="2026-10-02"),
             L(4, 10, dist="2 км", created="2026-10-03")]      # тот же человек на другой дистанции — отдельно
    assert sorted(l["id"] for l in main_lead_per_person(leads)) == [1, 3, 4]


def test_main_lead_order_manual_then_bib_then_latest():
    from src.analytics.bibs import main_lead_per_person
    pick = lambda leads: main_lead_per_person(leads)[0]["id"]
    assert pick([L(1, 10, created="2026-10-05"), L(2, 10, created="2026-10-01", bib=7)]) == 2      # номер — у основной
    assert pick([L(1, 10, created="2026-10-05", bib=8), L(2, 10, created="2026-10-01", main=1)]) == 2
    assert pick([L(1, 10, created="2026-10-05"), L(2, 10, created="2026-10-05")]) == 2             # равное время — больший id


def test_elite_gets_no_bib_and_is_main():
    # «Элита» — именной номер 0 (Жара 21,1 км): номер не присваивается, 0 не занимает диапазон
    leads = [L(1, 10, bib=0, created="2026-10-01"), L(2, 10, created="2026-10-05"), L(3, 11, created="2026-10-02")]
    rows, assign, ok = run(leads, {("7 км", ""): (1, 100)})
    assert ok and assign == [(3, 1)] and rows[0]["with_bib"] == 1


def test_import_bib_elite():
    from src.analytics.db_results import _import_bib
    assert [_import_bib(v) for v in ("17", " Элита ", "элита", "", "abc")] == [17, 0, 0, None, None]
