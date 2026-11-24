"""Identity decisions for a stable application ID."""
from collections import defaultdict

from src.siberman.persons import db as pdb
from src.siberman.persons.linking import plain_key


def name_key(row: dict) -> str:
    return plain_key(row["surname"], row["name"])


def resolve(entry: dict, candidates: list[dict], manual_id: int | None = None) -> dict:
    """A name suggests candidates. A verified manual decision or a unique date resolves them."""
    dob = entry.get("birthdate")
    if manual_id is not None:
        person = next((p for p in candidates if p["id"] == manual_id), None)
        if person is not None and (not dob or not person["birthdate"] or person["birthdate"] == dob):
            return {"state": "manual", "person_id": manual_id}
        return {"state": "review", "person_id": None}
    matches = [p for p in candidates if dob and p["birthdate"] == dob]
    if len(matches) == 1:
        return {"state": "matched", "person_id": matches[0]["id"]}
    return {"state": "review", "person_id": None}


def decisions(conn, entries: list[dict], include_candidates: bool = False) -> dict:
    if not entries:
        return {}
    ids = [e["id"] for e in entries]
    with conn.cursor(dictionary=True, buffered=True) as cur:
        cur.execute("SELECT id,surname,name,city,city_manual,birthdate FROM siberman_persons")
        persons = cur.fetchall()
        cur.execute("SELECT person_id,name_key FROM siberman_person_links")
        aliases = cur.fetchall()
        cur.execute(f"SELECT entry_id,person_id,is_new FROM siberman_entry_person_links "
                    f"WHERE entry_id IN ({', '.join(['%s'] * len(ids))})", ids)
        manual = {r["entry_id"]: r for r in cur.fetchall()}
    by_name = defaultdict(set)
    by_id = {p["id"]: p for p in persons}
    for person in persons:
        by_name[name_key(person)].add(person["id"])
    for row in aliases:
        if row["name_key"]:
            by_name[row["name_key"]].add(row["person_id"])
    out = {}
    for entry in entries:
        binding = manual.get(entry["id"])
        linked = binding["person_id"] if binding else None
        options = by_name[name_key(entry)] | ({linked} if linked else set())
        candidates = [by_id[pid] for pid in sorted(options)]
        result = ({"state": "review", "person_id": None}
                  if binding and linked is None else resolve(entry, candidates, linked))
        if result["person_id"] is not None and binding and binding["is_new"]:
            result["state"] = "new"
        if include_candidates:
            result["candidates"] = candidates
        out[entry["id"]] = result
    return out


def create_person(conn, entry: dict) -> int:
    return pdb.insert_person(conn, {
        "surname": entry["surname"], "name": entry["name"], "gender": entry.get("gender"),
        "birthdate": entry["birthdate"], "city": entry.get("city") or "",
    })
