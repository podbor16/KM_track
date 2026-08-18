"""
Запросы к БД: результаты забегов, статистика, сегменты, вспомогательные функции.
"""

import logging
import time
import datetime
from typing import Optional, List, Dict, Any

from mysql.connector import Error

from .db_pool import (
    get_pooled_connection,
    find_table,
    get_table_row_count_fast,
    get_table_columns,
    get_cached_tables,
    _validate_table_name,
)
from src.krasmarafon.services.tilda_webhook import is_name_suspicious

logger = logging.getLogger(__name__)


# ============================================================
# ПОЛУЧЕНИЕ РЕЗУЛЬТАТОВ ПО EVENT_ID
# ============================================================

_results_cache: dict = {}
_results_cache_ts: dict = {}
RESULTS_CACHE_TTL = 5  # секунд — короткий TTL для live-данных КТ

_segments_cache: dict[int, list] = {}
_segments_cache_ts: dict[int, float] = {}
SEGMENTS_CACHE_TTL = 30  # секунд

# Кеш данных события (gun_time и т.д.) — с TTL, чтобы изменения в events отражались быстро
_event_info_cache: dict = {}
_event_info_cache_ts: dict = {}
EVENT_INFO_CACHE_TTL = 5  # секунд
_prev_year_cache: dict = {}    # get_prev_year_results — финиши прошлого года

_stats_cache: dict = {}
_stats_cache_ts: dict = {}
STATS_CACHE_TTL = 60  # секунд — статистика не требует real-time точности


def get_race_results_by_event_id(event_id: int) -> List[Dict[str, Any]]:
    """
    Результаты забега по event_id с JOIN к events.

    Returns:
        Список словарей с результатами, отсортированных по времени финиша.
    """
    _now = time.time()
    if event_id in _results_cache and (_now - _results_cache_ts.get(event_id, 0)) < RESULTS_CACHE_TTL:
        return _results_cache[event_id]

    logger.info(f"🔍 Загрузка результатов для event_id={event_id}")

    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return []

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)

        results_table = find_table(["results", "Results", "RESULTS", "гонка", "забеги"])

        if not results_table:
            logger.error("❌ Таблица results не найдена")
            return []

        query = f"""
        SELECT
            r.id,
            r.surname,
            r.name,
            r.birthday,
            r.client_id,
            r.event_id,
            r.sex,
            r.start_number,
            r.category,
            r.race_status,
            r.time_gun_start,
            r.time_clear_start,
            r.time_gun_finish,
            r.time_clear_finish,
            r.rank_absolute,
            r.rank_sex,
            r.rank_category,
            r.finish_pace_avg,
            r.finish_pace_avg_gun,
            r.finish_pace_avg_clean,
            r.time_clear_kt1,
            r.time_clear_kt2,
            r.time_clear_kt3,
            r.time_clear_kt4,
            r.time_clear_kt5,
            r.time_clear_kt6,
            r.time_clear_kt7,
            r.pace_avg_kt1,
            r.pace_avg_kt2,
            r.pace_avg_kt3,
            r.pace_avg_kt4,
            r.pace_avg_kt5,
            r.pace_avg_kt6,
            r.pace_avg_kt7,
            r.rank_absolute_clean,
            r.rank_sex_clean,
            r.rank_category_clean,
            e.event_name,
            e.event_distance,
            e.event_year
        FROM `{results_table}` r
        LEFT JOIN events e ON r.event_id = e.id
        WHERE r.event_id = %s
        ORDER BY r.time_clear_finish ASC
        """

        cursor.execute(query, (event_id,))
        results = cursor.fetchall()
        cursor.close()

        results_list = [dict(r) for r in results] if results else []
        logger.info(f"✅ Найдено {len(results_list)} результатов для event_id={event_id}")
        _results_cache[event_id] = results_list
        _results_cache_ts[event_id] = time.time()
        return results_list

    except Exception as e:
        logger.error(f"❌ Ошибка при получении результатов: {e}")
        return []
    finally:
        try:
            connection.close()
        except Exception:
            pass


def get_race_results_by_event_id_and_year(event_name: str, year: int) -> List[Dict[str, Any]]:
    """
    Результаты забега по названию события и году.

    Returns:
        Список словарей с результатами, отсортированных по рангу.
    """
    _cache_key = f"{event_name}|{year}"
    _now = time.time()
    if _cache_key in _results_cache and (_now - _results_cache_ts.get(_cache_key, 0)) < RESULTS_CACHE_TTL:
        return _results_cache[_cache_key]

    logger.info(f"🔍 Загрузка результатов для {event_name} {year}")

    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return []

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)

        query = """
        SELECT
            r.id,
            r.surname,
            r.name,
            r.birthday,
            r.client_id,
            r.event_id,
            r.sex,
            r.start_number,
            r.category,
            r.race_status,
            r.time_gun_start,
            r.time_clear_start,
            r.time_gun_finish,
            r.time_clear_finish,
            r.rank_absolute,
            r.rank_sex,
            r.rank_category,
            r.finish_pace_avg,
            r.finish_pace_avg_gun,
            r.finish_pace_avg_clean,
            r.time_clear_kt1,
            r.time_clear_kt2,
            r.time_clear_kt3,
            r.time_clear_kt4,
            r.time_clear_kt5,
            r.time_clear_kt6,
            r.time_clear_kt7,
            r.pace_avg_kt1,
            r.pace_avg_kt2,
            r.pace_avg_kt3,
            r.pace_avg_kt4,
            r.pace_avg_kt5,
            r.pace_avg_kt6,
            r.pace_avg_kt7,
            r.rank_absolute_clean,
            r.rank_sex_clean,
            r.rank_category_clean,
            e.event_name,
            e.event_distance,
            e.event_year
        FROM results r
        INNER JOIN events e ON r.event_id = e.id
        WHERE e.event_name = %s AND e.event_year = %s
        ORDER BY r.rank_absolute ASC
        """

        cursor.execute(query, (event_name, year))
        results = cursor.fetchall()

        if results:
            results_list = [dict(r) for r in results]
            logger.info(f"✅ Найдено {len(results_list)} результатов для {event_name} {year}")
            _results_cache[_cache_key] = results_list
            _results_cache_ts[_cache_key] = time.time()
            return results_list
        else:
            logger.warning(f"⚠️ Результаты не найдены для {event_name} {year}")
            return []

    except Exception as e:
        logger.error(f"❌ Ошибка при получении результатов: {e}")
        return []
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass


def get_checkpoint_distances(event_id: int) -> List[float]:
    """
    Дистанции контрольных точек для события из events.checkpoint_distances.

    Returns:
        Список дистанций в км, напр. [0.0, 2.5, 5.0]. При ошибке — пустой список.
    """
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ get_checkpoint_distances: нет соединения")
        return []

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT checkpoint_distances, event_distance FROM events WHERE id = %s",
            (event_id,)
        )
        row = cursor.fetchone()
        cursor.close()

        if not row:
            logger.warning(f"⚠️ get_checkpoint_distances: event_id={event_id} не найден")
            return []

        raw = row.get("checkpoint_distances")
        if raw is None:
            total = float(row.get("event_distance") or 0)
            return [0.0, total] if total else []

        if isinstance(raw, list):
            return [float(x) for x in raw]
        if isinstance(raw, str):
            import json as _json
            return [float(x) for x in _json.loads(raw)]

        return []

    except Exception as e:
        logger.error(f"❌ get_checkpoint_distances error: {e}")
        return []
    finally:
        try:
            connection.close()
        except Exception:
            pass


def get_category_avg_paces(event_name: str, event_distance, year: int) -> Dict[str, float]:
    """
    Средняя скорость (км/ч) финишировавших по категориям для заданного события.
    Считает из time_clear_finish / event_distance (finish_pace_avg часто NULL).
    Fallback по приоритету: год+дистанция → все годы+дистанция → все годы.
    Один DB round-trip через UNION ALL с полем priority.

    Returns:
        Dict {category_str: avg_speed_kmh}
    """
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ get_category_avg_paces: нет соединения")
        return {}

    # Один запрос: приоритет 1=точный год+дистанция, 2=все годы+дистанция, 3=все годы
    UNION_SQL = """
        SELECT category, finish_secs, dist_km, priority FROM (
            SELECT r.category,
                   TIME_TO_SEC(r.time_clear_finish) AS finish_secs,
                   CAST(e.event_distance AS DECIMAL(6,2)) AS dist_km,
                   1 AS priority
            FROM results r INNER JOIN events e ON r.event_id = e.id
            WHERE e.event_name = %s AND e.event_year = %s AND e.event_distance = %s
              AND r.race_status = 'Finished' AND r.time_clear_finish IS NOT NULL
              AND r.category IS NOT NULL AND r.category != ''

            UNION ALL

            SELECT r.category,
                   TIME_TO_SEC(r.time_clear_finish),
                   CAST(e.event_distance AS DECIMAL(6,2)),
                   2
            FROM results r INNER JOIN events e ON r.event_id = e.id
            WHERE e.event_name = %s AND e.event_distance = %s
              AND r.race_status = 'Finished' AND r.time_clear_finish IS NOT NULL
              AND r.category IS NOT NULL AND r.category != ''

            UNION ALL

            SELECT r.category,
                   TIME_TO_SEC(r.time_clear_finish),
                   CAST(e.event_distance AS DECIMAL(6,2)),
                   3
            FROM results r INNER JOIN events e ON r.event_id = e.id
            WHERE e.event_name = %s
              AND r.race_status = 'Finished' AND r.time_clear_finish IS NOT NULL
              AND r.category IS NOT NULL AND r.category != ''
        ) AS combined
        ORDER BY priority ASC
    """

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        cursor.execute(UNION_SQL, (
            event_name, year, str(event_distance),  # priority 1
            event_name, str(event_distance),          # priority 2
            event_name,                               # priority 3
        ))
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            logger.warning(f"⚠️ get_category_avg_paces: нет финишировавших для {event_name} {year} дист={event_distance}")
            return {}

        # Берём только строки с наименьшим priority среди тех, что нашлись
        min_priority = min(r["priority"] for r in rows)
        best_rows = [r for r in rows if r["priority"] == min_priority]

        from collections import defaultdict
        speeds_by_cat: Dict[str, list] = defaultdict(list)
        for row in best_rows:
            cat = (row.get("category") or "").strip()
            finish_secs = row.get("finish_secs")
            dist_km = float(row.get("dist_km") or 0)
            if cat and finish_secs and dist_km > 0:
                hours = float(finish_secs) / 3600.0
                kmh = dist_km / hours
                if 3.0 <= kmh <= 30.0:
                    speeds_by_cat[cat].append(kmh)

        result = {cat: sum(speeds) / len(speeds) for cat, speeds in speeds_by_cat.items()}
        logger.info(f"✅ get_category_avg_paces: {len(result)} категорий для {event_name} {year} (priority={min_priority})")
        return result

    except Exception as e:
        logger.error(f"❌ get_category_avg_paces error: {e}")
        return {}
    finally:
        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# ИНФОРМАЦИЯ О СОБЫТИИ
# ============================================================

def get_event_info(event_name: str, year: int) -> Dict[str, Any]:
    """
    Строка из таблицы events по названию и году.

    Returns:
        Словарь с полями id, event_name, event_distance, event_date, checkpoint_distances
        или пустой словарь если не найдено.
    """
    connection = get_pooled_connection()
    if not connection:
        return {}

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT id, event_name, event_distance, event_date, checkpoint_distances, gun_time_utc "
            "FROM events WHERE event_name = %s AND event_year = %s LIMIT 1",
            (event_name, year)
        )
        row = cursor.fetchone()
        cursor.close()
        return row or {}
    except Exception as e:
        logger.error(f"❌ get_event_info error: {e}")
        return {}
    finally:
        try:
            connection.close()
        except Exception:
            pass


def get_event_info_by_id(event_id: int) -> Dict[str, Any]:
    """
    Строка из таблицы events по ID.

    Returns:
        Словарь с полями id, event_name, event_distance, event_date, checkpoint_distances
        или пустой словарь если не найдено.
    """
    _now = time.time()
    if event_id in _event_info_cache and (_now - _event_info_cache_ts.get(event_id, 0)) < EVENT_INFO_CACHE_TTL:
        return _event_info_cache[event_id]

    connection = get_pooled_connection()
    if not connection:
        return {}

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT id, event_name, event_distance, event_date, checkpoint_distances, event_year, gun_time_utc "
            "FROM events WHERE id = %s LIMIT 1",
            (event_id,)
        )
        row = cursor.fetchone()
        cursor.close()
        result = dict(row) if row else {}
        _event_info_cache[event_id] = result
        _event_info_cache_ts[event_id] = _now
        return result
    except Exception as e:
        logger.error(f"❌ get_event_info_by_id error: {e}")
        return {}
    finally:
        try:
            connection.close()
        except Exception:
            pass


def get_prev_year_results(event_name: str, event_distance, year: int) -> List[Dict[str, Any]]:
    """Результаты финишировавших в предыдущем году для расчёта исторического темпа."""
    _key = f"{event_name}|{event_distance}|{year}"
    if _key in _prev_year_cache:
        return _prev_year_cache[_key]

    connection = get_pooled_connection()
    if not connection:
        return []
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        cursor.execute(
            """
            SELECT r.surname, r.name, r.birthday, r.category, r.finish_pace_avg_clean
            FROM results r
            INNER JOIN events e ON r.event_id = e.id
            WHERE e.event_name = %s
              AND e.event_distance = %s
              AND e.event_year = %s
              AND r.race_status = 'Finished'
              AND r.time_clear_finish IS NOT NULL
              AND r.finish_pace_avg_clean IS NOT NULL
            """,
            (event_name, str(event_distance), year),
        )
        rows = cursor.fetchall()
        if not rows:
            cursor.execute(
                """
                SELECT r.surname, r.name, r.birthday, r.category, r.finish_pace_avg_clean
                FROM results r
                INNER JOIN events e ON r.event_id = e.id
                WHERE e.event_name = %s
                  AND e.event_year = %s
                  AND r.race_status = 'Finished'
                  AND r.time_clear_finish IS NOT NULL
                  AND r.finish_pace_avg_clean IS NOT NULL
                  AND r.finish_pace_avg_clean != ''
                """,
                (event_name, year),
            )
            rows = cursor.fetchall()
        cursor.close()
        result = [dict(r) for r in rows] if rows else []
        if result:  # не кешируем пустой список (мероприятие могло ещё не начаться)
            _prev_year_cache[_key] = result
        return result
    except Exception as e:
        logger.error(f"get_prev_year_results error: {e}")
        return []
    finally:
        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# СТАТИСТИКА ЗАБЕГА
# ============================================================

def get_race_stats_from_db(event_name: str) -> Dict[str, Any]:
    """
    Статистика по забегу: лучший результат, средние темпы по полам, история по годам.
    Группировка по дистанции (поддержка мультидистанционных событий типа «Жара»).
    """
    _now = time.time()
    if event_name in _stats_cache and (_now - _stats_cache_ts.get(event_name, 0)) < STATS_CACHE_TTL:
        return _stats_cache[event_name]

    logger.info(f"🔍 Получение статистики забега: {event_name}")

    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return {}

    cursor = None
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)

        cursor.execute(
            """
            SELECT r.surname, r.name, r.sex,
                   r.time_clear_finish, r.time_gun_finish,
                   r.finish_pace_avg_clean, r.finish_pace_avg_gun,
                   r.race_status, e.event_distance, e.event_year
            FROM results r
            INNER JOIN events e ON r.event_id = e.id
            WHERE e.event_name = %s
            ORDER BY e.event_distance, e.event_year DESC
            """,
            (event_name,)
        )
        all_results = cursor.fetchall()
        cursor.close()
        cursor = None

        if not all_results:
            logger.warning(f"⚠️ Нет данных для '{event_name}'")
            return {}

        def _fmt_dist(dist) -> str:
            if dist is None:
                return 'N/A'
            n = float(dist)
            return f"{int(n)} км" if n == int(n) else f"{n} км"

        def _td_sec(val) -> Optional[int]:
            if val is None:
                return None
            if hasattr(val, 'total_seconds'):
                s = int(val.total_seconds())
                return s if s > 0 else None
            return None

        def _pace_str(sec) -> str:
            if not sec:
                return "N/A"
            return f"{int(sec // 60):02d}:{int(sec % 60):02d} мин/км"

        def _time_str(val) -> str:
            sec = _td_sec(val)
            if not sec:
                return str(val) if val else 'N/A'
            h = sec // 3600
            m = (sec % 3600) // 60
            s = sec % 60
            return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

        # Группируем: dist_data[dist_str][year] = [rows...]
        dist_data: Dict[str, Dict[int, list]] = {}
        for r in all_results:
            dist = _fmt_dist(r['event_distance'])
            year = r['event_year']
            dist_data.setdefault(dist, {}).setdefault(year, []).append(r)

        distances_out = []

        for dist_str, year_map in dist_data.items():
            years_data = []
            dist_best: Optional[Dict] = None
            dist_best_raw = None
            all_male_paces: list = []
            all_female_paces: list = []

            for year in sorted(year_map.keys(), reverse=True):
                rows = year_map[year]
                finished = [r for r in rows if r['race_status'] in ('Finished', 'finished')]

                male_count = 0
                female_count = 0
                male_paces: list = []
                female_paces: list = []

                for r in finished:
                    sex = (r.get('sex') or '').lower()
                    is_male = sex == 'мужчина'
                    is_female = sex == 'женщина'
                    if is_male:
                        male_count += 1
                    elif is_female:
                        female_count += 1

                    pace_sec = _td_sec(r.get('finish_pace_avg_clean') or r.get('finish_pace_avg_gun'))
                    if pace_sec:
                        if is_male:
                            male_paces.append(pace_sec)
                            all_male_paces.append(pace_sec)
                        elif is_female:
                            female_paces.append(pace_sec)
                            all_female_paces.append(pace_sec)

                    tc = r.get('time_clear_finish')
                    tc_sec = _td_sec(tc)
                    if tc_sec:
                        if dist_best_raw is None or tc_sec < dist_best_raw:
                            dist_best_raw = tc_sec
                            pace_sec_best = _td_sec(r.get('finish_pace_avg_clean') or r.get('finish_pace_avg_gun'))
                            dist_best = {
                                'surname': r.get('surname', ''),
                                'name': r.get('name', ''),
                                'time': _time_str(tc),
                                'pace': _pace_str(pace_sec_best),
                                'year': year,
                            }

                combined = male_paces + female_paces
                avg_all = sum(combined) / len(combined) if combined else None
                avg_m = sum(male_paces) / len(male_paces) if male_paces else None
                avg_f = sum(female_paces) / len(female_paces) if female_paces else None

                years_data.append({
                    'year': year,
                    'total_runners': len(rows),
                    'finished_runners': len(finished),
                    'male_count': male_count,
                    'female_count': female_count,
                    'average_pace': _pace_str(avg_all),
                    'male_avg_pace': _pace_str(avg_m),
                    'female_avg_pace': _pace_str(avg_f),
                })

            combined_all = all_male_paces + all_female_paces
            avg_all_ov = sum(combined_all) / len(combined_all) if combined_all else None
            avg_m_ov = sum(all_male_paces) / len(all_male_paces) if all_male_paces else None
            avg_f_ov = sum(all_female_paces) / len(all_female_paces) if all_female_paces else None

            distances_out.append({
                'distance': dist_str,
                'years_data': years_data,
                'best_result': dist_best,
                'average_paces': {
                    'all': _pace_str(avg_all_ov),
                    'male': _pace_str(avg_m_ov),
                    'female': _pace_str(avg_f_ov),
                },
            })

        logger.info(f"✅ Статистика загружена: {event_name}, дистанций: {len(distances_out)}")
        result = {'race_name': event_name, 'distances': distances_out}
        _stats_cache[event_name] = result
        _stats_cache_ts[event_name] = time.time()
        return result

    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}\n{repr(e)}")
        return {}
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass


# ============================================================
# СЕГМЕНТЫ
# ============================================================

def get_result_segments(result_id: int) -> List[Dict[str, Any]]:
    """
    Сегменты результата из таблицы result_segments.

    Returns:
        Список словарей с данными сегментов (segment_code, sg_time_clear, sg_pace_avg, ранги).
    """
    _now = time.time()
    if result_id in _segments_cache and (_now - _segments_cache_ts.get(result_id, 0)) < SEGMENTS_CACHE_TTL:
        logger.debug(f"📦 Сегменты из кеша для result_id={result_id}")
        return _segments_cache[result_id]

    logger.info(f"🔍 Загрузка сегментов для result_id={result_id}")

    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return []

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)

        segments_table = find_table(["result_segments", "result_segment", "segments", "race_segments", "Сегменты результатов"])

        if not segments_table:
            logger.warning("⚠️ Таблица result_segments не найдена")
            return []

        columns = get_table_columns(segments_table)
        missing_cols = [col for col in ['result_id', 'segment_code'] if col not in columns]

        if missing_cols:
            logger.warning(f"⚠️ Отсутствуют требуемые колонки в {segments_table}: {missing_cols}")
            return []

        query = f"""
        SELECT *
        FROM `{segments_table}`
        WHERE result_id = %s
        ORDER BY
            CASE SUBSTRING_INDEX(segment_code, '-', 1)
                WHEN 'start' THEN 0
                WHEN 'kt1'   THEN 1
                WHEN 'kt2'   THEN 2
                WHEN 'kt3'   THEN 3
                WHEN 'kt4'   THEN 4
                WHEN 'kt5'   THEN 5
                ELSE 99
            END ASC,
            CASE SUBSTRING_INDEX(segment_code, '-', -1)
                WHEN 'kt1'    THEN 1
                WHEN 'kt2'    THEN 2
                WHEN 'kt3'    THEN 3
                WHEN 'kt4'    THEN 4
                WHEN 'kt5'    THEN 5
                WHEN 'finish' THEN 99
                ELSE 0
            END ASC
        """

        cursor.execute(query, (result_id,))
        segments = cursor.fetchall()
        cursor.close()

        logger.info(f"{'✅' if segments else 'ℹ️'} {'Найдено ' + str(len(segments)) + ' сегментов' if segments else 'Сегменты не найдены'} для result_id={result_id}")
        result = list(segments) if segments else []
        _segments_cache[result_id] = result
        _segments_cache_ts[result_id] = time.time()
        return result

    except Exception as e:
        logger.error(f"❌ Ошибка при получении сегментов: {e}")
        return []
    finally:
        if connection.is_connected():
            connection.close()


def _td_to_str(val) -> Optional[str]:
    """Конвертирует datetime.timedelta (TIME из MySQL) в 'HH:MM:SS' строку."""
    import datetime as _dt
    if val is None:
        return None
    if isinstance(val, _dt.timedelta):
        total = int(val.total_seconds())
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    return str(val)


def get_event_segment_rankings(event_id: int, segment_code: str) -> List[Dict[str, Any]]:
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение для get_event_segment_rankings")
        return []
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        query = """
        SELECT
            rs.result_id,
            rs.segment_code,
            rs.sg_time_clear, rs.sg_time_gun,
            rs.sg_pace_avg,   rs.sg_pace_avg_gun,
            rs.sg_rank_absolute,     rs.sg_rank_sex,     rs.sg_rank_category,
            rs.sg_rank_absolute_gun, rs.sg_rank_sex_gun, rs.sg_rank_category_gun,
            r.surname, r.name, r.start_number, r.sex, r.category
        FROM `result_segments` rs
        JOIN `results` r ON rs.result_id = r.id
        WHERE rs.event_id = %s AND rs.segment_code = %s
          AND rs.sg_time_clear IS NOT NULL
        ORDER BY rs.sg_time_clear ASC
        """
        cursor.execute(query, (event_id, segment_code))
        rows = cursor.fetchall()
        cursor.close()
        time_fields = ('sg_time_clear', 'sg_time_gun', 'sg_pace_avg', 'sg_pace_avg_gun')
        result = []
        for row in rows:
            for f in time_fields:
                if f in row:
                    row[f] = _td_to_str(row[f])
            result.append(row)
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка get_event_segment_rankings: {e}")
        return []
    finally:
        if connection.is_connected():
            connection.close()


def get_event_segment_codes(event_id: int) -> List[str]:
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение для get_event_segment_codes")
        return []
    try:
        cursor = connection.cursor(buffered=True)
        query = """
        SELECT DISTINCT segment_code,
            CASE SUBSTRING_INDEX(segment_code, '-', 1)
                WHEN 'start' THEN 0 WHEN 'kt1' THEN 1 WHEN 'kt2' THEN 2
                WHEN 'kt3'   THEN 3 WHEN 'kt4' THEN 4 WHEN 'kt5' THEN 5
                WHEN 'kt6'   THEN 6 WHEN 'kt7' THEN 7
                ELSE 99 END AS ord
        FROM `result_segments`
        WHERE event_id = %s AND sg_time_clear IS NOT NULL
        ORDER BY ord ASC
        """
        cursor.execute(query, (event_id,))
        rows = cursor.fetchall()
        cursor.close()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"❌ Ошибка get_event_segment_codes: {e}")
        return []
    finally:
        if connection.is_connected():
            connection.close()


def find_result_by_client_id(client_identifier) -> Optional[Dict[str, Any]]:
    """
    Строка результата в таблице `results` по client_id, start_number или id.

    Args:
        client_identifier: client_id, start_number или числовой id

    Returns:
        dict строки результата или None
    """
    logger.info(f"🔎 Поиск result по идентификатору: {client_identifier}")
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение для find_result_by_client_id")
        return None

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)

        try:
            numeric = int(client_identifier)
        except Exception:
            numeric = None

        cursor.execute("SELECT * FROM results WHERE client_id = %s LIMIT 1", (str(client_identifier),))
        row = cursor.fetchone()
        if row:
            cursor.close()
            return dict(row)

        if numeric is not None:
            cursor.execute("SELECT * FROM results WHERE start_number = %s LIMIT 1", (numeric,))
            row = cursor.fetchone()
            if row:
                cursor.close()
                return dict(row)

            cursor.execute("SELECT * FROM results WHERE id = %s LIMIT 1", (numeric,))
            row = cursor.fetchone()
            if row:
                cursor.close()
                return dict(row)

        cursor.close()
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка find_result_by_client_id: {e}")
        return None
    finally:
        try:
            if connection.is_connected():
                connection.close()
        except Exception:
            pass


# ============================================================
# DEBUG ENDPOINT
# ============================================================

def get_database_info_optimized() -> Dict[str, Any]:
    """Информация о БД для debug endpoint (использует INFORMATION_SCHEMA)."""
    debug_info = {
        "connection": "❌ Failed",
        "tables_list": [],
        "tables": [],
        "errors": []
    }

    connection = get_pooled_connection()
    if not connection:
        debug_info["errors"].append("Не удалось получить соединение")
        return debug_info

    debug_info["connection"] = "✅ Connected successfully"

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)

        tables = get_cached_tables()
        debug_info["tables_list"] = tables

        for table_name in tables:
            table_info = {
                "name": table_name,
                "row_count": 0,
                "columns": [],
                "sample_rows": []
            }

            try:
                table_info["row_count"] = get_table_row_count_fast(table_name)
                table_info["columns"] = get_table_columns(table_name)
                cursor.execute(f"SELECT * FROM `{_validate_table_name(table_name)}` LIMIT 2")
                samples = cursor.fetchall()
                table_info["sample_rows"] = samples if samples else []
                debug_info["tables"].append(table_info)

            except Exception as table_error:
                debug_info["errors"].append(f"❌ Error reading table {table_name}: {str(table_error)}")
                logger.error(f"Error reading table {table_name}: {table_error}")

        cursor.close()

    except Exception as e:
        debug_info["errors"].append(f"❌ General error: {str(e)}")
        logger.error(f"Error in debug info: {e}")
    finally:
        if connection.is_connected():
            connection.close()

    return debug_info


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _parse_age_and_sex(birthdate_or_age, sex: str = None):
    """(age, is_male) из даты рождения/возраста/пола — общий разбор,
    переиспользуется calculate_age_group() и get_age_group_label().
    Возвращает (None, is_male), если возраст не удалось определить."""
    age = None

    if isinstance(birthdate_or_age, (datetime.date, datetime.datetime)):
        if birthdate_or_age.year == 1900:
            # Сентинел "дата рождения неизвестна" (leads.birthday NOT NULL
            # DEFAULT '1900-01-01', bulk_import_leads() — регистрация без
            # указанной даты) — не настоящий возраст 126 лет.
            age = None
        else:
            age = datetime.datetime.now().year - birthdate_or_age.year
    elif isinstance(birthdate_or_age, str):
        if birthdate_or_age[:4] == '1900':
            age = None
        else:
            try:
                birth_date = datetime.datetime.strptime(birthdate_or_age[:10], '%Y-%m-%d')
                age = datetime.datetime.now().year - birth_date.year
            except Exception:
                try:
                    age = int(birthdate_or_age)
                except Exception:
                    age = None
    elif isinstance(birthdate_or_age, int):
        age = birthdate_or_age

    is_male = True
    if sex:
        sex_lower = str(sex).lower().strip()
        if sex_lower in ['female', 'ж', 'женщина', 'women', 'f']:
            is_male = False

    return age, is_male


_age_group_cache: dict = {}
_age_group_cache_ts: float = 0.0
AGE_GROUP_CACHE_TTL = 60  # админ-конфиг — короткий TTL, правки видны быстро


def _get_age_group_configs() -> dict:
    """{(event_name, event_distance, 'M'|'F'): [(min_age, max_age, label), ...]}
    отсортировано по min_age, из age_group_configs. Кэш на весь процесс,
    TTL 60с — таблицу правят из /admin, изменения должны быть видны быстро,
    но не на каждый запрос."""
    global _age_group_cache, _age_group_cache_ts
    now = time.time()
    if _age_group_cache and (now - _age_group_cache_ts) < AGE_GROUP_CACHE_TTL:
        return _age_group_cache

    conn = get_pooled_connection()
    if not conn:
        return _age_group_cache or {}
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(
            "SELECT event_name, event_distance, sex, min_age, max_age, label "
            "FROM age_group_configs ORDER BY event_name, event_distance, sex, min_age"
        )
        rows = cur.fetchall()
        cur.close()
        cache: dict = {}
        for r in rows:
            key = (r['event_name'], r['event_distance'], r['sex'])
            cache.setdefault(key, []).append((r['min_age'], r['max_age'], r['label']))
        _age_group_cache = cache
        _age_group_cache_ts = now
        return cache
    except Exception as e:
        logger.error(f"_get_age_group_configs error: {e}")
        return _age_group_cache or {}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_age_group_label(event_name: str, event_distance: str, birthdate_or_age, sex: str = None) -> str:
    """Возрастная группа с учётом границ, заданных в /admin для конкретных
    (event_name, event_distance). Два разных случая "нет подходящего
    брекета" различаются осознанно:
    - для события/дистанции вообще не настроены границы (напр. "2 км" —
      единая группа без деления по возрасту) — пустая строка, тут просто
      нет понятия "категория";
    - границы настроены, но возраст КОНКРЕТНОГО участника не попадает ни в
      один из них (напр. регистрация младше официального минимального
      возраста дистанции, ещё не вычищенная организатором) — это сигнал
      реальной проблемы данных, а не "категория не нужна", поэтому явный
      маркер "Ошибка возраста", а не тихая пустая строка."""
    age, is_male = _parse_age_and_sex(birthdate_or_age, sex)
    if age is None:
        return 'Неизвестно'

    sex_key = 'M' if is_male else 'F'
    brackets = _get_age_group_configs().get((event_name, event_distance, sex_key))
    if brackets:
        for min_age, max_age, label in brackets:
            if age >= min_age and (max_age is None or age <= max_age):
                return label
        return 'Ошибка возраста'

    return ''


def _invalidate_age_group_cache() -> None:
    global _age_group_cache_ts
    _age_group_cache_ts = 0.0


def list_age_groups(event_name: Optional[str] = None, event_distance: Optional[str] = None) -> List[Dict[str, Any]]:
    """Границы для /admin — без кеша, всегда актуальные (в отличие от
    _get_age_group_configs(), которым пользуется отображение стартового
    списка)."""
    conn = get_pooled_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        conds, params = [], []
        if event_name is not None:
            conds.append("event_name = %s"); params.append(event_name)
        if event_distance is not None:
            conds.append("event_distance = %s"); params.append(event_distance)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        cur.execute(
            f"SELECT * FROM age_group_configs {where} "
            "ORDER BY event_name, event_distance, sex, min_age",
            params,
        )
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"list_age_groups error: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def create_age_group(event_name: str, event_distance: str, sex: str,
                      min_age: int, max_age: Optional[int], label: str) -> Optional[Dict[str, Any]]:
    conn = get_pooled_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(
            "INSERT INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (event_name, event_distance, sex, min_age, max_age, label),
        )
        conn.commit()
        new_id = cur.lastrowid
        cur.execute("SELECT * FROM age_group_configs WHERE id = %s", (new_id,))
        row = cur.fetchone()
        cur.close()
        _invalidate_age_group_cache()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"create_age_group error: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


_AGE_GROUP_UPDATABLE = ('event_name', 'event_distance', 'sex', 'min_age', 'max_age', 'label')


def update_age_group(config_id: int, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    safe = {k: v for k, v in fields.items() if k in _AGE_GROUP_UPDATABLE}
    if not safe:
        return None
    conn = get_pooled_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        set_clause = ", ".join(f"{col} = %s" for col in safe)
        cur.execute(
            f"UPDATE age_group_configs SET {set_clause} WHERE id = %s",
            list(safe.values()) + [config_id],
        )
        conn.commit()
        cur.execute("SELECT * FROM age_group_configs WHERE id = %s", (config_id,))
        row = cur.fetchone()
        cur.close()
        _invalidate_age_group_cache()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"update_age_group error: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def delete_age_group(config_id: int) -> bool:
    conn = get_pooled_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor(buffered=True)
        cur.execute("DELETE FROM age_group_configs WHERE id = %s", (config_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        cur.close()
        if deleted:
            _invalidate_age_group_cache()
        return deleted
    except Exception as e:
        logger.error(f"delete_age_group error: {e}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def calculate_age_group(birthdate_or_age, sex: str = None) -> str:
    """
    Возрастная группа по дате рождения/возрасту и полу — дефолт, когда для
    события/дистанции не настроены свои границы (см. get_age_group_label()).

    Returns:
        Строка с названием возрастной группы.
    """
    if not birthdate_or_age:
        return 'Неизвестно'

    try:
        age, is_male = _parse_age_and_sex(birthdate_or_age, sex)
        if age is None:
            return 'Неизвестно'

        if is_male:
            if age < 49:
                return 'мужчины до 49 лет (1977 г.р. и младше)'
            elif age <= 59:
                return 'мужчины 50-59 лет (1967-1976 г.р.)'
            elif age <= 64:
                return 'мужчины 60-64 года (1962-1966 г.р.)'
            elif age <= 69:
                return 'мужчины 65-69 лет (1957-1961 г.р.)'
            elif age <= 74:
                return 'мужчины 70-74 года (1952-1956 г.р.)'
            else:
                return 'мужчины 75 лет и старше (1952-1956 г.р.)'
        else:
            if age < 49:
                return 'женщины до 49 лет (1977 г.р. и младше)'
            elif age <= 59:
                return 'женщины 50-59 лет (1967-1976 г.р.)'
            elif age <= 64:
                return 'женщины 60-64 года (1962-1966 г.р.)'
            else:
                return 'женщины 65 лет и старше (1961 г.р. и старше)'

    except Exception as e:
        logger.error(f"Ошибка при расчёте возрастной группы: {e}")
        return 'Неизвестно'


_start_list_cache: list = []
_start_list_cache_ts: float = 0.0
START_LIST_CACHE_TTL = 300  # 5 минут


def get_test_table_data() -> List[Dict[str, Any]]:
    """
    Данные участников из БД (стартовый список).
    При недоступности БД возвращает тестовые данные.
    """
    global _start_list_cache, _start_list_cache_ts
    _now_sl = time.time()
    if _start_list_cache and (_now_sl - _start_list_cache_ts) < START_LIST_CACHE_TTL:
        return _start_list_cache

    connection = get_pooled_connection()

    if connection:
        try:
            cursor = connection.cursor(dictionary=True, buffered=True)

            try:
                possible_tables = [
                    "Все заявки", "leads", "runners", "participants",
                    "entries", "registrations", "zajavki", "applications"
                ]

                target_table = find_table(possible_tables)

                if not target_table:
                    logger.error(f"❌ Таблица не найдена. Доступные таблицы: {get_cached_tables()}")
                    return get_test_data_fallback()

                cursor.execute(f"SELECT * FROM `{_validate_table_name(target_table)}`")
                records = cursor.fetchall()

                if records:
                    logger.info(f"✅ Получено {len(records)} записей из таблицы '{target_table}'")

                    for record in records:
                        age_info = (
                            record.get('birthday') or record.get('birthdate') or
                            record.get('Дата рождения') or record.get('age') or
                            record.get('Возраст')
                        )
                        sex_info = (
                            record.get('sex') or record.get('Пол') or
                            record.get('gender') or record.get('gender_en')
                        )
                        record['category'] = get_age_group_label(
                            record.get('event_name'), record.get('event_distance'), age_info, sex_info
                        ) if age_info else 'Неизвестно'

                    _start_list_cache = records
                    _start_list_cache_ts = time.time()
                    return records
                else:
                    logger.warning(f"⚠️ Таблица '{target_table}' пуста, возвращаем тестовые данные")
                    return get_test_data_fallback()

            except Error as e:
                logger.error(f"❌ Ошибка выполнения SQL запроса: {e}")
                return get_test_data_fallback()

            finally:
                cursor.close()

        finally:
            if connection.is_connected():
                connection.close()
                logger.info("📂 Соединение с БД закрыто")
    else:
        logger.error("❌ Не удалось установить соединение с БД, используем тестовые данные")
        return get_test_data_fallback()


def get_test_data_fallback() -> List[Dict[str, Any]]:
    """Тестовые данные для режима стартового списка (когда БД недоступна)."""
    return [
        {'surname': 'Иванов', 'name': 'Иван', 'sex': 'male', 'city': 'Красноярск', 'club': 'КМ',
         'birthday': '1985-03-15', 'category': 'мужчины до 49 лет', 'event_distance': '10 км',
         'event_name': 'Ночной забег', 'event_year': 2026},
        {'surname': 'Петрова', 'name': 'Мария', 'sex': 'female', 'city': 'Красноярск', 'club': 'Спорт',
         'birthday': '1990-07-22', 'category': 'женщины до 49 лет', 'event_distance': '5 км',
         'event_name': 'Ночной забег', 'event_year': 2026},
        {'surname': 'Сидоров', 'name': 'Алексей', 'sex': 'male', 'city': 'Красноярск', 'club': 'Бег',
         'birthday': '1975-11-30', 'category': 'мужчины 50-59 лет', 'event_distance': '21 км',
         'event_name': 'Ночной забег', 'event_year': 2026},
        {'surname': 'Морозов', 'name': 'Игорь', 'sex': 'male', 'city': 'Енисейск', 'club': 'Олимп',
         'birthday': '1988-09-12', 'category': 'мужчины до 49 лет', 'event_distance': '10 км',
         'event_name': 'Ночной забег', 'event_year': 2026},
        {'surname': 'Волкова', 'name': 'Светлана', 'sex': 'female', 'city': 'Красноярск', 'club': 'Марафон',
         'birthday': '1960-05-20', 'category': 'женщины 60-64 года', 'event_distance': '5 км',
         'event_name': 'Ночной забег', 'event_year': 2026},
        {'surname': 'Белов', 'name': 'Сергей', 'sex': 'male', 'city': 'Красноярск', 'club': 'Спорт',
         'birthday': '1970-12-03', 'category': 'мужчины 50-59 лет', 'event_distance': '21 км',
         'event_name': 'Ночной забег', 'event_year': 2026},
        {'surname': 'Лебедева', 'name': 'Виктория', 'sex': 'female', 'city': 'Ачинск', 'club': 'Бегуны',
         'birthday': '1985-06-18', 'category': 'женщины до 49 лет', 'event_distance': '10 км',
         'event_name': 'Ночной забег', 'event_year': 2026},
    ]


# ============================================================
# СТАРТОВЫЙ СПИСОК / LEADS API
# ============================================================

_startlist_cache: dict = {}
_startlist_cache_ts: dict = {}
STARTLIST_CACHE_TTL = 60  # секунд


def get_leads_by_event(event_id: int, include_duplicates: bool = True) -> List[Dict[str, Any]]:
    """Лиды по event_id. Кеш 60с. include_duplicates=False → AND is_duplicate=0."""
    key = (event_id, include_duplicates)
    now = time.time()
    if key in _startlist_cache and (now - _startlist_cache_ts.get(key, 0)) < STARTLIST_CACHE_TTL:
        return _startlist_cache[key]
    conn = get_pooled_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT * FROM leads WHERE event_id = %s"
        if not include_duplicates:
            sql += " AND is_duplicate = 0"
        sql += " ORDER BY surname ASC, name ASC"
        cur.execute(sql, (event_id,))
        rows = cur.fetchall()
        cur.close()
        result = []
        for row in rows:
            d = dict(row)
            d['category'] = get_age_group_label(d.get('event_name'), d.get('event_distance'), d.get('birthday'), d.get('sex'))
            result.append(d)
        _startlist_cache[key] = result
        _startlist_cache_ts[key] = time.time()
        return result
    except Exception as e:
        logger.error(f"get_leads_by_event error: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _leads_where(
    event_id=None, event_name=None, event_year=None, event_distance=None,
    is_duplicate=None, is_name_suspicious=None, search=None
):
    """Строит WHERE + params для leads-запросов."""
    conds: list = []
    params: list = []
    if event_id is not None:
        conds.append("event_id = %s"); params.append(event_id)
    if event_name is not None:
        conds.append("event_name = %s"); params.append(event_name)
    if event_year is not None:
        conds.append("event_year = %s"); params.append(event_year)
    if event_distance is not None:
        conds.append("event_distance = %s"); params.append(event_distance)
    if is_duplicate is not None:
        if is_duplicate:
            # Показываем ВСЕ записи людей с дублями — по триплету (surname, name, birthday)
            # в том же мероприятии/году
            sub_conds = ["is_duplicate = 1", "surname IS NOT NULL", "name IS NOT NULL", "birthday IS NOT NULL"]
            sub_params: list = []
            if event_name is not None:
                sub_conds.append("event_name = %s"); sub_params.append(event_name)
            if event_year is not None:
                sub_conds.append("event_year = %s"); sub_params.append(event_year)
            sub_where = "WHERE " + " AND ".join(sub_conds)
            conds.append(
                f"(surname, name, birthday) IN "
                f"(SELECT DISTINCT surname, name, birthday FROM leads {sub_where})"
            )
            params.extend(sub_params)
        else:
            conds.append("is_duplicate = %s"); params.append(0)
    if is_name_suspicious is not None:
        conds.append("is_name_suspicious = %s"); params.append(1 if is_name_suspicious else 0)
    if search:
        like = "%" + search.replace("%", "\\%").replace("_", "\\_") + "%"
        conds.append("(surname LIKE %s OR name LIKE %s OR email LIKE %s)")
        params.extend([like, like, like])
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def count_leads_admin(
    event_id=None, event_name=None, event_year=None, event_distance=None,
    is_duplicate=None, is_name_suspicious=None, search=None
) -> int:
    """SELECT COUNT(*) с теми же фильтрами что get_leads_admin."""
    conn = get_pooled_connection()
    if not conn:
        return 0
    try:
        where, params = _leads_where(
            event_id=event_id, event_name=event_name, event_year=event_year,
            event_distance=event_distance, is_duplicate=is_duplicate,
            is_name_suspicious=is_name_suspicious, search=search,
        )
        cur = conn.cursor(buffered=True)
        cur.execute(f"SELECT COUNT(*) FROM leads {where}", params)
        row = cur.fetchone()
        cur.close()
        return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"count_leads_admin error: {e}")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_leads_admin(
    event_id=None, event_name=None, event_year=None, event_distance=None,
    is_duplicate=None, is_name_suspicious=None,
    search=None, offset=0, limit=100
) -> List[Dict[str, Any]]:
    """Лиды с фильтрами для admin. Без кеша."""
    conn = get_pooled_connection()
    if not conn:
        return []
    try:
        where, params = _leads_where(
            event_id=event_id, event_name=event_name, event_year=event_year,
            event_distance=event_distance, is_duplicate=is_duplicate,
            is_name_suspicious=is_name_suspicious, search=search,
        )
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(
            f"SELECT * FROM leads {where} ORDER BY id DESC LIMIT %s OFFSET %s",
            params + [limit, offset],
        )
        rows = cur.fetchall()
        cur.close()
        result = []
        for row in rows:
            d = dict(row)
            d['category'] = get_age_group_label(d.get('event_name'), d.get('event_distance'), d.get('birthday'), d.get('sex'))
            result.append(d)
        return result
    except Exception as e:
        logger.error(f"get_leads_admin error: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_leads_filter_options(event_name: str = None, event_year: int = None) -> dict:
    """Distinct значения для каскадных фильтров (event_names, years, distances)."""
    conn = get_pooled_connection()
    if not conn:
        return {"event_names": [], "years": [], "distances": []}
    try:
        cur = conn.cursor(buffered=True)
        cur.execute(
            "SELECT DISTINCT event_name FROM leads "
            "WHERE event_name IS NOT NULL ORDER BY event_name"
        )
        event_names = [r[0] for r in cur.fetchall()]

        years: list = []
        if event_name:
            cur.execute(
                "SELECT DISTINCT event_year FROM leads "
                "WHERE event_name = %s AND event_year IS NOT NULL "
                "ORDER BY event_year DESC",
                (event_name,),
            )
            years = [r[0] for r in cur.fetchall()]

        distances: list = []
        if event_name:
            q = "SELECT DISTINCT event_distance FROM leads WHERE event_name = %s AND event_distance IS NOT NULL"
            p: list = [event_name]
            if event_year:
                q += " AND event_year = %s"
                p.append(event_year)
            q += " ORDER BY event_distance"
            cur.execute(q, p)
            distances = [r[0] for r in cur.fetchall()]

        cur.close()
        return {"event_names": event_names, "years": years, "distances": distances}
    except Exception as e:
        logger.error(f"get_leads_filter_options error: {e}")
        return {"event_names": [], "years": [], "distances": []}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def update_lead(lead_id: int, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Partial UPDATE leads по leads.id. Поля — только из whitelist."""
    ALLOWED = {'surname', 'name', 'event_distance', 'is_duplicate', 'status'}
    safe = {k: v for k, v in fields.items() if k in ALLOWED}
    if not safe:
        return None
    conn = get_pooled_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        if 'surname' in safe or 'name' in safe:
            # Правка ФИО вручную в админке должна пересчитывать
            # is_name_suspicious — иначе после исправления "Kazakov"->"Казаков"
            # флаг остаётся застрявшим на старом значении (реальная находка:
            # 1547 записей с чистым кириллическим ФИО, но is_name_suspicious=1,
            # т.к. этот путь никогда его не пересчитывал).
            cur.execute("SELECT surname, name FROM leads WHERE id = %s", (lead_id,))
            current = cur.fetchone()
            if current:
                new_surname = safe.get('surname', current['surname'])
                new_name = safe.get('name', current['name'])
                safe['is_name_suspicious'] = int(is_name_suspicious(new_surname, new_name))
        set_clause = ", ".join(f"{col} = %s" for col in safe)
        cur.execute(
            f"UPDATE leads SET {set_clause} WHERE id = %s",
            list(safe.values()) + [lead_id],
        )
        conn.commit()
        cur.execute("SELECT * FROM leads WHERE id = %s", (lead_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        d = dict(row)
        d['category'] = get_age_group_label(d.get('event_name'), d.get('event_distance'), d.get('birthday'), d.get('sex'))
        return d
    except Exception as e:
        logger.error(f"update_lead error: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def recompute_duplicate_flag(client_id: int, event_id: int) -> int:
    """Пересчитать is_duplicate для ВСЕХ строк группы (client_id, event_id):
    1, если в группе >1 строки, иначе 0 — включая первую заявку, не только
    повторные (trg_leads_before_insert делает `SET NEW.is_duplicate = 0;`
    безусловно на каждой вставке — мёртвый код, is_duplicate никогда не
    считался автоматически). Вызывается из webhook._insert_lead после
    INSERT и из bulk-импорта Tilda-заявок.

    Один атомарный UPDATE с производной таблицей (MySQL не разрешает
    `UPDATE leads SET ... WHERE ... IN (SELECT ... FROM leads)` напрямую по
    той же таблице — оборачиваем в derived table), устраняет гонку между
    параллельными вызовами вместо read-then-write.
    """
    if not client_id or not event_id:
        return 0
    conn = get_pooled_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE leads
            SET is_duplicate = (
                SELECT cnt > 1 FROM (
                    SELECT COUNT(*) AS cnt FROM leads
                    WHERE client_id = %s AND event_id = %s
                ) t
            )
            WHERE client_id = %s AND event_id = %s
            """,
            (client_id, event_id, client_id, event_id),
        )
        conn.commit()
        updated = cur.rowcount
        cur.close()
        return updated
    except Exception as e:
        logger.error(f"recompute_duplicate_flag error (client_id={client_id}, event_id={event_id}): {e}")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


_IMPORT_UPDATABLE = ('surname', 'name', 'sex', 'city', 'club', 'email', 'phone', 'event_distance', 'is_name_suspicious')


def _find_lead_matches(cur, row) -> list:
    """Список совпавших leads (dict-строк, курсор должен быть
    dictionary=True) для row — двухуровневый поиск, общий для
    bulk_import_leads()/preview_leads_import_matches():
    1. По order_id (переживает правку фамилии/имени в CRM Tilda задним
       числом) — order_id=0/NULL исключён, это заглушка Tilda для
       бесплатных/незавершённых заявок, а не настоящий номер заказа.
    2. Фоллбэк — surname+name+birthday+event_name+event_year+event_distance
       (для заявок без order_id: бесплатные события, старые данные)."""
    order_id_raw = (row.order_id or '').strip()
    row_order_id = int(order_id_raw) if order_id_raw.isdigit() and order_id_raw != '0' else None

    if row_order_id:
        cur.execute(
            "SELECT id FROM leads WHERE order_id=%s "
            "AND event_name=%s AND event_year=%s AND event_distance=%s",
            (row_order_id, row.event_name, row.event_year, row.event_distance),
        )
        matches = cur.fetchall()
        if matches:
            return matches

    # birthday NOT NULL в схеме, '' невалиден как DATE для MySQL (ошибка 1525
    # "Incorrect DATE value") — тот же сентинел '1900-01-01', что и при INSERT
    # в bulk_import_leads(), иначе сравнение в WHERE падает при пустой дате
    # (дата рождения необязательна при импорте с 2026-08-18).
    row_birthday = row.birthday or '1900-01-01'
    cur.execute(
        "SELECT id FROM leads WHERE surname=%s AND name=%s AND birthday=%s "
        "AND event_name=%s AND event_year=%s AND event_distance=%s",
        (row.surname, row.name, row_birthday, row.event_name, row.event_year, row.event_distance),
    )
    return cur.fetchall()


def bulk_import_leads(rows: list) -> Dict[str, Any]:
    """Сопоставляет rows (list[ImportRow] из tilda_import_parser) с leads.

    Сопоставление — см. _find_lead_matches() (двухуровневое: order_id, затем
    фоллбэк на surname+name+birthday+событие). Без order_id-поиска:
    организатор правит "Kazakov Oleg" на "Казаков Олег" в Tilda,
    переимпортирует — поиск по (уже устаревшим) фамилии/имени не находит
    старую строку, создаётся дубль вместо исправления существующей записи
    (реальный инцидент, Жара 2026, 2026-08-17).

    Совпавшие строки — UPDATE (ВСЕ строки группы, если их несколько — если
    группа уже была дублем, обе строки должны отразить правку организатора).
    Несовпавшие — INSERT новой заявки (trg_leads_before_insert сам резолвит
    client_id/event_id — не переизобретаем это в Python), затем
    recompute_duplicate_flag() на случай пересечения с уже живой группой.

    birthday намеренно не в whitelist апдейта — смена даты рождения = смена
    личности (для этого есть обычный admin PATCH по одной строке).
    client_id/event_id/платёжные поля тоже не трогаются — не про правки
    ФИО/контактов."""
    conn = get_pooled_connection()
    if not conn:
        return {"updated": 0, "created": 0, "errors": ["Нет соединения с БД"]}
    updated = created = 0
    errors: list = []
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        for row in rows:
            matches = _find_lead_matches(cur, row)

            if matches:
                values = {c: (getattr(row, c) or None) for c in _IMPORT_UPDATABLE}
                values['event_distance'] = row.event_distance  # не-NULL поле
                # is_name_suspicious — bool/int, а не текстовое поле: "or None"
                # выше превратил бы False/0 в NULL, хотя False — валидное
                # значение (имя чистое), а не "данных нет".
                values['is_name_suspicious'] = int(row.is_name_suspicious)
                set_clause = ", ".join(f"{c} = %s" for c in _IMPORT_UPDATABLE)
                # start_number — намеренно ВНЕ _IMPORT_UPDATABLE/блока "or None"
                # выше: та логика на пустом значении из файла тихо стирает
                # существующее значение в БД (годится для club/phone и т.п. —
                # "этот импорт теперь источник истины", но не для номера,
                # который может быть проставлен только в одном из нескольких
                # файлов, гуляющих между организатором/оператором). Обновляем
                # только когда в ЭТОЙ строке номер реально есть.
                start_number = int(row.start_number) if row.start_number.strip().isdigit() else None
                for m in matches:
                    cur.execute(
                        f"UPDATE leads SET {set_clause} WHERE id = %s",
                        [values[c] for c in _IMPORT_UPDATABLE] + [m['id']],
                    )
                    if start_number is not None:
                        cur.execute(
                            "UPDATE leads SET start_number = %s WHERE id = %s",
                            [start_number, m['id']],
                        )
                    updated += 1
            else:
                def _float_or_zero(v):
                    try:
                        return float(v) if v else 0.0
                    except (TypeError, ValueError):
                        return 0.0

                order_id_raw = (row.order_id or '').strip()
                cur.execute(
                    """
                    INSERT INTO leads (
                        surname, name, sex, city, club, birthday, email, phone,
                        event_name, event_distance, event_year, products,
                        amount, promocode, discount, order_id, transaction_id, payment_system,
                        is_name_suspicious, start_number, client_id, event_id, is_duplicate,
                        status, is_new, is_new_event
                    ) VALUES (
                        %(surname)s, %(name)s, %(sex)s, %(city)s, %(club)s, %(birthday)s,
                        %(email)s, %(phone)s, %(event_name)s, %(event_distance)s,
                        %(event_year)s, '',
                        %(amount)s, %(promocode)s, %(discount)s, %(order_id)s, %(transaction_id)s, %(payment_system)s,
                        %(is_name_suspicious)s, %(start_number)s, 0, 0, 0, 0, 0, 0
                    )
                    """,
                    {
                        'surname': row.surname, 'name': row.name, 'sex': row.sex or '',
                        'city': row.city or '', 'club': row.club or '',
                        # birthday NOT NULL в схеме — '1900-01-01' тот же сентинел
                        # "дата неизвестна", что уже подразумевает DEFAULT колонки;
                        # задаём явно, а не полагаемся на DEFAULT (сработал бы,
                        # только если колонку вообще не передавать в INSERT).
                        'birthday': row.birthday or '1900-01-01',
                        'email': row.email or 'example@mail.ru', 'phone': row.phone or None,
                        'event_name': row.event_name, 'event_distance': row.event_distance,
                        'event_year': row.event_year,
                        'amount': _float_or_zero(row.amount),
                        'promocode': row.promocode or '',
                        'discount': _float_or_zero(row.discount),
                        'order_id': int(order_id_raw) if order_id_raw.isdigit() else None,
                        'transaction_id': row.transaction_id or '',
                        'payment_system': row.payment_system or '',
                        'is_name_suspicious': int(row.is_name_suspicious),
                        'start_number': int(row.start_number) if row.start_number.strip().isdigit() else None,
                    },
                )
                new_id = cur.lastrowid
                cur.execute("SELECT client_id, event_id FROM leads WHERE id = %s", (new_id,))
                new_row = cur.fetchone()
                if new_row:
                    recompute_duplicate_flag(client_id=new_row['client_id'], event_id=new_row['event_id'])
                created += 1
        conn.commit()
        cur.close()
        return {"updated": updated, "created": created, "errors": errors}
    except Exception as e:
        logger.error(f"bulk_import_leads error: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return {"updated": updated, "created": created, "errors": [str(e)]}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def preview_leads_import_matches(rows: list) -> list:
    """Только чтение — для каждой row возвращает matched_count (0 = будет
    создана новая заявка при bulk_import_leads), используется для превью
    перед подтверждением импорта в admin UI."""
    conn = get_pooled_connection()
    if not conn:
        return [
            {"row_number": r.row_number, "surname": r.surname, "name": r.name,
             "birthday": r.birthday, "event_name": r.event_name, "event_distance": r.event_distance,
             "matched_count": 0, "will": "unknown"}
            for r in rows
        ]
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        out = []
        for row in rows:
            cnt = len(_find_lead_matches(cur, row))
            out.append({
                "row_number": row.row_number, "surname": row.surname, "name": row.name,
                "birthday": row.birthday, "event_name": row.event_name, "event_distance": row.event_distance,
                "matched_count": cnt, "will": "update" if cnt >= 1 else "create",
            })
        cur.close()
        return out
    finally:
        try:
            conn.close()
        except Exception:
            pass


def create_connection():
    """УСТАРЕВШАЯ функция — используйте get_pooled_connection()."""
    logger.warning("⚠️ create_connection() устаревшая, используйте get_pooled_connection()")
    return get_pooled_connection()


def list_db_events() -> List[Dict[str, Any]]:
    """Список событий из таблицы events (числовой id + человекочитаемые
    поля) — для выбора конкретного event_id в админке (напр. вкладка «Фото
    участников»), где нужен именно ID, а не event_name/event_distance
    строки, как в age_group_configs."""
    conn = get_pooled_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(
            "SELECT id, event_name, event_distance, event_year FROM events "
            "ORDER BY event_year DESC, event_name, event_distance"
        )
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"list_db_events error: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def list_participant_photos(event_id: int) -> List[Dict[str, Any]]:
    conn = get_pooled_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(
            "SELECT * FROM participant_photos WHERE event_id = %s ORDER BY start_number",
            (event_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"list_participant_photos error: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def upsert_participant_photo(event_id: int, start_number: int, photo_url: str) -> Optional[Dict[str, Any]]:
    """INSERT ... ON DUPLICATE KEY UPDATE — форма в /admin всегда просто
    "сохраняет", не важно, новая это запись или правка существующей."""
    conn = get_pooled_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(
            "INSERT INTO participant_photos (event_id, start_number, photo_url) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE photo_url = VALUES(photo_url)",
            (event_id, start_number, photo_url),
        )
        conn.commit()
        cur.execute(
            "SELECT * FROM participant_photos WHERE event_id = %s AND start_number = %s",
            (event_id, start_number),
        )
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"upsert_participant_photo error: {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def delete_participant_photo(photo_id: int) -> bool:
    conn = get_pooled_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor(buffered=True)
        cur.execute("DELETE FROM participant_photos WHERE id = %s", (photo_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        cur.close()
        return deleted
    except Exception as e:
        logger.error(f"delete_participant_photo error: {e}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass
