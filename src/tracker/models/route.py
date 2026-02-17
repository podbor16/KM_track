"""
Модели данных для маршрутов (Pydantic)
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class RouteCoordinates(BaseModel):
    """Координаты маршрута"""
    coordinates: List[List[float]] = Field(..., description="Список [lat, lon] координат")
    distance: float = Field(..., description="Полная дистанция маршрута в км")


class Route(BaseModel):
    """Модель маршрута события"""
    
    coordinates: List[List[float]] = Field(..., description="Координаты маршрута [[lat,lon], ...]")
    distance: float = Field(..., description="Полная дистанция в км")
    way_id: int = Field(..., description="OpenStreetMap Way ID")
    event: str = Field(..., description="ID события")
    event_name: str = Field(..., description="Название события")
    route_type: str = Field(..., description="Тип маршрута (shuttle/loop)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "coordinates": [[56.028855, 92.946101], [56.02996, 92.949893]],
                "distance": 7.0,
                "way_id": 1477580211,
                "event": "night_run",
                "event_name": "Ночной забег",
                "route_type": "shuttle"
            }
        }


class RouteCache(BaseModel):
    """Кэшированные данные маршрута"""
    coordinates: List[List[float]]
    distance: float
    way_id: int
    timestamp: float


class Checkpoint(BaseModel):
    """Контрольная точка на маршруте"""
    id: str = Field(..., description="Уникальный ID точки")
    distance: float = Field(..., description="Дистанция от старта в км")
    name: str = Field(..., description="Название контрольной точки")
    coordinates: Optional[List[float]] = Field(None, description="[lat, lon]")


class RaceConfig(BaseModel):
    """Конфигурация забега"""
    
    total_distance: float = Field(..., description="Полная дистанция забега в км")
    event_name: str = Field(..., description="Название события")
    event_id: str = Field(..., description="ID события")
    route_type: str = Field(..., description="Тип маршрута (shuttle/loop)")
    
    # Для челночных маршрутов
    one_way_length: Optional[float] = Field(None, description="Длина одного плеча в км")
    laps: Optional[int] = Field(None, description="Количество плеч/кругов")
    
    # Для кольцевых маршрутов
    lap_length: Optional[float] = Field(None, description="Длина одного круга в км")
    
    checkpoints: List[Checkpoint] = Field(default_factory=list, description="Контрольные точки")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_distance": 7.0,
                "event_name": "Снежная семерка",
                "event_id": "snow7",
                "route_type": "shuttle",
                "one_way_length": 1.75,
                "laps": 4,
                "checkpoints": [
                    {"id": "start", "distance": 0.0, "name": "Старт"},
                    {"id": "turn", "distance": 1.75, "name": "Разворот"},
                    {"id": "finish", "distance": 7.0, "name": "Финиш"}
                ]
            }
        }


class RouteResponse(BaseModel):
    """Ответ с информацией о маршруте"""
    success: bool = Field(..., description="Успешно ли загружен маршрут")
    route: Optional[Route] = Field(None, description="Данные маршрута")
    config: Optional[RaceConfig] = Field(None, description="Конфигурация забега")
    cached: bool = Field(..., description="Получено из кеша")
    message: Optional[str] = Field(None, description="Сообщение об ошибке")
