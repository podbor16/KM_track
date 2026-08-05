import os
import logging
import mysql.connector
from typing import Optional

from src.siberman.finish_counts import get_prior_finish_count

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


def get_race_start(conn, race_year: int):
    """Абсолютное время старта гонки (день 1, плавание) — датой + временем.
    None, если для этого года ещё не сохранено (загрузка была до миграции
    004 или race_start не передан при апрувe)."""
    cur = conn.cursor()
    cur.execute("SELECT race_start FROM race_config WHERE race_year=%s", (race_year,))
    row = cur.fetchone()
    return row[0] if row else None


def set_race_start(conn, race_year: int, race_start) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO race_config (race_year, race_start) VALUES (%s, %s)
           ON DUPLICATE KEY UPDATE race_start=VALUES(race_start)""",
        (race_year, race_start)
    )


def get_stage_starts(conn, race_year: int) -> dict:
    """Расписание Вело Дня 2 и Бега (задаётся в админке отдельно от
    race_start) — None, если ещё не сохранено для этого года. Плавание и
    Вело День 1 своего расписания не хранят (см. 005_stage_starts.sql)."""
    cur = conn.cursor()
    cur.execute("SELECT bike2_start, run_start FROM race_config WHERE race_year=%s", (race_year,))
    row = cur.fetchone()
    return {"bike2_start": row[0] if row else None, "run_start": row[1] if row else None}


def set_stage_starts(conn, race_year: int, bike2_start, run_start) -> None:
    """Требует уже существующую строку race_config (race_start сохраняется
    раньше, при апруве загрузки) — обновляет расписание на месте."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE race_config SET bike2_start=%s, run_start=%s WHERE race_year=%s",
        (bike2_start, run_start, race_year)
    )


def get_copernico_run_enabled(conn, race_year: int) -> bool:
    """Флаг live-опроса Copernico для бегового этапа (задача 6 Live v2) —
    проверяется в apply_copernico_snapshot() перед записью, управляется
    из админки. False (в т.ч. если для года ещё нет строки race_config),
    если явно не включён."""
    cur = conn.cursor()
    cur.execute("SELECT copernico_run_enabled FROM race_config WHERE race_year=%s", (race_year,))
    row = cur.fetchone()
    return bool(row[0]) if row else False


def set_copernico_run_enabled(conn, race_year: int, enabled: bool) -> None:
    """Требует уже существующую строку race_config (см. set_stage_starts) —
    обновляет флаг на месте."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE race_config SET copernico_run_enabled=%s WHERE race_year=%s",
        (enabled, race_year)
    )


def get_latest_race_year(conn) -> Optional[int]:
    """Последний (по номеру) год с загруженными данными — используется
    ТЕСТОВОЙ страницей (/siberman/test, ?latest=1), чтобы сразу видеть
    свежезалитый тестовый год, не трогая настройку публичного года."""
    cur = conn.cursor()
    cur.execute("SELECT race_year FROM race_config ORDER BY race_year DESC LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else None


def get_public_race_year(conn) -> Optional[int]:
    """Год, который показывается на ПУБЛИЧНОЙ странице результатов — не
    обязательно последний загруженный (2026-08-05: тестовые данные под
    новым годом на /siberman/test не должны утекать на прод). Явно
    задаётся через set_public_race_year() в админке; если ещё ни разу не
    задан — откат на "последний год" (см. 007_public_year.sql: миграция
    сама помечает текущий последний год публичным при накатке)."""
    cur = conn.cursor()
    cur.execute("SELECT race_year FROM race_config WHERE is_public=1 ORDER BY race_year DESC LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else get_latest_race_year(conn)


def set_public_race_year(conn, race_year: int) -> None:
    """Ровно один год публичный одновременно — снимаем флаг со всех
    остальных."""
    cur = conn.cursor()
    cur.execute("UPDATE race_config SET is_public=0 WHERE race_year<>%s", (race_year,))
    cur.execute("UPDATE race_config SET is_public=1 WHERE race_year=%s", (race_year,))


def get_all_records(conn) -> list[dict]:
    """Все рекорды Siberman (не привязаны к году) — для отдачи на
    публичную страницу, см. 006_records.sql."""
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT column_key, category, best_s, holder_name, holder_team, year_set FROM siberman_records")
    return cur.fetchall()


def write_best_record(conn, column_key: str, category: str,
                       candidates: list[tuple[int, str, Optional[str]]], race_year: int) -> None:
    """ПОЛНЫЙ пересчёт (не инкрементальное "побил — не побил") — best_s/
    holder_*/year_set выставляются заново на каждый apply как минимум
    среди НЕИЗМЕННОГО исторического baseline_* (см. 007/008 миграции) и
    переданных ЖИВЫХ кандидатов этого года. Если прошлый рекордсмен года
    с тех пор сошёл (dnf/dsq) — он просто не попадёт в candidates на этот
    раз, и результат "откатится" сам собой к следующему подходящему или к
    baseline (2026-08-05, второй раунд: рекорд должен быть виден в
    live-режиме, а не только после финиша всей гонки, и пропадать при
    DNF — инкрементальное сравнение этого не умеет, нужен пересчёт).
    Молча ничего не делает, если для этой пары (column_key, category) нет
    строки baseline (значит, эта категория не отслеживается)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT baseline_s, baseline_holder_name, baseline_holder_team, baseline_year_set "
        "FROM siberman_records WHERE column_key=%s AND category=%s",
        (column_key, category)
    )
    row = cur.fetchone()
    if row is None:
        return
    best_s, holder_name, holder_team, year_set = row
    for value, name, team in candidates:
        if value < best_s:
            best_s, holder_name, holder_team, year_set = value, name, team, race_year
    cur.execute(
        "UPDATE siberman_records SET best_s=%s, holder_name=%s, holder_team=%s, year_set=%s "
        "WHERE column_key=%s AND category=%s",
        (best_s, holder_name, holder_team, year_set, column_key, category)
    )


def clear_race_year(conn, race_year: int) -> None:
    """Удалить всех участников (и каскадно все связанные данные) за год."""
    cur = conn.cursor()
    cur.execute("DELETE FROM participants WHERE race_year=%s", (race_year,))


def upsert_participant(conn, p: dict) -> int:
    """Вставить/обновить участника. Возвращает id."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO participants
           (race_year, bib, surname, name, gender, country, city,
            format, relay_team_name, relay_stage, status, dnf_stage, bike_day2_handicap_s)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE
             surname=VALUES(surname), name=VALUES(name), gender=VALUES(gender),
             country=VALUES(country), city=VALUES(city), format=VALUES(format),
             relay_team_name=VALUES(relay_team_name), relay_stage=VALUES(relay_stage),
             status=VALUES(status), dnf_stage=VALUES(dnf_stage),
             bike_day2_handicap_s=VALUES(bike_day2_handicap_s)""",
        (p["race_year"], p["bib"], p["surname"], p["name"], p["gender"],
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


def get_participants_for_year(conn, race_year: int) -> list[dict]:
    """Все участники года плоским списком (без JOIN на stage_totals) — для
    recompute_totals_ranks_records()/copernico_run.py, где нужен просто
    id+bib+gender+format+relay_stage+status+surname+name+relay_team_name."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, bib, surname, name, gender, format, relay_team_name, "
        "relay_stage, status, dnf_stage "
        "FROM participants WHERE race_year=%s",
        (race_year,)
    )
    return cur.fetchall()


def update_participant_status(conn, participant_id: int, status: str, dnf_stage: Optional[str]) -> None:
    """Точечное обновление статуса участника (например, из live-опроса
    Copernico) — в отличие от upsert_participant, не требует полного
    словаря участника."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE participants SET status=%s, dnf_stage=%s WHERE id=%s",
        (status, dnf_stage, participant_id)
    )


def get_checkpoint_times_for_year(
    conn, race_year: int
) -> tuple[dict[int, dict[str, dict[int, int]]], dict[int, dict[str, dict[int, int]]]]:
    """(cumulative, splits): participant_id -> stage -> seq -> секунды.

    Сплиты (время МЕЖДУ соседними КТ) нужны для страницы участника (задача
    5) — не задействуются в существующей gap-логике на results.html, чтобы
    не менять форму уже используемого дерева `cp` (там ожидается голое
    число cumulative_s, не вложенный объект).
    """
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT ct.participant_id, c.stage, c.seq, ct.cumulative_s, ct.split_s
        FROM checkpoint_times ct
        JOIN checkpoints c ON c.id = ct.checkpoint_id
        JOIN participants p ON p.id = ct.participant_id
        WHERE p.race_year=%s
    """, (race_year,))
    cumulative: dict[int, dict[str, dict[int, int]]] = {}
    splits: dict[int, dict[str, dict[int, int]]] = {}
    for row in cur.fetchall():
        if row["cumulative_s"] is not None:
            cumulative.setdefault(row["participant_id"], {}).setdefault(row["stage"], {})[row["seq"]] = row["cumulative_s"]
        if row["split_s"] is not None:
            splits.setdefault(row["participant_id"], {}).setdefault(row["stage"], {})[row["seq"]] = row["split_s"]
    return cumulative, splits


def get_results_for_year(conn, race_year: int) -> dict:
    """Вернуть все результаты за год для публичной страницы."""
    cur = conn.cursor(dictionary=True)
    cp_by_pid, split_by_pid = get_checkpoint_times_for_year(conn, race_year)

    # Личные участники — все данные в одной строке (pivot через LEFT JOIN)
    cur.execute("""
        SELECT
            p.id, p.bib, p.surname, p.name, p.gender, p.country, p.city, p.status,
            p.bike_day2_handicap_s AS bike2_start_s,
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
    for p in individual:
        pid = p.pop("id")
        p["cp"] = cp_by_pid.get(pid, {})
        p["splits"] = split_by_pid.get(pid, {})
        # Только личный зачёт (запрошено пользователем 2026-08-05) — у
        # эстафетных команд свой "стаж" не считается.
        p["finish_count"] = get_prior_finish_count(p["surname"], p["name"])

    # Эстафетные члены (все трое)
    cur.execute("""
        SELECT
            p.id, p.bib, p.relay_team_name, p.relay_stage, p.surname, p.name, p.gender, p.status,
            p.bike_day2_handicap_s AS bike2_start_s,
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
            "gender": row["gender"],
            "status": row["status"],
            "bike2_start_s": row["bike2_start_s"],
            "cp": cp_by_pid.get(row["id"], {}),
            "splits": split_by_pid.get(row["id"], {}),
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

    race_start = get_race_start(conn, race_year)
    stage_starts = get_stage_starts(conn, race_year)

    return {
        "individual": individual, "relay": relay_list, "race_start": race_start, "race_year": race_year,
        "bike2_start": stage_starts["bike2_start"], "run_start": stage_starts["run_start"],
    }
