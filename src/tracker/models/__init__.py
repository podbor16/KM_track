"""Pydantic модели для трекера"""

from .runner import (
    Runner,
    RunnerMinimal,
    RunnersListResponse,
    RunnerSelectionRequest,
    SelectedRunnersResponse,
    Position,
    Timing,
)

from .route import (
    Route,
    RouteCoordinates,
    RouteCache,
    Checkpoint,
    RaceConfig,
    RouteResponse,
)

from .event import (
    EventInfo,
    CurrentEventResponse,
    EventsListResponse,
)

from .analytics import (
    Analytics,
    GeneralStats,
    GenderStats,
    TopFinishers,
    AnalyticsResponse,
    RegisteredRunnerInfo,
    RegisteredRunnersListResponse,
    RaceResultsResponse,
)

__all__ = [
    # Runner models
    "Runner",
    "RunnerMinimal",
    "RunnersListResponse",
    "RunnerSelectionRequest",
    "SelectedRunnersResponse",
    "Position",
    "Timing",
    
    # Route models
    "Route",
    "RouteCoordinates",
    "RouteCache",
    "Checkpoint",
    "RaceConfig",
    "RouteResponse",
    
    # Event models
    "EventInfo",
    "CurrentEventResponse",
    "EventsListResponse",
    
    # Analytics models
    "Analytics",
    "GeneralStats",
    "GenderStats",
    "TopFinishers",
    "AnalyticsResponse",
    "RegisteredRunnerInfo",
    "RegisteredRunnersListResponse",
    "RaceResultsResponse",
]
