"""История спортсмена (личный кабинет, Б1): итоги и лента по строкам результатов и заявок — без БД.
Правила — спецификация 2026-11-03-athlete-cards-history-design, «Страница истории»."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from src.core.mailer import mask_email
from src.krasmarafon.services.athlete_cabinet import finish_info, fmt_time, is_upcoming, protocol_url

_STATUS_TEXT = {
    "Not started": "не стартовал",
    "DNF": "сошёл",
    "Withdrawn": "сошёл",
    "DSQ": "дисквалифицирован",
}


def _dist(value) -> Optional[Decimal]:
    return Decimal(str(value)) if value is not None else None


def _dist_key(d: Decimal) -> str:
    """21.1 -> "21.1", Decimal("5.00") -> "5"."""
    return format(d.normalize(), "f")


def _dist_label(d: Optional[Decimal]) -> Optional[str]:
    return _dist_key(d).replace(".", ",") + " км" if d is not None else None


def _pace(seconds: float, km: Decimal) -> str:
    s = round(seconds / float(km))
    return f"{s // 60}:{s % 60:02d}"


def _year(year: Optional[int], date: Optional[dt.date]) -> Optional[int]:
    return year or (date.year if date else None)


def _money(value) -> Optional[str]:
    """1090.0 -> "1 090 ₽" (неразрывные пробелы), 109.5 -> "109,5 ₽"; None -> None."""
    if value is None:
        return None
    d = Decimal(str(round(float(value), 2)))
    text = format(d if d != d.to_integral_value() else d.quantize(Decimal(1)), ",f")
    return text.replace(",", "\u00a0").replace(".", ",") + " ₽"


def _places(r: dict, place: Optional[int]) -> Optional[str]:
    """«{абс} абс. · {место} в {категория}»: при чистом времени — чистые места; пустые части не выводятся."""
    clean = r["time_clear_finish"] is not None
    absolute = (r["rank_absolute_clean"] or r["rank_absolute"]) if clean else r["rank_absolute"]
    category = (r["category"] or "").strip()
    parts = []
    if absolute:
        parts.append(f"{absolute} абс.")
    if place:
        parts.append(f"{place} в {category}" if category else f"{place} место в категории")
    return " · ".join(parts) or None


def _order(lead: dict, account_email: Optional[str]) -> dict:
    """Подробности заявки (раскрывающийся блок). Почта оформления — полностью, если это почта аккаунта, иначе маской."""
    mail = (lead["email"] or "").strip() or (lead["ma_email"] or "").strip()
    if mail and mail.lower() != (account_email or "").strip().lower():
        mail = mask_email(mail)
    return {
        "participant": f"{lead['surname'] or ''} {lead['name'] or ''}".strip(), "birthday": lead["birthday"],
        "created": lead["created_at"], "order_id": lead["order_id"] or None,
        "amount": _money(lead["amount"]), "promocode": (lead["promocode"] or "").strip() or None,
        "discount": _money(lead["discount"]) if lead["discount"] else None,
        "products": (lead["products"] or "").strip() or None, "email": mail or None,
    }


def _result_entry(r: dict, codes: dict, diploma_ids: set) -> dict:
    finished, td, place = finish_info(r)
    dist = _dist(r["event_distance"])
    year = _year(r["event_year"], r["event_date"])
    if finished:
        status = None
    else:
        status = _STATUS_TEXT.get(r["race_status"], "нет результата")
    return {
        "kind": "result", "date": r["event_date"], "year": year, "event_name": r["event_name"],
        "distance": _dist_label(dist), "start_number": r["start_number"],
        "time": fmt_time(td) if finished else None, "place": place,
        "places": _places(r, place) if finished else None,
        "pace": _pace(td.total_seconds(), dist) if finished and dist else None,
        "status": status, "refund": False, "order": None,  # подробности заказа — только у заявок
        "protocol_url": protocol_url(r["event_name"], year, r.get("surname"), codes) if finished else None,
        "diploma_url": (f"/diploma/{r['event_id']}/{r['start_number']}"
                        if finished and r["event_id"] in diploma_ids and r["start_number"] is not None else None),
    }


def _lead_entry(lead: dict, today: dt.date, account_email: Optional[str]) -> dict:
    year = _year(lead["event_year"], lead["event_date"])
    upcoming = is_upcoming(lead["event_date"], lead["event_year"], today)
    refund = bool(lead["refund"])
    if upcoming:
        status = None
    else:
        status = "возврат" if refund else "не стартовал"
    return {
        "kind": "ticket" if upcoming else "result", "date": lead["event_date"], "year": year,
        "event_name": lead["event_name"], "distance": _dist_label(_dist(lead["event_distance"])),
        "start_number": lead["start_number"], "time": None, "place": None, "places": None, "pace": None,
        "status": status, "refund": refund, "protocol_url": None, "diploma_url": None,
        "order": _order(lead, account_email),
    }


def _item_order(e: dict):
    """Предстоящие (билеты) ближайшие сверху, затем прошедшие от новых к старым."""
    if e["kind"] == "ticket":
        return (0, (e["date"] or dt.date.max).toordinal())
    return (1, -(e["date"] or dt.date(e["year"] or 1, 1, 1)).toordinal())


def _tiles(finishes: list[dict]) -> dict:
    km = sum((f["dist"] for f in finishes if f["dist"]), Decimal(0))
    paced = [f for f in finishes if f["dist"] and f["dist"] >= 1]
    pace_km = sum((f["dist"] for f in paced), Decimal(0))
    pace = _pace(sum(f["sec"] for f in paced), pace_km) if paced else None
    return {"km": int(km.quantize(Decimal(1), ROUND_HALF_UP)), "pace": pace}


def _records(finishes: list[dict]) -> list[dict]:
    best: dict = {}
    for f in finishes:
        if f["dist"] and (f["dist"] not in best or f["sec"] < best[f["dist"]]["sec"]):
            best[f["dist"]] = f
    return [{"distance": _dist_label(d), "time": fmt_time(dt.timedelta(seconds=f["sec"])),
             "pace": _pace(f["sec"], d), "event_name": f["event_name"], "year": f["year"]}
            for d, f in sorted(best.items(), key=lambda kv: kv[0], reverse=True)]


def _dynamics(finishes: list[dict]) -> dict:
    by_dist: dict = {}
    for f in finishes:
        if f["dist"] and f["year"]:
            by_dist.setdefault(f["dist"], []).append(f)
    series: dict = {}
    for d, fs in by_dist.items():
        best: dict = {}
        for f in fs:
            best[f["year"]] = min(best.get(f["year"], f["sec"]), f["sec"])
        if len(best) >= 2:
            series[d] = [[y, best[y]] for y in sorted(best)]
    if not series:
        return {}
    default = max(series, key=lambda d: (len(by_dist[d]), d))
    return {"default": _dist_key(default),
            "series": {_dist_key(d): series[d] for d in sorted(series)}}


def build_history(results: list[dict], leads: list[dict], today: dt.date, codes: dict, diploma_ids: set,
                  account_email: Optional[str] = None) -> dict:
    """-> {"since", "tiles": {starts, finishes, km, pace}, "records", "dynamics", "years": [{year, items}]}.
    account_email — почта аккаунта: в подробностях заявки она показывается полностью, остальные — маской."""
    done = {(r["client_id"], r["event_id"]) for r in results}   # результат той же карточки в том же событии; номер заявки не нужен
    active = done | {(ld["client_id"], ld["event_id"]) for ld in leads if not ld["refund"]}
    open_leads = [ld for ld in leads if (ld["client_id"], ld["event_id"]) not in done
                  and not (ld["refund"] and ld["event_id"] is not None and (ld["client_id"], ld["event_id"]) in active)]

    entries = ([_result_entry(r, codes, diploma_ids) for r in results]
               + [_lead_entry(ld, today, account_email) for ld in open_leads])

    finishes = []
    for r in results:
        finished, td, _ = finish_info(r)
        if finished:
            finishes.append({"dist": _dist(r["event_distance"]), "sec": int(td.total_seconds()),
                             "year": _year(r["event_year"], r["event_date"]), "event_name": r["event_name"]})
    starts = [r for r in results if r["race_status"] != "Not started"]

    start_years = [y for y in (_year(r["event_year"], r["event_date"]) for r in starts) if y]
    lead_years = [y for y in (_year(ld["event_year"], ld["event_date"]) for ld in leads) if y]
    since = min(start_years or lead_years, default=None)

    by_year: dict = {}
    for e in entries:
        by_year.setdefault(e["year"], []).append(e)
    years = [{"year": y, "items": sorted(by_year[y], key=_item_order)}
             for y in sorted(by_year, key=lambda y: (y is None, -(y or 0)))]

    return {
        "since": since,
        "tiles": {"starts": len(starts), "finishes": len(finishes), **_tiles(finishes)},
        "records": _records(finishes),
        "dynamics": _dynamics(finishes),
        "years": years,
    }
