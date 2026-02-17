"""
Модели данных для аналитики (Pydantic)
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class GeneralStats(BaseModel):
    """Общая статистика по гонке"""
    
    total_runners: int = Field(..., description="Всего участников")
    not_started: int = Field(..., description="Не стартовали")
    on_track: int = Field(..., description="На дистанции")
    finished: int = Field(..., description="Финишировали")


class GenderStats(BaseModel):
    """Статистика по полам"""
    
    male_count: int = Field(..., description="Мужчин")
    female_count: int = Field(..., description="Женщин")
    male_avg_time: str = Field(..., description="Среднее время для мужчин")
    female_avg_time: str = Field(..., description="Среднее время для женщин")


class TopFinishers(BaseModel):
    """Топ финишёров"""
    
    overall: List[Dict[str, Any]] = Field(..., description="Топ в целом")
    male: List[Dict[str, Any]] = Field(..., description="Топ мужчин")
    female: List[Dict[str, Any]] = Field(..., description="Топ женщин")


class Analytics(BaseModel):
    """Полная аналитика гонки"""
    
    event: str = Field(..., description="ID события")
    timestamp: str = Field(..., description="Время расчёта")
    
    general_stats: GeneralStats = Field(..., description="Общая статистика")
    gender_stats: GenderStats = Field(..., description="Статистика по полам")
    top_finishers: TopFinishers = Field(..., description="Топ финишёров")
    
    class Config:
        json_schema_extra = {
            "example": {
                "event": "night_run",
                "timestamp": "2026-02-16T12:30:45",
                "general_stats": {
                    "total_runners": 150,
                    "not_started": 20,
                    "on_track": 50,
                    "finished": 80
                },
                "gender_stats": {
                    "male_count": 90,
                    "female_count": 60,
                    "male_avg_time": "00:45:30.000",
                    "female_avg_time": "00:52:15.000"
                },
                "top_finishers": {
                    "overall": [],
                    "male": [],
                    "female": []
                }
            }
        }


class AnalyticsResponse(BaseModel):
    """Ответ с аналитикой"""
    success: bool = Field(..., description="Успешно ли получена аналитика")
    data: Optional[Analytics] = Field(None, description="Данные аналитики")
    message: Optional[str] = Field(None, description="Сообщение об ошибке")


class RegisteredRunnerInfo(BaseModel):
    """Информация о зарегистрированном участнике из БД"""
    
    id: Optional[str] = Field(None)
    name: str = Field(..., description="Имя")
    surname: str = Field(..., description="Фамилия")
    full_name: str = Field(..., description="Полное имя")
    category: Optional[str] = Field(None, description="Возрастная категория")
    city: Optional[str] = Field(None, description="Город")
    sex: Optional[str] = Field(None, description="Пол (Мужчина/Женщина)")
    club: Optional[str] = Field(None, description="Клуб")
    birthday: Optional[str] = Field(None, description="Дата рождения")
    registration_date: Optional[str] = Field(None, description="Дата регистрации")


class RegisteredRunnersListResponse(BaseModel):
    """Список зарегистрированных участников"""
    
    total: int = Field(..., description="Всего зарегистрировано")
    runners: List[RegisteredRunnerInfo] = Field(..., description="Список участников")


class RaceResultsResponse(BaseModel):
    """Результаты гонки"""
    
    event: str = Field(..., description="ID события")
    total_results: int = Field(..., description="Всего результатов")
    results: List[Dict[str, Any]] = Field(..., description="Результаты участников")
    timestamp: str = Field(..., description="Время получения результатов")
