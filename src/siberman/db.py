import os
import logging
import mysql.connector
from typing import Optional

log = logging.getLogger(__name__)


def get_siberman_connection() -> Optional[mysql.connector.MySQLConnection]:
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("SIBERMAN_DB_NAME", "siberman"),
            user=os.getenv("DB_USER", "km_analytic"),
            password=os.getenv("DB_PASSWORD"),
            charset="utf8mb4",
            autocommit=True,
            connection_timeout=10,
        )
    except Exception as e:
        log.error(f"siberman connect error: {e}")
        return None


def get_checkpoints(conn, race_year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, stage, seq, label, distance_km "
        "FROM checkpoints WHERE race_year=%s ORDER BY stage, seq",
        (race_year,)
    )
    return cur.fetchall()


def clear_race_year(conn, race_year: int) -> None:
    """Удалить всех участников (и каскадно все связанные данные) за год."""
    cur = conn.cursor()
    cur.execute("DELETE FROM participants WHERE race_year=%s", (race_year,))


def upsert_participant(conn, p: dict) -> int:
    """Вставить/обновить участника. Возвращает id."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO participants
           (race_year, bib, surname, name, gender, member_gender, country, city,
            format, relay_team_name, relay_stage, status, dnf_stage, bike_day2_handicap_s)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE
             surname=VALUES(surname), name=VALUES(name), gender=VALUES(gender),
             member_gender=VALUES(member_gender),
             country=VALUES(country), city=VALUES(city), format=VALUES(format),
             relay_team_name=VALUES(relay_team_name), relay_stage=VALUES(relay_stage),
             status=VALUES(status), dnf_stage=VALUES(dnf_stage),
             bike_day2_handicap_s=VALUES(bike_day2_handicap_s)""",
        (p["race_year"], p["bib"], p["surname"], p["name"], p["gender"], p.get("member_gender"),
         p.get("country", "Россия"), p.get("city", ""),
         p.get("format", "individual"), p.get("relay_team_name"),
         p.get("relay_stage", "none"), p.get("status", "active"),
         p.get("dnf_stage"), p.get("bike_day2_handicap_s"))
    )
    if cur.lastrowid:
        return cur.lastrowid
    cur.execute(
        "SELECT id FROM participants WHERE race_year=%s AND bib=%s AND relay_stage=%s",
        (p["race_year"], p["bib"], p.get("relay_stage", "none"))
    )
    return cur.fetchone()[0]


def upsert_checkpoint_time(conn, participant_id: int, checkpoint_id: int,
                            cumulative_s: Optional[int], split_s: Optional[int]) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO checkpoint_times (participant_id, checkpoint_id, cumulative_s, split_s)
           VALUES (%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE cumulative_s=VALUES(cumulative_s), split_s=VALUES(split_s)""",
        (participant_id, checkpoint_id, cumulative_s, split_s)
    )


def upsert_transition(conn, participant_id: int, zone: str, duration_s: Optional[int]) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO transitions (participant_id, zone, duration_s)
           VALUES (%s,%s,%s)
           ON DUPLICATE KEY UPDATE duration_s=VALUES(duration_s)""",
        (participant_id, zone, duration_s)
    )


def upsert_stage_total(
    conn, participant_id: int, stage: str,
    total_s: Optional[int], rank_stage: Optional[int], rank_gender: Optional[int],
    avg_pace_s: Optional[int], avg_speed_kmh: Optional[float],
) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO stage_totals
           (participant_id, stage, total_s, rank_stage, rank_gender, avg_pace_s, avg_speed_kmh)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE
             total_s=VALUES(total_s), rank_stage=VALUES(rank_stage),
             rank_gender=VALUES(rank_gender), avg_pace_s=VALUES(avg_pace_s),
             avg_speed_kmh=VALUES(avg_speed_kmh)""",
        (participant_id, stage, total_s, rank_stage, rank_gender, avg_pace_s, avg_speed_kmh),
    )


def upsert_overall_result(
    conn, participant_id: int,
    total_s: Optional[int], rank_overall: Optional[int],
    rank_gender: Optional[int], rank_relay: Optional[int],
) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO overall_results
           (participant_id, total_s, rank_overall, rank_gender, rank_relay)
           VALUES (%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE
             total_s=VALUES(total_s), rank_overall=VALUES(rank_overall),
             rank_gender=VALUES(rank_gender), rank_relay=VALUES(rank_relay)""",
        (participant_id, total_s, rank_overall, rank_gender, rank_relay),
    )


def get_participants_with_stage_totals(conn, race_year: int,
                                        gender: Optional[str] = None,
                                        fmt: Optional[str] = None) -> list[dict]:
    where = ["p.race_year=%s"]
    params: list = [race_year]
    if gender:
        where.append("p.gender=%s")
        params.append(gender)
    if fmt:
        where.append("p.format=%s")
        params.append(fmt)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"SELECT p.*, st.stage, st.total_s, st.rank_stage, st.rank_gender, "
        f"st.avg_pace_s, st.avg_speed_kmh "
        f"FROM participants p "
        f"LEFT JOIN stage_totals st ON st.participant_id=p.id "
        f"WHERE {' AND '.join(where)} ORDER BY p.bib, st.stage",
        params
    )
    return cur.fetchall()


def get_results_for_year(conn, race_year: int) -> dict:
    """Вернуть все результаты за год для публичной страницы."""
    cur = conn.cursor(dictionary=True)

    # Личные участники — все данные в одной строке (pivot через LEFT JOIN)
    cur.execute("""
        SELECT
            p.bib, p.surname, p.name, p.gender, p.city, p.status,
            o.total_s   AS overall_s,
            o.rank_overall, o.rank_gender AS overall_rank_g,
            sw.total_s  AS swim_s,  sw.rank_stage AS swim_rank,
            sw.rank_gender AS swim_rank_g, sw.avg_pace_s AS swim_pace,
            b1.total_s  AS bike1_s, b1.rank_stage AS bike1_rank,
            b1.rank_gender AS bike1_rank_g, b1.avg_speed_kmh AS bike1_speed,
            b2.total_s  AS bike2_s, b2.rank_stage AS bike2_rank,
            b2.rank_gender AS bike2_rank_g, b2.avg_speed_kmh AS bike2_speed,
            ru.total_s  AS run_s,   ru.rank_stage AS run_rank,
            ru.rank_gender AS run_rank_g, ru.avg_pace_s AS run_pace
        FROM participants p
        LEFT JOIN overall_results o  ON o.participant_id=p.id
        LEFT JOIN stage_totals sw ON sw.participant_id=p.id AND sw.stage='swim'
        LEFT JOIN stage_totals b1 ON b1.participant_id=p.id AND b1.stage='bike_day1'
        LEFT JOIN stage_totals b2 ON b2.participant_id=p.id AND b2.stage='bike_day2'
        LEFT JOIN stage_totals ru ON ru.participant_id=p.id AND ru.stage='run'
        WHERE p.race_year=%s AND p.format='individual'
        ORDER BY (o.total_s IS NULL), o.total_s, p.bib
    """, (race_year,))
    individual = cur.fetchall()

    # Эстафетные члены (все трое)
    cur.execute("""
        SELECT
            p.bib, p.relay_team_name, p.relay_stage, p.surname, p.name, p.status,
            sw.total_s AS swim_s,  sw.avg_pace_s AS swim_pace,
            b1.total_s AS bike1_s, b1.avg_speed_kmh AS bike1_speed,
            b2.total_s AS bike2_s, b2.avg_speed_kmh AS bike2_speed,
            ru.total_s AS run_s,   ru.avg_pace_s AS run_pace
        FROM participants p
        LEFT JOIN stage_totals sw ON sw.participant_id=p.id AND sw.stage='swim'
        LEFT JOIN stage_totals b1 ON b1.participant_id=p.id AND b1.stage='bike_day1'
        LEFT JOIN stage_totals b2 ON b2.participant_id=p.id AND b2.stage='bike_day2'
        LEFT JOIN stage_totals ru ON ru.participant_id=p.id AND ru.stage='run'
        WHERE p.race_year=%s AND p.format='relay'
        ORDER BY p.bib, p.relay_stage
    """, (race_year,))
    relay_rows = cur.fetchall()

    # Группировка эстафет по bib
    relay_teams: dict[str, dict] = {}
    for row in relay_rows:
        bib = row["bib"]
        if bib not in relay_teams:
            relay_teams[bib] = {
                "bib": bib,
                "team_name": row["relay_team_name"] or "",
                "members": [],
            }
        relay_teams[bib]["members"].append({
            "relay_stage": row["relay_stage"],
            "surname": row["surname"],
            "name": row["name"],
            "status": row["status"],
            "swim_s":   row["swim_s"],  "swim_pace":   row["swim_pace"],
            "bike1_s":  row["bike1_s"], "bike1_speed": row["bike1_speed"],
            "bike2_s":  row["bike2_s"], "bike2_speed": row["bike2_speed"],
            "run_s":    row["run_s"],   "run_pace":    row["run_pace"],
        })

    # Вычислить общее время эстафеты (сумма swim+bike1+bike2+run без None)
    relay_list = []
    for team in relay_teams.values():
        times = []
        for m in team["members"]:
            for key in ("swim_s", "bike1_s", "bike2_s", "run_s"):
                v = m.get(key)
                if v is not None:
                    times.append(v)
        team["overall_s"] = sum(times) if times else None
        relay_list.append(team)
    relay_list.sort(key=lambda t: (t["overall_s"] is None, t["overall_s"] or 0, t["bib"]))

    return {"individual": individual, "relay": relay_list}


def get_checkpoint_times_for_year(conn, race_year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT ct.participant_id, ct.checkpoint_id, ct.cumulative_s, ct.split_s, "
        "c.stage, c.seq, c.label, c.distance_km "
        "FROM checkpoint_times ct "
        "JOIN checkpoints c ON c.id=ct.checkpoint_id "
        "WHERE c.race_year=%s ORDER BY ct.participant_id, c.stage, c.seq",
        (race_year,)
    )
    return cur.fetchall()
