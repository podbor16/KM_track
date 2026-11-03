"""
Модели данных для аналитики (Pydantic)
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


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
    distance: Optional[str] = Field(None, description="Дистанция забега (км)")
    registration_date: Optional[str] = Field(None, description="Дата регистрации")
    start_number: Optional[int] = Field(None, description="Стартовый номер (bib), если присвоен заранее организатором")
    lead_id: Optional[int] = Field(None, description="id заявки (leads.id) — для диплома участника /diploma/lead/{lead_id}")
    event_id: Optional[int] = Field(None, description="id события-дистанции (events.id)")
    is_elite: Optional[int] = Field(None, description="«Элита» — на сайте вместо номера")
    is_pacer: Optional[int] = Field(None, description="«Пейсер» — на сайте вместо номера")
    pd_refused: Optional[int] = Field(None, description="Не согласен на публикацию ПД — на публичных страницах «Спортсмен»")


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
    server_time_unix: Optional[int] = Field(None, description="Unix ms когда был сформирован ответ — для экстраполяции позиций на клиенте")
    race_gun_unix_ms: Optional[int] = Field(None, description="Unix ms момента выстрела стартового пистолета")
    total_distance_km: Optional[float] = Field(None, description="Полная дистанция забега в км (для правильного масштаба маркера)")
