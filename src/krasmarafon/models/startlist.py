"""
Pydantic-модели для стартового списка и admin leads API.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, model_validator


class StartlistItem(BaseModel):
    """Публичная запись стартового списка (без birthday и чувствительных данных)."""

    surname: str
    name: str
    sex: Optional[str] = None
    city: Optional[str] = None
    club: Optional[str] = None
    event_distance: Optional[str] = None
    category: Optional[str] = None


class StartlistResponse(BaseModel):
    """Ответ GET /api/startlist/{event_id}."""

    items: List[StartlistItem]
    count: int


class LeadAdminItem(BaseModel):
    """Полная строка лида для admin-эндпоинтов (все колонки + category)."""

    id: int
    surname: Optional[str] = None
    name: Optional[str] = None
    sex: Optional[str] = None
    city: Optional[str] = None
    club: Optional[str] = None
    birthday: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    event_name: Optional[str] = None
    event_distance: Optional[str] = None
    event_year: Optional[int] = None
    products: Optional[str] = None
    payment_system: Optional[str] = None
    transaction_id: Optional[str] = None
    order_id: Optional[Any] = None
    promocode: Optional[str] = None
    discount: Optional[Any] = None
    amount: Optional[Any] = None
    is_name_suspicious: Optional[int] = None
    client_id: Optional[Any] = None
    event_id: Optional[int] = None
    is_duplicate: Optional[int] = None
    status: Optional[Any] = None
    is_new: Optional[int] = None
    is_new_event: Optional[int] = None
    category: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def _coerce_birthday(cls, values: Any) -> Any:
        """Приводит birthday: date/datetime → строку ISO."""
        if isinstance(values, dict):
            bday = values.get('birthday')
            if bday is not None and hasattr(bday, 'isoformat'):
                values['birthday'] = bday.isoformat()[:10]
        return values

    class Config:
        arbitrary_types_allowed = True


class LeadsAdminResponse(BaseModel):
    """Ответ GET /api/admin/leads."""

    items: List[LeadAdminItem]
    count: int   # записей на этой странице
    total: int   # всего записей с текущими фильтрами
    offset: int
    limit: int


class LeadPatch(BaseModel):
    """Тело PATCH /api/admin/leads/{id} — все поля Optional."""

    surname: Optional[str] = None
    name: Optional[str] = None
    event_distance: Optional[str] = None
    is_duplicate: Optional[int] = None
    status: Optional[Any] = None

    def non_null_fields(self) -> Dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class LeadImportPreviewRow(BaseModel):
    """Одна строка превью bulk-импорта Tilda — что будет с ней при apply."""

    row_number: int
    surname: str
    name: str
    birthday: str
    event_name: str
    event_distance: str
    matched_count: int
    will: str   # "update" | "create" | "unknown"


class LeadImportFailedRow(BaseModel):
    """Одна строка, пропущенная при разборе Tilda-импорта — для подсветки
    в таблице превью (не только текстом в parse_errors)."""

    row_number: int
    surname: str
    name: str
    birthday: str
    reason: str


class LeadImportPreviewResponse(BaseModel):
    """Ответ POST /api/admin/leads/import/upload."""

    token: str
    total_rows: int
    to_update: int
    to_create: int
    parse_errors: List[str]
    sample: List[LeadImportPreviewRow]
    unknown_headers: List[str] = []
    failed_rows: List[LeadImportFailedRow] = []


class LeadImportApplyResponse(BaseModel):
    """Ответ POST /api/admin/leads/import/apply."""

    updated: int
    created: int
    errors: List[str]
