"""Сервисы приложения"""

from .routes_service import (
    load_route_from_gpx,
    get_route_calculator,
    RouteCalculator,
)

from .runners_service import (
    calculate_live_position,
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
    "load_route_from_gpx",
    "get_route_calculator",
    "RouteCalculator",

    # runners
    "calculate_live_position",
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
