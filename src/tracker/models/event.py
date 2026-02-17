"""
Модели данных для событий (Pydantic)
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class EventInfo(BaseModel):
    """Информация о мероприятии"""
    
    id: str = Field(..., description="Уникальный ID события")
    name: str = Field(..., description="Название события")
    title: str = Field(..., description="Заголовок события")
    description: str = Field(..., description="Описание события")
    
    osm_way_id: int = Field(..., description="OpenStreetMap Way ID маршрута")
    route_type: str = Field(..., description="Тип маршрута (shuttle/loop)")
    
    total_distance: float = Field(..., description="Полная дистанция в км")
    one_way_length: Optional[float] = Field(None, description="Длина одного плеча (для челночных)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "night_run",
                "name": "Ночной забег",
                "title": "Ночной забег. Трекер",
                "description": "Набережная, Красноярск | Дистанции: 5 км",
                "osm_way_id": 1477580211,
                "route_type": "shuttle",
                "total_distance": 5.0,
                "one_way_length": 2.5
            }
        }


class CurrentEventResponse(BaseModel):
    """Ответ с текущим событием"""
    
    event: str = Field(..., description="ID текущего события")
    storage_key: str = Field(..., description="Ключ localStorage для сохранения выбора")
    name: str = Field(..., description="Название события")
    title: str = Field(..., description="Заголовок события")
    description: str = Field(..., description="Описание события")
    route_type: str = Field(..., description="Тип маршрута (shuttle/loop)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "event": "night_run",
                "storage_key": "night_run_selected_runners",
                "name": "Ночной забег",
                "title": "Ночной забег. Трекер",
                "description": "Набережная, Красноярск",
                "route_type": "shuttle"
            }
        }


class EventsListResponse(BaseModel):
    """Ответ со списком всех событий"""
    
    events: List[Dict[str, Any]] = Field(..., description="Список событий")
    current: str = Field(..., description="ID текущего события")
    
    class Config:
        json_schema_extra = {
            "example": {
                "events": [
                    {"id": "snow7", "name": "Снежная семерка", "way_id": 181589417},
                    {"id": "rosneft", "name": "Роснефть", "way_id": 553966988},
                    {"id": "night_run", "name": "Ночной забег", "way_id": 1477580211}
                ],
                "current": "night_run"
            }
        }
