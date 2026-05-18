"""
JSON API эндпоинты KM_track.
Все /api/* маршруты, возвращающие JSON.
"""

import asyncio
import logging
import json
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query, Request, Depends, HTTPException, Path as PathParam
from fastapi.responses import RedirectResponse, Response
from sse_starlette.sse import EventSourceResponse

from src.tracker.services.notification_hub import tracker_hub, notification_hub

from src.config import settings
from src.config.event_loader import (
    RouteConfig, load_events_cached, get_active_event, invalidate_events_cache,
)
from src.core.state import AppState
from src.core.dependencies import get_app_state
from src.core.auth import require_auth
from src.monitoring.collector import MetricsCollector, hours_to_bucket_secs
from src.tracker.models import (
    RunnerSelectionRequest, SelectedRunnersResponse,
    RaceConfig,
    CurrentEventResponse, DistanceInfo, CheckpointInfo, EventsListResponse,
    Analytics, AnalyticsResponse, RegisteredRunnersListResponse, RaceResultsResponse,
    Segment, SegmentsListResponse,
)
from src.tracker.services import get_formatted_analytics
from src.tracker import services as _svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["API"])


# ============================================================================
# СОБЫТИЯ (EVENTS)
# ============================================================================

@router.get("/api/current-event", response_model=CurrentEventResponse)
async def get_current_event() -> CurrentEventResponse:
    """Текущее активное событие. Перечитывает YAML с TTL-кешем 30 сек."""
    events = load_events_cached()
    active = get_active_event(events)
    code = active.code if active else settings.CURRENT_EVENT
    event = events.get(code)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {code} not configured")
    tracked = event.get_tracked()
    route_type = 'shuttle' if (tracked and tracked.route.laps > 1) else 'loop'

    tracked_distances = [d for d in event.distances if d.tracked]
    distances_info = [
        DistanceInfo(
            distance=d.distance,
            distance_km=d.distance_km,
            db_event_id=d.db_event_id,
            gpx_file=d.gpx_file,
            event_date=d.event_date,
            route_type='shuttle' if d.route.laps > 1 else 'loop',
            laps=d.route.laps,
            checkpoints=[
                CheckpointInfo(name=cp.name, distance_km=cp.distance_km, lat=cp.lat, lon=cp.lon)
                for cp in d.checkpoints
            ],
        )
        for d in tracked_distances
    ]

    return CurrentEventResponse(
        event=code,
        storage_key=f"{code}_selected_runners",
        name=event.name,
        title=event.title,
        description=event.description,
        route_type=route_type,
        year=event.year,
        start_lat=event.start_lat,
        start_lon=event.start_lon,
        gpx_file=tracked.gpx_file if tracked else None,
        db_event_id=tracked.db_event_id if tracked else None,
        distances=distances_info,
    )


@router.post("/api/admin/reload-config")
async def reload_config(request: Request) -> dict:
    """Немедленно перезагружает YAML-конфиги забегов без перезапуска сервера."""
    from src.core.auth import verify_session_cookie, COOKIE_NAME
    try:
        verify_session_cookie(request.cookies.get(COOKIE_NAME, ""))
    except Exception:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    invalidate_events_cache()
    events = load_events_cached()
    active = get_active_event(events)
    settings.EVENTS = events
    settings.CURRENT_EVENT = active.code if active else settings.CURRENT_EVENT
    return {"status": "ok", "active_event": settings.CURRENT_EVENT, "events_count": len(events)}


@router.get("/api/events", response_model=EventsListResponse)
async def get_events() -> EventsListResponse:
    """Список всех доступных событий."""
    events_list = []
    for code, event in settings.EVENTS.items():
        tracked = event.get_tracked()
        events_list.append({
            "id": code,
            "name": event.name,
            "title": event.title,
            "distance": tracked.distance_km if tracked else 0,
        })
    return EventsListResponse(events=events_list, current=settings.CURRENT_EVENT)


@router.get("/api/race-config", response_model=RaceConfig)
async def get_race_config(event: str = Query(settings.CURRENT_EVENT)) -> RaceConfig:
    """Конфигурация гонки (дистанция, тип маршрута, контрольные точки)."""
    event_cfg = settings.EVENTS.get(event)
    if not event_cfg:
        raise HTTPException(status_code=404, detail=f"Event '{event}' not found")
    tracked = event_cfg.get_tracked()
    route = tracked.route if tracked else RouteConfig()
    route_type = 'shuttle' if route.laps > 1 else 'loop'
    return RaceConfig(
        total_distance=route.total_km or 0,
        event_name=event_cfg.name,
        event_id=event,
        route_type=route_type,
        one_way_length=route.one_way_length_km,
        laps=route.laps,
        lap_length=None,
        checkpoints=[],
    )


# ============================================================================
# УЧАСТНИКИ (RUNNERS)
# ============================================================================

@router.get("/api/search-athletes")
async def search_athletes(
    q: str = Query("", min_length=1, description="Фамилия или имя для поиска"),
):
    """Поиск спортсменов по фамилии/имени (таблица clients). Максимум 20 результатов."""
    try:
        from src.analytics.db_connection_optimized import search_clients_optimized
        results = await asyncio.get_event_loop().run_in_executor(
            None, search_clients_optimized, q
        )
        return {'query': q, 'count': len(results), 'results': results[:20]}
    except Exception as e:
        logger.error(f"search_athletes error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/athlete/{surname}/{name}")
async def get_athlete_profile(
    surname: str = PathParam(..., description="Фамилия"),
    name: str = PathParam(..., description="Имя"),
):
    """Профиль спортсмена и все его результаты."""
    try:
        from src.analytics.db_connection_optimized import get_athlete_results_optimized

        athlete_info, results = get_athlete_results_optimized(surname, name)

        if not athlete_info and not results:
            raise HTTPException(
                status_code=404,
                detail=f"Спортсмен {surname} {name} не найден"
            )

        def _format(d: dict) -> dict:
            return {
                k: v.isoformat() if hasattr(v, 'isoformat') else v
                for k, v in d.items()
            }

        return {
            'athlete': _format(athlete_info),
            'results': [_format(r) for r in results],
            'total_races': len(results),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_athlete_profile error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/select-runner", response_model=SelectedRunnersResponse)
async def select_runner(
    request: RunnerSelectionRequest,
    event: str = Query(settings.CURRENT_EVENT),
    state: AppState = Depends(get_app_state),
) -> SelectedRunnersResponse:
    """Добавить участника в список отслеживания."""
    state.selected_runners.setdefault(event, set()).add(request.runner_id)
    if len(state.selected_runners[event]) > settings.MAX_SELECTED_RUNNERS:
        state.selected_runners[event].pop()
    return SelectedRunnersResponse(
        event=event,
        selected_ids=list(state.selected_runners[event]),
        count=len(state.selected_runners[event]),
    )


@router.post("/api/deselect-runner", response_model=SelectedRunnersResponse)
async def deselect_runner(
    request: RunnerSelectionRequest,
    event: str = Query(settings.CURRENT_EVENT),
    state: AppState = Depends(get_app_state),
) -> SelectedRunnersResponse:
    """Удалить участника из списка отслеживания."""
    if event in state.selected_runners:
        state.selected_runners[event].discard(request.runner_id)
    selected = state.selected_runners.get(event, set())
    return SelectedRunnersResponse(
        event=event, selected_ids=list(selected), count=len(selected),
    )


@router.get("/api/selected-runners", response_model=SelectedRunnersResponse)
async def get_selected_runners(
    event: str = Query(settings.CURRENT_EVENT),
    state: AppState = Depends(get_app_state),
) -> SelectedRunnersResponse:
    """Список отслеживаемых участников."""
    selected = state.selected_runners.get(event, set())
    return SelectedRunnersResponse(
        event=event, selected_ids=list(selected), count=len(selected),
    )


# ============================================================================
# СЕГМЕНТЫ РЕЗУЛЬТАТОВ (SEGMENTS)
# ============================================================================

def _resolve_result_id(runner_id: int) -> Optional[int]:
    """Конвертирует client_id в result_id через БД."""
    from src.analytics.db_connection_optimized import find_result_by_client_id
    result_row = find_result_by_client_id(runner_id)
    if result_row:
        return result_row.get('id') or result_row.get('result_id')
    return int(runner_id)  # fallback: treat as result_id directly


def _build_segments_response(runner_id: int, event: str, segments_data: list, success: bool = True, message: str = None):
    """Собирает SegmentsListResponse из сырых данных БД."""
    segments_models = [
        Segment(
            id=seg.get('id', 0),
            result_id=seg.get('result_id', 0),
            segment_code=seg.get('segment_code', ''),
            sg_time_clear=seg.get('sg_time_clear'),
            sg_pace_avg=seg.get('sg_pace_avg'),
            sg_rank_absolute=seg.get('sg_rank_absolute'),
            sg_rank_sex=seg.get('sg_rank_sex'),
            sg_rank_category=seg.get('sg_rank_category'),
        )
        for seg in segments_data
    ]
    return SegmentsListResponse(
        success=success,
        runner_id=runner_id,
        event=event,
        segments=segments_models,
        count=len(segments_models),
        message=message,
    )


@router.get("/api/runner/{runner_id}/segments")
async def get_runner_segments(
    runner_id: int = PathParam(...),
    event: str = Query(settings.CURRENT_EVENT),
) -> SegmentsListResponse:
    """Все сегменты (контрольные точки) спортсмена."""
    try:
        from src.analytics.db_connection_optimized import get_result_segments
        result_id = _resolve_result_id(runner_id)
        segments_data = get_result_segments(result_id) if result_id else []
        return _build_segments_response(runner_id, event, segments_data)
    except Exception as e:
        logger.error(f"get_runner_segments error: {e}")
        return _build_segments_response(runner_id, event, [], success=False, message=str(e))


@router.get("/api/runner/{runner_id}/latest-segment")
async def get_runner_latest_segment(
    runner_id: int = PathParam(...),
    event: str = Query(settings.CURRENT_EVENT),
) -> SegmentsListResponse:
    """Последний завершённый сегмент спортсмена."""
    try:
        from src.analytics.db_connection_optimized import get_result_segments
        result_id = _resolve_result_id(runner_id)
        segments_data = get_result_segments(result_id) if result_id else []
        last = [segments_data[-1]] if segments_data else []
        return _build_segments_response(runner_id, event, last)
    except Exception as e:
        logger.error(f"get_runner_latest_segment error: {e}")
        return _build_segments_response(runner_id, event, [], success=False, message=str(e))


# ============================================================================
# АНАЛИТИКА (ANALYTICS)
# ============================================================================

@router.get("/api/analytics", response_model=AnalyticsResponse)
async def get_analytics(event: str = Query(settings.CURRENT_EVENT)) -> AnalyticsResponse:
    """Полная аналитика гонки (статы, топ финишёров)."""
    try:
        data = get_formatted_analytics()
        analytics = Analytics(
            event=event,
            timestamp=datetime.now().isoformat(),
            general_stats=data['general_stats'],
            gender_stats={
                'male_count': data['gender_stats']['male_count'],
                'female_count': data['gender_stats']['female_count'],
                'male_avg_time': data['gender_stats'].get('male_avg_time', 'Н/Д'),
                'female_avg_time': data['gender_stats'].get('female_avg_time', 'Н/Д'),
            },
            top_finishers=data['top_finishers'],
        )
        return AnalyticsResponse(success=True, data=analytics)
    except Exception as e:
        logger.error(f"get_analytics error: {e}")
        return AnalyticsResponse(success=False, message=str(e))


@router.post("/api/analytics/refresh")
async def refresh_analytics(event: str = Query(settings.CURRENT_EVENT)):
    """Принудительный пересчёт аналитики."""
    try:
        data = get_formatted_analytics()
        return {'success': True, 'message': 'Analytics refreshed', 'timestamp': datetime.now().isoformat(), 'data': data}
    except Exception as e:
        logger.error(f"refresh_analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/registered-runners", response_model=RegisteredRunnersListResponse)
async def get_registered_runners(
    limit: int = Query(10000, ge=1, le=10000),
    event_name: str = Query("Ночной забег"),
    event_year: int = Query(2026),
) -> RegisteredRunnersListResponse:
    """Зарегистрированные участники из БД, фильтрация по событию и году."""
    try:
        from src.analytics.db_connection_optimized import get_test_table_data
        from src.tracker.models.analytics import RegisteredRunnerInfo

        all_data = await asyncio.get_event_loop().run_in_executor(None, get_test_table_data)

        filtered = [
            r for r in all_data
            if r.get('event_name', event_name) == event_name
            and (lambda y: y == event_year if y else True)(
                int(r['event_year']) if r.get('event_year') else None
            )
        ][:limit]

        def _clean(v):
            if v is None:
                return None
            s = str(v).strip()
            return None if s.lower() in ('null', 'none', '') else s

        runners = []
        for idx, r in enumerate(filtered):
            bday = r.get('birthday', '')
            if bday and hasattr(bday, 'isoformat'):
                bday = bday.isoformat()
            runners.append(RegisteredRunnerInfo(
                id=str(idx + 1),
                name=_clean(r.get('name')) or '',
                surname=_clean(r.get('surname')) or '',
                full_name=f"{r.get('surname', '')} {r.get('name', '')}".strip(),
                category=_clean(r.get('category')),
                city=_clean(r.get('city')),
                sex=_clean(r.get('sex')),
                club=_clean(r.get('club')),
                birthday=str(bday) if bday else '',
                distance=str(r.get('event_distance', r.get('distance', ''))).strip(),
                registration_date=None,
            ))

        return RegisteredRunnersListResponse(total=len(runners), runners=runners)
    except Exception as e:
        logger.error(f"get_registered_runners error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/event-results")
async def get_event_results(
    event_id: int = Query(None, description="ID события в БД"),
    event_name: str = Query(None, description="Название события"),
    year: int = Query(None, description="Год события"),
) -> Response:
    """
    Результаты события из БД с live-позициями участников.

    Примеры:
    - /api/event-results?event_id=104
    - /api/event-results?event_name=Ночной%20забег&year=2026
    """
    import time
    import asyncio
    from src.tracker.services.results_service import (
        build_event_results, _json_cache, _response_cache_ts, RESPONSE_CACHE_TTL
    )
    # Fast path: return pre-serialized JSON without Pydantic validation per-request
    _key = f"{event_id}|{event_name}|{year}"
    if _key in _json_cache and (time.time() - _response_cache_ts.get(_key, 0)) < RESPONSE_CACHE_TTL:
        return Response(content=_json_cache[_key], media_type="application/json")

    # Cache miss or stale: build in thread pool
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, build_event_results, event_id, event_name, year, settings.EVENTS
        )
        return Response(content=_json_cache.get(_key) or result.model_dump_json(), media_type="application/json")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_event_results error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/result-segments", response_model=list)
async def get_result_segments_api(result_id: int = Query(...)) -> list:
    """Сегменты (контрольные точки) для конкретного result_id."""
    try:
        from src.analytics.db_connection_optimized import get_result_segments
        segments = await asyncio.get_event_loop().run_in_executor(
            None, get_result_segments, result_id
        )
        return [dict(s) if not isinstance(s, dict) else s for s in segments]
    except Exception as e:
        logger.error(f"get_result_segments error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/event-segment-codes")
async def get_event_segment_codes_api(event_id: int = Query(...)):
    """Список кодов сегментов для события (упорядочен по маршруту)."""
    try:
        from src.analytics.db_results import get_event_segment_codes
        codes = get_event_segment_codes(event_id)
        return {"codes": codes}
    except Exception as e:
        logger.error(f"get_event_segment_codes error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/event-segment-rankings")
async def get_event_segment_rankings_api(event_id: int = Query(...), segment_code: str = Query(...)):
    """Рейтинг участников по времени на конкретном сегменте маршрута."""
    try:
        from src.analytics.db_results import get_event_segment_rankings
        rows = get_event_segment_rankings(event_id, segment_code)
        return rows
    except Exception as e:
        logger.error(f"get_event_segment_rankings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# СТАТИСТИКА ПО ЗАБЕГАМ (RACE STATS)
# ============================================================================

@router.get("/api/race-stats-db")
async def get_race_stats_db(race_name: str = Query(None)):
    """Статистика по забегу из БД (лучший результат, средний темп, по годам)."""
    try:
        from src.analytics.db_connection_optimized import get_race_stats_from_db as _get_stats
        if not race_name:
            raise HTTPException(status_code=400, detail="race_name обязателен")
        stats = _get_stats(race_name)
        if not stats or not stats.get('distances'):
            raise HTTPException(status_code=404, detail=f"Нет данных для: {race_name}")
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_race_stats_db error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/race-stats")
async def get_race_stats(event_name: str = Query(None)):
    """Статистика по забегу из race_data.json (legacy)."""
    try:
        race_data_path = Path(settings.RACE_DATA_FILE)
        with open(race_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        runners_data = data.get('data', [])
        if event_name:
            runners_data = [r for r in runners_data if r.get('event') == event_name]

        if not runners_data:
            raise HTTPException(
                status_code=404,
                detail=f"Нет данных для: {event_name}" if event_name else "Нет данных"
            )

        def _pace_to_sec(pace_str):
            if not pace_str or isinstance(pace_str, (int, float)):
                return None
            try:
                s = str(pace_str).split('/')[0].strip()
                parts = s.replace('"', '').split("'")
                if len(parts) == 2:
                    return int(parts[0]) * 60 + int(parts[1])
            except Exception:
                pass
            return None

        def _sec_to_pace(sec):
            if not sec:
                return "N/A"
            return f"{int(sec // 60)}'{int(sec % 60):02d}\"/Km"

        finished = [r for r in runners_data if r.get('status') == 'finished' or
                    r.get('times.official_:::finish:::') is not None]
        all_p, male_p, female_p = [], [], []
        best_pace, best_runner = None, None

        for r in finished:
            sec = _pace_to_sec(r.get('intervalaverages_:::full-1:::'))
            if not sec:
                continue
            all_p.append(sec)
            if best_pace is None or sec < best_pace:
                best_pace = sec
                t = r.get('times.official_:::finish:::')
                if t and isinstance(t, (int, float)):
                    ts = t / 1000
                    best_runner = {
                        'full_name': r.get('fullName', ''),
                        'time': f"{int(ts//60)}:{int(ts%60):02d}",
                        'pace': r.get('intervalaverages_:::full-1:::'),
                    }
            g = r.get('gender', '').lower()
            if g in ('male', 'm', 'мужчина'):
                male_p.append(sec)
            elif g in ('female', 'f', 'женщина'):
                female_p.append(sec)

        return {
            'event_name': event_name or 'All',
            'total_runners': len(runners_data),
            'finished_runners': len(finished),
            'best_result': {'runner': best_runner, 'pace': _sec_to_pace(best_pace)} if best_runner else None,
            'average_pace': {
                'all': _sec_to_pace(sum(all_p) / len(all_p) if all_p else None),
                'male': _sec_to_pace(sum(male_p) / len(male_p) if male_p else None),
                'female': _sec_to_pace(sum(female_p) / len(female_p) if female_p else None),
            },
            'statistics': {'male_count': len(male_p), 'female_count': len(female_p)},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_race_stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DATALENS
# ============================================================================

@router.get("/api/datalens-tokens")
async def datalens_tokens(user=Depends(require_auth)):
    """Свежие JWT-токены для DataLens embed. Вызывается клиентом каждые 50 минут."""
    from src.core.datalens import make_embed_token
    if isinstance(user, RedirectResponse):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not settings.DATALENS_KEY_SECRET:
        raise HTTPException(status_code=503, detail="DataLens not configured")
    result = []
    for cfg in settings.DATALENS_EMBEDS:
        token = make_embed_token(cfg["id"], settings.DATALENS_KEY_SECRET)
        embed_type = cfg.get("type", "dash")
        result.append({
            "id": cfg["id"],
            "title": cfg.get("title", ""),
            "url": f"https://datalens.ru/embeds/{embed_type}#dl_embed_token={token}",
        })
    return {"embeds": result}


# ============================================================================
# СИСТЕМНЫЕ ЭНДПОИНТЫ
# ============================================================================

@router.get("/api/status")
async def api_status(state: AppState = Depends(get_app_state)):
    """Статус приложения."""
    return {
        'status': 'ok',
        'event': settings.CURRENT_EVENT,
        'events_loaded': len(settings.EVENTS),
        'cached_routes': len(state.osm_route_data),
        'selected_runners': {k: len(v) for k, v in state.selected_runners.items()},
    }


@router.post("/api/fetch-now")
async def fetch_race_data_now():
    """Ручное получение данных с Copernico API."""
    if not settings.DEBUG_MODE:
        raise HTTPException(status_code=403, detail="Недоступно в production режиме")
    from src.tracker.parsers import fetch_data, save_to_file
    try:
        data = fetch_data()
        if data is not None:
            success = save_to_file(data)
            num = len(data) if isinstance(data, list) else len(data.get('data', []))
            return {"success": success, "records_count": num, "timestamp": datetime.now().isoformat()}
        return {"success": False, "message": "Нет данных от API", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"fetch_race_data_now error: {e}", exc_info=True)
        return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}


# ============================================================================
# SSE ENDPOINTS
# ============================================================================

@router.get("/api/sse/tracker", tags=["SSE"])
async def sse_tracker(request: Request, event_id: int = Query(..., description="ID события")):
    """SSE поток с полными данными трекера. Обновляется каждые 2 сек."""
    queue = await tracker_hub.subscribe(event_id)

    async def stream():
        try:
            yield {"comment": "connected"}
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield {"data": data}
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
                if await request.is_disconnected():
                    break
        finally:
            tracker_hub.unsubscribe(event_id, queue)

    return EventSourceResponse(stream())


@router.get("/api/sse/notify", tags=["SSE"])
async def sse_notify(request: Request):
    """SSE поток лёгких уведомлений: results_updated, startlist_updated."""
    queue = await notification_hub.subscribe()

    async def stream():
        try:
            yield {"comment": "connected"}
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield {"data": data}
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
                if await request.is_disconnected():
                    break
        finally:
            notification_hub.unsubscribe(queue)

    return EventSourceResponse(stream())

@router.get("/api/fetcher-status")
async def fetcher_status():
    """Состояние файла race_data.json."""
    if not settings.DEBUG_MODE:
        raise HTTPException(status_code=403, detail="Недоступно в production режиме")
    try:
        race_data_path = Path(settings.RACE_DATA_FILE)
        if not race_data_path.exists():
            return {"exists": False, "file_path": str(race_data_path)}
        with open(race_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            "exists": True,
            "file_path": str(race_data_path),
            "last_updated": data.get('last_updated', 'Unknown'),
            "records_count": len(data.get('data', [])),
            "file_size_kb": race_data_path.stat().st_size / 1024,
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@router.get("/api/db-debug")
async def database_debug():
    """Отладка: состояние подключения к БД и структура таблиц."""
    if not settings.DEBUG_MODE:
        raise HTTPException(status_code=403, detail="Недоступно в production режиме")
    try:
        from src.analytics.db_connection_optimized import get_database_info_optimized
        debug_info = {
            "db_config": {
                "host": settings.DB_HOST,
                "port": settings.DB_PORT,
                "database": settings.DB_NAME,
                "user": settings.DB_USER,
            },
        }
        debug_info.update(get_database_info_optimized())
        return debug_info
    except Exception as e:
        logger.error(f"database_debug error: {e}", exc_info=True)
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@router.get("/api/db-test-fetch")
async def test_fetch_runners():
    """Тест загрузки участников из БД (первые 10 записей)."""
    if not settings.DEBUG_MODE:
        raise HTTPException(status_code=403, detail="Недоступно в production режиме")
    try:
        from src.analytics.db_connection_optimized import get_test_table_data
        runners = get_test_table_data()
        return {
            "success": True,
            "total_runners": len(runners),
            "sample_runner": runners[0] if runners else None,
            "all_runners": runners[:10],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"test_fetch_runners error: {e}", exc_info=True)
        return {"success": False, "error": str(e), "timestamp": datetime.now().isoformat()}


# ============================================================================
# ADMIN: SERVER METRICS
# ============================================================================

def _get_metrics_collector() -> MetricsCollector:
    import app as _app
    return _app.metrics_collector


@router.get("/api/admin/metrics", tags=["Admin"])
async def get_server_metrics(
    hours: int = Query(default=24, description="Диапазон: 1,6,24,168,720,2160,4320,8760"),
    user=Depends(require_auth),
):
    """История метрик сервера с downsampling по диапазону."""
    import time
    if isinstance(user, RedirectResponse):
        return user
    allowed = {1, 6, 24, 168, 720, 2160, 4320, 8760}
    if hours not in allowed:
        hours = 24
    bucket_secs = hours_to_bucket_secs(hours)
    now = int(time.time())
    since = now - hours * 3600
    collector = _get_metrics_collector()
    points = await asyncio.get_event_loop().run_in_executor(
        None, collector.query, since, now, bucket_secs
    )
    return {
        "points": points,
        "meta": {
            "from_ts": since,
            "to_ts": now,
            "bucket_secs": bucket_secs,
            "hours": hours,
            "uptime_secs": collector.get_uptime_secs(),
        },
    }


@router.get("/api/admin/metrics/live", tags=["Admin"])
async def get_server_metrics_live(
    request: Request,
    user=Depends(require_auth),
):
    """SSE-стрим: новая точка метрик каждые 5 секунд."""
    if isinstance(user, RedirectResponse):
        return user
    collector = _get_metrics_collector()
    queue = collector.subscribe()

    async def stream():
        try:
            yield {"comment": "connected"}
            while True:
                try:
                    point = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"data": json.dumps(point)}
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
                if await request.is_disconnected():
                    break
        finally:
            collector.unsubscribe(queue)

    return EventSourceResponse(stream())
