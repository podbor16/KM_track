"""
Admin API роутер — управление конфигами событий и загрузчиком результатов.
Все endpoints требуют авторизации через cookie-сессию.
"""

import asyncio
import pickle
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from src.krasmarafon.models.startlist import (
    LeadPatch, LeadAdminItem, LeadsAdminResponse,
    LeadImportPreviewRow, LeadImportPreviewResponse, LeadImportApplyResponse,
    LeadImportFailedRow,
)
from src.krasmarafon.models.age_groups import AgeGroupConfig, AgeGroupCreate, AgeGroupPatch
from src.krasmarafon.models.participant_photos import DbEvent, ParticipantPhoto, ParticipantPhotoUpsert

from src.config import settings
from src.config.event_loader import (
    get_active_event,
    get_history_enabled,
    invalidate_events_cache,
    load_events_cached,
    set_active_event_override,
    set_history_enabled,
)
from src.core.auth import api_require_auth

router = APIRouter(tags=["Admin"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
EVENTS_DIR = BASE_DIR / "config" / "events"
PRESETS_DIR = BASE_DIR / "config" / "copernico"
LOADERS_DIR = BASE_DIR / "config" / "loader"

# Pending-файлы bulk-импорта Tilda — общий для всех воркеров gunicorn,
# как аналогичный паттерн у Siberman-загрузчика (src/siberman/router.py:52)
_LEADS_IMPORT_PENDING_DIR = Path(tempfile.gettempdir()) / "leads_import_pending"
_LEADS_IMPORT_PENDING_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _systemctl(action: str, name: str) -> tuple[bool, str]:
    """sudo systemctl {action} km_race_loader@{name}.service"""
    try:
        r = subprocess.run(
            ["sudo", "systemctl", action, f"km_race_loader@{name}.service"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def _event_file(code: str) -> Optional[Path]:
    """Находит YAML-файл события по code (имя файла может не совпадать с code)."""
    exact = EVENTS_DIR / f"{code}.yaml"
    if exact.exists():
        return exact
    for f in EVENTS_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("code") == code:
                return f
        except Exception:
            pass
    return None


def _loader_for_event(event_code: str) -> Optional[str]:
    """Ищет config/loader/*.env, чей LOADER_CONFIG указывает на YAML с данным code."""
    for f in LOADERS_DIR.glob("*.env"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.startswith("LOADER_CONFIG="):
                continue
            yaml_path = BASE_DIR / line.split("=", 1)[1].strip()
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and data.get("code", yaml_path.stem) == event_code:
                return f.stem
    return None


def _loader_event_code(loader_name: str) -> Optional[str]:
    """Извлекает event_code из config/loader/{loader_name}.env, читая поле code из YAML."""
    env_file = LOADERS_DIR / f"{loader_name}.env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("LOADER_CONFIG="):
            yaml_path = BASE_DIR / line.split("=", 1)[1].strip()
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("code"):
                    return data["code"]
            except Exception:
                pass
            return yaml_path.stem
    return None


def _reload_settings() -> None:
    invalidate_events_cache()
    events = load_events_cached()
    active = get_active_event(events)
    settings.EVENTS = events
    if active:
        settings.CURRENT_EVENT = active.code


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class YamlBody(BaseModel):
    yaml: str


# ---------------------------------------------------------------------------
# История участия (/history, /athlete-profile) — временный переключатель
# ---------------------------------------------------------------------------


@router.get("/api/admin/history-status")
async def get_history_status(user: str = Depends(api_require_auth)) -> dict:
    return {"enabled": get_history_enabled()}


@router.post("/api/admin/history-toggle")
async def toggle_history(enabled: bool, user: str = Depends(api_require_auth)) -> dict:
    set_history_enabled(enabled)
    return {"enabled": enabled}


# ---------------------------------------------------------------------------
# Events API
# ---------------------------------------------------------------------------


@router.get("/api/admin/events")
async def list_events(user: str = Depends(api_require_auth)) -> list[dict]:
    result = []
    for code, ev in settings.EVENTS.items():
        db_event_ids = [
            {"db_event_id": d.db_event_id, "distance": d.distance}
            for d in ev.distances
            if d.db_event_id is not None
        ]
        result.append({
            "code": code,
            "name": ev.name,
            "is_active": (code == settings.CURRENT_EVENT),
            "db_event_ids": db_event_ids,
        })
    return result


@router.get("/api/admin/events/{code}/yaml")
async def get_event_yaml(code: str, user: str = Depends(api_require_auth)) -> dict:
    path = _event_file(code)
    if not path:
        raise HTTPException(status_code=404, detail=f"Конфиг события '{code}' не найден")
    return {"yaml": path.read_text(encoding="utf-8")}


@router.put("/api/admin/events/{code}/yaml")
async def save_event_yaml(
    code: str, body: YamlBody, user: str = Depends(api_require_auth)
) -> dict:
    path = _event_file(code)
    if not path:
        raise HTTPException(status_code=404, detail=f"Конфиг события '{code}' не найден")
    try:
        yaml.safe_load(body.yaml)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Невалидный YAML: {e}")
    path.write_text(body.yaml, encoding="utf-8")
    _reload_settings()
    return {"status": "ok"}


@router.post("/api/admin/events/{code}/activate")
async def activate_event(code: str, user: str = Depends(api_require_auth)) -> dict:
    if code not in settings.EVENTS:
        raise HTTPException(status_code=404, detail=f"Событие '{code}' не найдено")

    # Остановить старый загрузчик
    old_code = settings.CURRENT_EVENT
    old_loader = _loader_for_event(old_code)
    if old_loader:
        _systemctl("stop", old_loader)

    # Активное событие хранится вне git (config/active_event.local), а не в самих
    # YAML — иначе очередной деплой (git checkout) затирал бы переключение из /admin.
    set_active_event_override(code)
    _reload_settings()

    # Запустить новый загрузчик
    new_loader = _loader_for_event(code)
    loader_started = False
    loader_output = ""
    if new_loader:
        ok, loader_output = _systemctl("start", new_loader)
        loader_started = ok

    return {
        "status": "ok",
        "active_event": code,
        "loader_started": loader_started,
        "loader_name": new_loader,
        "loader_output": loader_output,
    }


# ---------------------------------------------------------------------------
# Presets API
# ---------------------------------------------------------------------------


@router.get("/api/admin/presets")
async def list_presets(user: str = Depends(api_require_auth)) -> list[str]:
    return sorted(f.stem for f in PRESETS_DIR.glob("*.yaml") if not f.stem.startswith("tri_"))


@router.get("/api/admin/presets/{name}/yaml")
async def get_preset_yaml(name: str, user: str = Depends(api_require_auth)) -> dict:
    path = PRESETS_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Пресет '{name}' не найден")
    return {"yaml": path.read_text(encoding="utf-8")}


@router.put("/api/admin/presets/{name}/yaml")
async def save_preset_yaml(
    name: str, body: YamlBody, user: str = Depends(api_require_auth)
) -> dict:
    path = PRESETS_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Пресет '{name}' не найден")
    try:
        yaml.safe_load(body.yaml)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Невалидный YAML: {e}")
    path.write_text(body.yaml, encoding="utf-8")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Loader API
# ---------------------------------------------------------------------------


@router.get("/api/admin/loader")
async def loader_status(user: str = Depends(api_require_auth)) -> list[dict]:
    result = []
    for env_file in sorted(LOADERS_DIR.glob("*.env")):
        name = env_file.stem
        if name.startswith("tri_"):  # tri loaders управляются через /tri/admin
            continue
        event_code = _loader_event_code(name)
        event_name = settings.EVENTS.get(event_code, None)
        ok, _ = _systemctl("is-active", name)
        result.append({
            "name": name,
            "event_code": event_code,
            "event_name": event_name.name if event_name else event_code,
            "status": "active" if ok else "inactive",
        })
    return result


@router.post("/api/admin/loader/{name}/start")
async def loader_start(name: str, user: str = Depends(api_require_auth)) -> dict:
    ok, output = _systemctl("start", name)
    return {"status": "ok" if ok else "error", "output": output}


@router.post("/api/admin/loader/{name}/stop")
async def loader_stop(name: str, user: str = Depends(api_require_auth)) -> dict:
    ok, output = _systemctl("stop", name)
    return {"status": "ok" if ok else "error", "output": output}


@router.post("/api/admin/loader/{name}/init")
async def loader_init(name: str, user: str = Depends(api_require_auth)) -> dict:
    """Запустить загрузчик в режиме --init (первичный INSERT участников из Copernico)."""
    import sys

    env_file = LOADERS_DIR / f"{name}.env"
    if not env_file.exists():
        raise HTTPException(status_code=404, detail=f"Конфиг загрузчика '{name}' не найден")

    config_path, distance = None, None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("LOADER_CONFIG="):
            config_path = line.split("=", 1)[1].strip()
        elif line.startswith("LOADER_DISTANCE="):
            distance = line.split("=", 1)[1].strip().strip('"')

    if not config_path or not distance:
        raise HTTPException(status_code=400, detail="Не найдены LOADER_CONFIG или LOADER_DISTANCE в .env файле")

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(BASE_DIR / "load_race_results.py"),
            "--config", config_path,
            "--distance", distance,
            "--init",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BASE_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        output = (stdout + stderr).decode("utf-8", errors="replace")

        inserted = 0
        orphaned = []
        for line in output.splitlines():
            if "Вставлено:" in line:
                try:
                    inserted = int(line.split("Вставлено:")[1].split()[0])
                except Exception:
                    pass
            if "ОСИРОТЕВШИЙ:" in line:
                orphaned.append(line.split("ОСИРОТЕВШИЙ:")[1].strip())

        success = proc.returncode == 0
        return {
            "status": "ok" if success else "error",
            "inserted": inserted,
            "orphaned": orphaned,
            "output": output[-3000:],
        }
    except asyncio.TimeoutError:
        return {"status": "error", "inserted": 0, "orphaned": [], "output": "Timeout: Copernico API не ответил за 3 минуты"}
    except Exception as e:
        return {"status": "error", "inserted": 0, "orphaned": [], "output": str(e)}


# ---------------------------------------------------------------------------
# Leads API
# ---------------------------------------------------------------------------

@router.get("/api/admin/leads/meta")
async def leads_meta(
    event_name: Optional[str] = None,
    event_year: Optional[int] = None,
    user: str = Depends(api_require_auth),
) -> dict:
    """Distinct значения для каскадных фильтров."""
    from src.analytics.db_results import get_leads_filter_options
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: get_leads_filter_options(event_name=event_name, event_year=event_year),
    )


@router.get("/api/admin/leads")
async def list_leads(
    event_id: Optional[int] = None,
    event_name: Optional[str] = None,
    event_year: Optional[int] = None,
    event_distance: Optional[str] = None,
    is_duplicate: Optional[bool] = None,
    is_name_suspicious: Optional[bool] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = Query(default=100, le=500),
    user: str = Depends(api_require_auth),
) -> dict:
    """Постраничный список лидов с фильтрацией и поиском."""
    from src.analytics.db_results import get_leads_admin, count_leads_admin

    kw = dict(
        event_id=event_id, event_name=event_name, event_year=event_year,
        event_distance=event_distance, is_duplicate=is_duplicate,
        is_name_suspicious=is_name_suspicious, search=search,
    )
    # Последовательно — избегаем одновременного захвата двух соединений из пула
    rows = await asyncio.get_event_loop().run_in_executor(
        None, lambda: get_leads_admin(**kw, offset=offset, limit=limit)
    )
    total = await asyncio.get_event_loop().run_in_executor(
        None, lambda: count_leads_admin(**kw)
    )
    items = [LeadAdminItem.model_validate(r) for r in rows]
    return LeadsAdminResponse(items=items, count=len(items), total=total, offset=offset, limit=limit).model_dump()


@router.patch("/api/admin/leads/{lead_id}")
async def patch_lead(
    lead_id: int,
    body: LeadPatch,
    user: str = Depends(api_require_auth),
) -> dict:
    """Частичное обновление лида по leads.id."""
    from src.analytics.db_results import update_lead

    fields = body.non_null_fields()
    if not fields:
        raise HTTPException(status_code=422, detail="Нет полей для обновления")
    updated = await asyncio.get_event_loop().run_in_executor(
        None, lambda: update_lead(lead_id, fields)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Лид {lead_id} не найден")
    return LeadAdminItem.model_validate(updated).model_dump()


# --- Возрастные группы (age_group_configs) --------------------------------
# Границы для конкретных (event_name, event_distance) — переопределяют
# дефолтную формулу calculate_age_group() при отображении регистраций
# (/start_list, /admin → «Стартовый список»). Результаты после финиша
# (results.category, из Copernico) не затрагиваются — сознательно вне
# объёма этого API.

@router.get("/api/admin/age-groups")
async def list_age_groups_endpoint(
    event_name: Optional[str] = Query(None),
    event_distance: Optional[str] = Query(None),
    user: str = Depends(api_require_auth),
) -> dict:
    from src.analytics.db_results import list_age_groups

    rows = await asyncio.get_event_loop().run_in_executor(
        None, lambda: list_age_groups(event_name, event_distance)
    )
    return {"items": [AgeGroupConfig.model_validate(r).model_dump() for r in rows]}


@router.post("/api/admin/age-groups")
async def create_age_group_endpoint(
    body: AgeGroupCreate, user: str = Depends(api_require_auth)
) -> dict:
    from src.analytics.db_results import create_age_group

    created = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: create_age_group(
            body.event_name, body.event_distance, body.sex,
            body.min_age, body.max_age, body.label,
        ),
    )
    if created is None:
        raise HTTPException(status_code=400, detail="Не удалось создать границу (возможно, дубликат)")
    return AgeGroupConfig.model_validate(created).model_dump()


@router.patch("/api/admin/age-groups/{config_id}")
async def patch_age_group_endpoint(
    config_id: int, body: AgeGroupPatch, user: str = Depends(api_require_auth)
) -> dict:
    from src.analytics.db_results import update_age_group

    fields = body.non_null_fields()
    if not fields:
        raise HTTPException(status_code=422, detail="Нет полей для обновления")
    updated = await asyncio.get_event_loop().run_in_executor(
        None, lambda: update_age_group(config_id, fields)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Граница {config_id} не найдена")
    return AgeGroupConfig.model_validate(updated).model_dump()


@router.delete("/api/admin/age-groups/{config_id}")
async def delete_age_group_endpoint(
    config_id: int, user: str = Depends(api_require_auth)
) -> dict:
    from src.analytics.db_results import delete_age_group

    deleted = await asyncio.get_event_loop().run_in_executor(
        None, lambda: delete_age_group(config_id)
    )
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Граница {config_id} не найдена")
    return {"status": "ok"}


# Числовой event_id для вкладки «Фото участников» — age_group_configs
# использует event_name+event_distance строки, но participant_photos
# ссылается на реальный results.event_id, поэтому нужен отдельный список
# с настоящими ID.

@router.get("/api/admin/db-events")
async def list_db_events_endpoint(user: str = Depends(api_require_auth)) -> dict:
    from src.analytics.db_results import list_db_events

    rows = await asyncio.get_event_loop().run_in_executor(None, list_db_events)
    return {"items": [DbEvent.model_validate(r).model_dump() for r in rows]}


@router.get("/api/admin/participant-photos")
async def list_participant_photos_endpoint(
    event_id: int = Query(...), user: str = Depends(api_require_auth)
) -> dict:
    from src.analytics.db_results import list_participant_photos

    rows = await asyncio.get_event_loop().run_in_executor(
        None, lambda: list_participant_photos(event_id)
    )
    return {"items": [ParticipantPhoto.model_validate(r).model_dump() for r in rows]}


@router.post("/api/admin/participant-photos")
async def upsert_participant_photo_endpoint(
    body: ParticipantPhotoUpsert, user: str = Depends(api_require_auth)
) -> dict:
    from src.analytics.db_results import upsert_participant_photo

    saved = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: upsert_participant_photo(body.event_id, body.start_number, body.photo_url),
    )
    if saved is None:
        raise HTTPException(status_code=400, detail="Не удалось сохранить фото")
    return ParticipantPhoto.model_validate(saved).model_dump()


@router.delete("/api/admin/participant-photos/{photo_id}")
async def delete_participant_photo_endpoint(
    photo_id: int, user: str = Depends(api_require_auth)
) -> dict:
    from src.analytics.db_results import delete_participant_photo

    deleted = await asyncio.get_event_loop().run_in_executor(
        None, lambda: delete_participant_photo(photo_id)
    )
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Фото {photo_id} не найдено")
    return {"status": "ok"}


@router.post("/api/admin/leads/import/upload")
async def upload_leads_import(
    file: UploadFile = File(...),
    event_name: Optional[str] = Form(None),
    event_year: Optional[int] = Form(None),
    user: str = Depends(api_require_auth),
) -> dict:
    """Шаг 1 bulk-импорта заявок из выгрузки Tilda: парсит файл, строит
    превью совпадений (обновится/создастся), сохраняет разобранные строки
    во временный pending-файл — реальная запись в БД только на /apply.

    event_name/event_year — событие и год, выбранные в /admin перед
    загрузкой файла (фильтры вкладки «Стартовый список»). Используются
    ТОЛЬКО как фоллбэк — когда у строки нет полного текста продукта, а есть
    отдельная колонка "Дистанция" (см. tilda_import_parser._extract_event_info,
    реальный случай — организатор вручную укоротил product-текст при
    переносе участника на другую дистанцию, 2026-08-18)."""
    from src.krasmarafon.services.tilda_import_parser import parse_tilda_export
    from src.analytics.db_results import preview_leads_import_matches

    data = await file.read()
    try:
        parsed = await asyncio.get_event_loop().run_in_executor(
            None, lambda: parse_tilda_export(data, file.filename or "", event_name, event_year)
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    preview_rows = await asyncio.get_event_loop().run_in_executor(
        None, lambda: preview_leads_import_matches(parsed.rows)
    )

    token = secrets.token_urlsafe(16)
    with open(_LEADS_IMPORT_PENDING_DIR / f"{token}.pkl", "wb") as f:
        pickle.dump(parsed, f)

    return LeadImportPreviewResponse(
        token=token,
        total_rows=parsed.total_rows,
        to_update=sum(1 for r in preview_rows if r["will"] == "update"),
        to_create=sum(1 for r in preview_rows if r["will"] == "create"),
        parse_errors=parsed.errors,
        sample=[LeadImportPreviewRow(**r) for r in preview_rows[:50]],
        unknown_headers=parsed.unknown_headers,
        failed_rows=[LeadImportFailedRow(**r) for r in parsed.failed_rows],
    ).model_dump()


@router.post("/api/admin/leads/import/apply")
async def apply_leads_import(
    token: str,
    user: str = Depends(api_require_auth),
) -> dict:
    """Шаг 2 bulk-импорта: применяет ранее разобранный и подтверждённый
    файл (по token из /upload) — UPDATE совпавших заявок, INSERT
    несовпавших. Очищает pending-файл после применения."""
    from src.analytics.db_results import bulk_import_leads

    path = _LEADS_IMPORT_PENDING_DIR / f"{token}.pkl"
    if not path.exists():
        raise HTTPException(status_code=400, detail="Нет данных для импорта — загрузите файл заново")
    with open(path, "rb") as f:
        parsed = pickle.load(f)

    summary = await asyncio.get_event_loop().run_in_executor(
        None, lambda: bulk_import_leads(parsed.rows)
    )
    path.unlink(missing_ok=True)
    return LeadImportApplyResponse(**summary).model_dump()


# ---------------------------------------------------------------------------
# DataLens embeds (для вкладки Аналитика в /admin)
# ---------------------------------------------------------------------------

@router.get("/api/admin/datalens-embeds")
async def admin_datalens_embeds(user: str = Depends(api_require_auth)) -> dict:
    """Генерирует свежие JWT-токены для DataLens iframe."""
    from src.core.datalens import make_embed_token

    embeds = []
    if settings.DATALENS_KEY_SECRET:
        try:
            for cfg in settings.DATALENS_EMBEDS:
                token = make_embed_token(cfg["id"], settings.DATALENS_KEY_SECRET)
                embed_type = cfg.get("type", "dash")
                embeds.append({
                    "url": f"https://datalens.ru/embeds/{embed_type}#dl_embed_token={token}",
                    "title": cfg.get("title", ""),
                })
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"DataLens admin embed error: {e}")
    return {"embeds": embeds}
