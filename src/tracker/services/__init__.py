"""Сервисы приложения"""

from .routes_service import (
    fetch_route_from_osm,
    get_route_calculator,
    load_route_from_json,
    process_osm_route_data,
)

from .runners_service import (
    fetch_copernico_data,
    transform_copernico_data,
    update_runner_positions,
    parse_pace_to_speed,
)

from .analytics_service import (
    get_formatted_analytics,
)

from .pace_calculator import (
    parse_distance,
    parse_pace_to_kmh,
    kmh_to_pace,
    get_initial_pace,
    get_runner_average_pace,
    get_category_average_pace,
)

__all__ = [
    # routes
    "fetch_route_from_osm",
    "get_route_calculator",
    "load_route_from_json",
    "process_osm_route_data",
    
    # runners
    "fetch_copernico_data",
    "transform_copernico_data",
    "update_runner_positions",
    "parse_pace_to_speed",
    
    # analytics
    "get_formatted_analytics",
    
    # pace_calculator
    "parse_distance",
    "parse_pace_to_kmh",
    "kmh_to_pace",
    "get_initial_pace",
    "get_runner_average_pace",
    "get_category_average_pace",
]
