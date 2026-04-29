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

logger = logging.getLogger(__name__)


# ============================================================
# ПОЛУЧЕНИЕ РЕЗУЛЬТАТОВ ПО EVENT_ID
# ============================================================

_results_cache: dict = {}
_results_cache_ts: dict = {}
RESULTS_CACHE_TTL = 5  # секунд — короткий TTL для live-данных КТ

# Кеш данных события (gun_time и т.д.) — с TTL, чтобы изменения в events отражались быстро
_event_info_cache: dict = {}
_event_info_cache_ts: dict = {}
EVENT_INFO_CACHE_TTL = 5  # секунд
_prev_year_cache: dict = {}    # get_prev_year_results — финиши прошлого года


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

    Returns:
        Dict {category_str: avg_speed_kmh}
    """

    def _pace_to_kmh(pace_str: str) -> float:
        try:
            parts = pace_str.strip().split(':')
            minutes = int(parts[0])
            seconds = int(parts[1]) if len(parts) > 1 else 0
            total_secs = minutes * 60 + seconds
            return 3600.0 / total_secs if total_secs > 0 else 0.0
        except Exception:
            return 0.0

    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ get_category_avg_paces: нет соединения")
        return {}

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)

        cursor.execute(
            """
            SELECT r.category, r.finish_pace_avg
            FROM results r
            INNER JOIN events e ON r.event_id = e.id
            WHERE e.event_name = %s
              AND e.event_year = %s
              AND e.event_distance = %s
              AND r.race_status = 'Finished'
              AND r.finish_pace_avg IS NOT NULL
              AND r.finish_pace_avg != ''
              AND r.category IS NOT NULL
              AND r.category != ''
            """,
            (event_name, year, str(event_distance)),
        )
        rows = cursor.fetchall()

        if not rows:
            cursor.execute(
                """
                SELECT r.category, r.finish_pace_avg
                FROM results r
                INNER JOIN events e ON r.event_id = e.id
                WHERE e.event_name = %s
                  AND e.event_year = %s
                  AND r.race_status = 'Finished'
                  AND r.finish_pace_avg IS NOT NULL
                  AND r.finish_pace_avg != ''
                  AND r.category IS NOT NULL
                  AND r.category != ''
                """,
                (event_name, year),
            )
            rows = cursor.fetchall()

        cursor.close()

        if not rows:
            logger.warning(f"⚠️ get_category_avg_paces: нет финишировавших для {event_name} {year} дист={event_distance}")
            return {}

        from collections import defaultdict
        speeds_by_cat: Dict[str, list] = defaultdict(list)
        for row in rows:
            cat = (row.get("category") or "").strip()
            pace_str = (row.get("finish_pace_avg") or "").strip()
            if cat and pace_str:
                kmh = _pace_to_kmh(pace_str)
                if kmh > 0:
                    speeds_by_cat[cat].append(kmh)

        result = {cat: sum(speeds) / len(speeds) for cat, speeds in speeds_by_cat.items()}
        logger.info(f"✅ get_category_avg_paces: {len(result)} категорий для {event_name} {year}")
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
        return {
            'race_name': event_name,
            'distances': distances_out,
        }

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
        return list(segments) if segments else []

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

def calculate_age_group(birthdate_or_age, sex: str = None) -> str:
    """
    Возрастная группа по дате рождения/возрасту и полу.

    Returns:
        Строка с названием возрастной группы.
    """
    if not birthdate_or_age:
        return 'Неизвестно'

    try:
        age = None

        if isinstance(birthdate_or_age, (datetime.date, datetime.datetime)):
            age = datetime.datetime.now().year - birthdate_or_age.year
        elif isinstance(birthdate_or_age, str):
            try:
                birth_date = datetime.datetime.strptime(birthdate_or_age[:10], '%Y-%m-%d')
                age = datetime.datetime.now().year - birth_date.year
            except Exception:
                try:
                    age = int(birthdate_or_age)
                except Exception:
                    return 'Неизвестно'
        elif isinstance(birthdate_or_age, int):
            age = birthdate_or_age

        if age is None:
            return 'Неизвестно'

        is_male = True
        if sex:
            sex_lower = str(sex).lower().strip()
            if sex_lower in ['female', 'ж', 'женщина', 'women', 'f']:
                is_male = False

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
                        record['category'] = calculate_age_group(age_info, sex=sex_info) if age_info else 'Неизвестно'

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


def create_connection():
    """УСТАРЕВШАЯ функция — используйте get_pooled_connection()."""
    logger.warning("⚠️ create_connection() устаревшая, используйте get_pooled_connection()")
    return get_pooled_connection()
