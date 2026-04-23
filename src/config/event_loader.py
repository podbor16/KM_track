"""
Загрузчик конфигураций мероприятий из YAML-файлов.
Единственная точка правды для всех настроек событий.
"""

import threading
import time
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


class CopernicoConfig(BaseModel):
    race_id: Optional[str] = None
    login: str
    preset: str
    event: str


class RouteConfig(BaseModel):
    laps: int = 1
    one_way_length_km: Optional[float] = None
    total_km: Optional[float] = None


class CheckpointCoord(BaseModel):
    name: str
    distance_km: float
    lat: float
    lon: float


class DistanceConfig(BaseModel):
    distance: str                        # "5 км"
    distance_km: float
    db_event_id: Optional[int] = None
    tracked: bool = False
    has_start_list: bool = False
    checkpoint_distances: list[float] = []
    checkpoints: list[CheckpointCoord] = []
    gpx_file: Optional[str] = None
    event_date: Optional[str] = None
    route: RouteConfig = RouteConfig()
    copernico: Optional[CopernicoConfig] = None


class EventConfig(BaseModel):
    code: str                            # ключ — совпадает с именем YAML-файла
    name: str                            # ТОЧНО как event_name в БД
    display_name: str
    year: int
    is_active: bool = False
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    gun_time: Optional[str] = None       # "21:00:00"
    description: str = ""
    distances: list[DistanceConfig] = []

    @property
    def title(self) -> str:
        return f"{self.display_name} | Трекер"

    def get_distance(self, d: str) -> Optional[DistanceConfig]:
        """Найти дистанцию по строке, например '5 км'."""
        return next((x for x in self.distances if x.distance == d), None)

    def get_tracked(self) -> Optional[DistanceConfig]:
        """Первая отслеживаемая дистанция (tracked=true)."""
        return next((x for x in self.distances if x.tracked), None)

    def get_by_db_id(self, db_id: int) -> Optional[DistanceConfig]:
        """Найти дистанцию по db_event_id."""
        return next((x for x in self.distances if x.db_event_id == db_id), None)


def load_all_events(config_dir: Path) -> dict[str, "EventConfig"]:
    """Загружает все YAML из config/events/, ключ = поле code внутри файла.

    Вызывается один раз при старте приложения.
    """
    if not _YAML_AVAILABLE:
        raise ImportError("PyYAML не установлен. Выполните: pip install pyyaml")

    events: dict[str, EventConfig] = {}
    config_dir = Path(config_dir)

    for path in sorted(config_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
            # code по умолчанию = имя файла без расширения
            raw.setdefault("code", path.stem)
            cfg = EventConfig(**raw)
            events[cfg.code] = cfg
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Не удалось загрузить %s: %s", path.name, exc
            )

    return events


def get_event_by_db_id(
    events: dict[str, "EventConfig"], db_id: int
) -> tuple[Optional["EventConfig"], Optional["DistanceConfig"]]:
    """Найти (EventConfig, DistanceConfig) по db_event_id дистанции."""
    for event in events.values():
        dist = event.get_by_db_id(db_id)
        if dist is not None:
            return event, dist
    return None, None


def get_active_event(
    events: dict[str, "EventConfig"],
) -> Optional["EventConfig"]:
    """Найти единственное активное событие (is_active=true в YAML)."""
    return next((e for e in events.values() if e.is_active), None)


def get_event_by_name(
    events: dict[str, "EventConfig"], name: str
) -> Optional["EventConfig"]:
    """Найти EventConfig по точному имени события (как в БД)."""
    return next((e for e in events.values() if e.name == name), None)


# ---------------------------------------------------------------------------
# TTL-кеш для горячей перезагрузки YAML без перезапуска сервера
# ---------------------------------------------------------------------------

_DEFAULT_EVENTS_DIR = Path(__file__).parent.parent.parent / "config" / "events"

_cache_lock = threading.Lock()
_cached_events: Optional[dict] = None
_cache_timestamp: float = 0.0
EVENTS_CACHE_TTL = 30.0  # секунды


def load_events_cached(config_dir: Path = _DEFAULT_EVENTS_DIR) -> dict[str, "EventConfig"]:
    """Загружает конфиги с TTL-кешем. YAML перечитывается не чаще раза в EVENTS_CACHE_TTL секунд."""
    global _cached_events, _cache_timestamp
    now = time.monotonic()
    with _cache_lock:
        if _cached_events is None or (now - _cache_timestamp) > EVENTS_CACHE_TTL:
            _cached_events = load_all_events(config_dir)
            _cache_timestamp = now
        return _cached_events


def invalidate_events_cache() -> None:
    """Сбрасывает кеш — следующий вызов load_events_cached() перечитает YAML."""
    global _cached_events, _cache_timestamp
    with _cache_lock:
        _cached_events = None
        _cache_timestamp = 0.0
