"""
Модели для сегментов маршрута и контрольных точек
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class Segment(BaseModel):
    """Модель сегмента результата спортсмена (контрольная точка)"""
    
    id: int = Field(..., description="ID записи в result_segments")
    result_id: int = Field(..., description="ID результата спортсмена")
    event_id: Optional[int] = Field(None, description="ID мероприятия")
    segment_code: str = Field(..., description="Код сегмента (kt1, kt2, kt3, kt4, kt5)")
    sg_time_clear: Optional[str] = Field(None, description="Чистое время прохождения (HH:MM:SS)")
    sg_pace_avg: Optional[str] = Field(None, description="Средний темп на сегменте (м:сс)")
    sg_rank_absolute: Optional[int] = Field(None, description="Абсолютное место на сегменте")
    sg_rank_sex: Optional[int] = Field(None, description="Место по полу на сегменте")
    sg_rank_category: Optional[int] = Field(None, description="Место по категории на сегменте")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "result_id": 123,
                "segment_code": "kt1",
                "sg_time_clear": "00:08:45",
                "sg_pace_avg": "7:22",
                "sg_rank_absolute": 15,
                "sg_rank_sex": 8,
                "sg_rank_category": 3
            }
        }


class SegmentsListResponse(BaseModel):
    """Ответ со списком сегментов спортсмена"""
    
    success: bool = Field(..., description="Успешность запроса")
    runner_id: int = Field(..., description="ID спортсмена")
    event: str = Field(..., description="ID события")
    segments: List[Segment] = Field(default_factory=list, description="Список сегментов")
    count: int = Field(default=0, description="Количество сегментов")
    message: Optional[str] = Field(None, description="Сообщение об ошибке или успехе")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "runner_id": 123,
                "event": "night_run",
                "segments": [
                    {
                        "id": 1,
                        "result_id": 123,
                        "segment_code": "kt1",
                        "sg_time_clear": "00:08:45",
                        "sg_pace_avg": "7:22",
                        "sg_rank_absolute": 15,
                        "sg_rank_sex": 8,
                        "sg_rank_category": 3
                    }
                ],
                "count": 1
            }
        }
