"""
Admin API роутер — управление конфигами событий и загрузчиком результатов.
Все endpoints требуют авторизации через cookie-сессию.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.tracker.models.startlist import LeadPatch, LeadAdminItem, LeadsAdminResponse

from src.config import settings
from src.config.event_loader import (
    get_active_event,
    invalidate_events_cache,
    load_events_cached,
)
from src.core.auth import api_require_auth

router = APIRouter(tags=["Admin"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
EVENTS_DIR = BASE_DIR / "config" / "events"
PRESETS_DIR = BASE_DIR / "config" / "copernico"
LOADERS_DIR = BASE_DIR / "config" / "loader"


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
    """Ищет config/loader/*.env с LOADER_CONFIG=.../events/{event_code}.yaml"""
    for f in LOADERS_DIR.glob("*.env"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("LOADER_CONFIG=") and f"/{event_code}.yaml" in line:
                return f.stem
    return None


def _loader_event_code(loader_name: str) -> Optional[str]:
    """Извлекает event_code из config/loader/{loader_name}.env"""
    env_file = LOADERS_DIR / f"{loader_name}.env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("LOADER_CONFIG="):
            path = line.split("=", 1)[1].strip()
            return Path(path).stem
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
            "is_active": ev.is_active,
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

    # Переключить is_active в YAML через ruamel.yaml
    try:
        from ruamel.yaml import YAML
        _yaml = YAML()
        _yaml.preserve_quotes = True

        for yaml_file in EVENTS_DIR.glob("*.yaml"):
            with yaml_file.open("r", encoding="utf-8") as f:
                data = _yaml.load(f)
            if not isinstance(data, dict):
                continue
            event_code = data.get("code", yaml_file.stem)
            new_val = (event_code == code)
            if data.get("is_active") != new_val:
                data["is_active"] = new_val
                with yaml_file.open("w", encoding="utf-8") as f:
                    _yaml.dump(data, f)
    except ImportError:
        # Fallback: PyYAML (потеряет комментарии, но сработает)
        for yaml_file in EVENTS_DIR.glob("*.yaml"):
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            event_code = data.get("code", yaml_file.stem)
            data["is_active"] = (event_code == code)
            yaml_file.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False), encoding="utf-8")

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
    return sorted(f.stem for f in PRESETS_DIR.glob("*.yaml"))


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
    rows, total = await asyncio.gather(
        asyncio.get_event_loop().run_in_executor(None, lambda: get_leads_admin(**kw, offset=offset, limit=limit)),
        asyncio.get_event_loop().run_in_executor(None, lambda: count_leads_admin(**kw)),
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
