"""
Шим обратной совместимости — импортируйте из db_pool, db_athletes, db_results напрямую.
Весь код перенесён в:
  - db_pool.py    — пул соединений и кэш таблиц
  - db_athletes.py — поиск и профиль спортсменов
  - db_results.py  — результаты, статистика, сегменты
"""

from .db_pool import (
    initialize_connection_pool,
    get_pooled_connection,
    get_cached_tables,
    find_table,
    get_table_row_count_fast,
    get_table_columns,
)

from .db_athletes import (
    search_clients_optimized,
    get_athlete_results_optimized,
    get_athlete_results,
    search_clients,
)

from .db_results import (
    RESULTS_CACHE_TTL,
    _results_cache,
    _results_cache_ts,
    get_race_results_by_event_id,
    get_race_results_by_event_id_and_year,
    get_checkpoint_distances,
    get_category_avg_paces,
    get_event_info,
    get_event_info_by_id,
    get_prev_year_results,
    get_race_stats_from_db,
    get_result_segments,
    find_result_by_client_id,
    get_database_info_optimized,
    calculate_age_group,
    get_test_table_data,
    get_test_data_fallback,
    create_connection,
)

__all__ = [
    # db_pool
    "initialize_connection_pool",
    "get_pooled_connection",
    "get_cached_tables",
    "find_table",
    "get_table_row_count_fast",
    "get_table_columns",
    "get_table_row_count_fast",
    # db_athletes
    "search_clients_optimized",
    "get_athlete_results_optimized",
    "get_athlete_results",
    "search_clients",
    # db_results
    "RESULTS_CACHE_TTL",
    "_results_cache",
    "_results_cache_ts",
    "get_race_results_by_event_id",
    "get_race_results_by_event_id_and_year",
    "get_checkpoint_distances",
    "get_category_avg_paces",
    "get_event_info",
    "get_event_info_by_id",
    "get_prev_year_results",
    "get_race_stats_from_db",
    "get_result_segments",
    "find_result_by_client_id",
    "get_database_info_optimized",
    "calculate_age_group",
    "get_test_table_data",
    "get_test_data_fallback",
    "create_connection",
]
