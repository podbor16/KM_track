"""
Pydantic-модели для настраиваемых возрастных групп (admin API) — см.
src/analytics/db_results.py: list_age_groups()/create_age_group()/
update_age_group()/delete_age_group(), get_age_group_label().
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel


class AgeGroupConfig(BaseModel):
    """Одна граница возрастной группы — ответ API."""

    id: int
    event_name: str
    event_distance: str
    sex: str  # 'M' | 'F'
    min_age: int
    max_age: Optional[int] = None
    label: str


class AgeGroupCreate(BaseModel):
    """Тело POST /api/admin/age-groups."""

    event_name: str
    event_distance: str
    sex: str
    min_age: int
    max_age: Optional[int] = None
    label: str


class AgeGroupPatch(BaseModel):
    """Тело PATCH /api/admin/age-groups/{id} — все поля Optional."""

    event_name: Optional[str] = None
    event_distance: Optional[str] = None
    sex: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    label: Optional[str] = None

    def non_null_fields(self) -> Dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}
