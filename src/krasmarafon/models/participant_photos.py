"""
Pydantic-модели для фото участников live-топ-10 трансляции (admin API) — см.
src/analytics/db_results.py: list_db_events()/list_participant_photos()/
upsert_participant_photo()/delete_participant_photo().
"""

from pydantic import BaseModel


class DbEvent(BaseModel):
    """Событие из таблицы events — для выбора event_id в /admin."""

    id: int
    event_name: str
    event_distance: float
    event_year: int


class ParticipantPhoto(BaseModel):
    """Одна ссылка на фото — ответ API."""

    id: int
    event_id: int
    start_number: int
    photo_url: str


class ParticipantPhotoUpsert(BaseModel):
    """Тело POST /api/admin/participant-photos."""

    event_id: int
    start_number: int
    photo_url: str
