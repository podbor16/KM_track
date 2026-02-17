"""
Модели данных для участников гонки (Pydantic)
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Position(BaseModel):
    """Географическая позиция"""
    lat: float = Field(..., description="Широта")
    lng: float = Field(..., description="Долгота")


class Timing(BaseModel):
    """Временные метки для контрольной точки"""
    treal: Optional[str] = Field(None, description="Реальное время")
    tofficial: Optional[str] = Field(None, description="Официальное время")
    avg: Optional[str] = Field(None, description="Средний темп (мин/км)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "treal": "08:00:00",
                "tofficial": "08:00:00",
                "avg": "7'22\"/km"
            }
        }


class Runner(BaseModel):
    """Модель участника гонки"""
    
    # Идентификация
    id: str = Field(..., description="Уникальный ID участника")
    bib: int = Field(..., description="Номер на нагрудной повязке")
    dorsal: int = Field(..., description="Номер дорсального номера")
    
    # ФИО и категория
    name: str = Field(..., description="Имя")
    surname: str = Field(..., description="Фамилия")
    full_name: str = Field(..., description="Полное имя")
    category: str = Field(..., description="Возрастная категория")
    gender: str = Field(..., description="Пол (Male/Female/Unknown)")
    
    # Статус и позиция
    status: str = Field(..., description="Статус (notstarted/running/finished)")
    current_distance: float = Field(..., description="Текущая пройденная дистанция (км)")
    position: Position = Field(..., description="Текущая географическая позиция")
    speed: float = Field(..., description="Текущая скорость (км/ч)")
    pace: float = Field(..., description="Текущий темп (мин/км)")
    
    # Временные метки
    start: Timing = Field(..., description="Старт")
    kt2: Timing = Field(..., description="Контрольная точка 2")
    finish: Optional[Timing] = Field(None, description="Финиш")
    
    # Метаданные
    last_update: str = Field(..., description="Время последнего обновления")
    source_data: Optional[dict] = Field(None, description="Оригинальные данные из API")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "123",
                "bib": 123,
                "dorsal": 123,
                "name": "Иван",
                "surname": "Иванов",
                "full_name": "Иван Иванов",
                "category": "M40",
                "gender": "Male",
                "status": "running",
                "current_distance": 3.5,
                "position": {"lat": 56.028855, "lng": 92.946101},
                "speed": 12.5,
                "pace": 4.8,
                "start": {"treal": "08:00:00", "tofficial": "08:00:00"},
                "kt2": {"treal": "08:08:45", "tofficial": "08:08:45", "avg": "7'12\"/km"},
                "finish": None,
                "last_update": "2026-02-16T12:30:45.123456"
            }
        }


class RunnerMinimal(BaseModel):
    """Минимальная модель участника (для списков)"""
    id: str
    full_name: str
    bib: int
    status: str
    current_distance: float
    position: Position


class RunnersListResponse(BaseModel):
    """Ответ со списком участников"""
    event: str = Field(..., description="ID события")
    total: int = Field(..., description="Всего участников")
    running: int = Field(..., description="Бегут сейчас")
    finished: int = Field(..., description="Финишировали")
    not_started: int = Field(..., description="Не стартовали")
    runners: list[Runner] = Field(..., description="Список участников")
    last_update: str = Field(..., description="Время обновления")


class RunnerSelectionRequest(BaseModel):
    """Запрос на выбор/отмену выбора участника"""
    runner_id: str = Field(..., description="ID участника")


class SelectedRunnersResponse(BaseModel):
    """Ответ со списком выбранных участников"""
    event: str = Field(..., description="ID события")
    selected_ids: list[str] = Field(..., description="IDs выбранных участников")
    count: int = Field(..., description="Количество выбранных")
