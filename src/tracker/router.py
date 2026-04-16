"""
API роутеры для трекера маршрутов
Основной модуль с 18+ endpoints для управления гонками и участниками
"""

import logging
import json
from typing import Optional, List
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Query, Request, Depends, HTTPException, Path as PathParam
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.core.state import AppState
from src.core.dependencies import get_app_state, get_event
from src.tracker.models import (
    RunnerSelectionRequest, SelectedRunnersResponse,
    RaceConfig,
    CurrentEventResponse, EventsListResponse, EventInfo,
    Analytics, AnalyticsResponse, RegisteredRunnersListResponse, RaceResultsResponse,
    Segment, SegmentsListResponse,
)
from src.tracker.services import (
    get_formatted_analytics,
)

logger = logging.getLogger(__name__)

# Создать роутер
router = APIRouter(prefix="", tags=["tracker"])

# Кэш исторических данных (прошлый год): заполняется один раз при первом запросе
_hist_cache: dict = {}

# Подключить шаблоны (реэкспорт из app.py)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================================
# СТРАНИЦЫ (HTML)
# ============================================================================

@router.get("/", response_class=HTMLResponse, tags=["Pages"])
async def root(request: Request):
    """Главная страница приложения - перенаправление на трекер"""
    return await tracker_main(request)


@router.get("/tracker", response_class=HTMLResponse, tags=["Pages"])
async def tracker_redirect(request: Request):
    """Перенаправление на главную трекера"""
    return await tracker_main(request)


@router.get("/tracker/{event:path}", response_class=HTMLResponse, tags=["Pages"])
async def tracker_event(request: Request, event: str):
    """Страница трекера для конкретного события"""
    # Валидируем событие
    if event not in settings.EVENTS_CONFIG:
        logger.warning(f"Invalid event: {event}")
        event = settings.CURRENT_EVENT
    
    context = {
        "request": request,
        "event": event,
        "events": list(settings.EVENTS_CONFIG.keys()),
    }
    return templates.TemplateResponse("tracker.html", context)


async def tracker_main(request: Request):
    """Главная страница трекера"""
    context = {
        "request": request,
        "event": settings.CURRENT_EVENT,
        "events": list(settings.EVENTS_CONFIG.keys()),
    }
    return templates.TemplateResponse("tracker.html", context)


@router.get("/analytics", response_class=HTMLResponse, tags=["Pages"])
async def analytics_page(request: Request):
    """Страница аналитики (перенаправлено на /start_list для обратной совместимости)"""
    # Для совместимости перенаправляем старый маршрут на новый
    context = {
        "request": request,
        "event": settings.CURRENT_EVENT,
    }
    return templates.TemplateResponse("start_list.html", context)


@router.get("/start_list", response_class=HTMLResponse, tags=["Pages"])
async def start_list_page(request: Request):
    """Страница стартового списка"""
    context = {
        "request": request,
        "event": settings.CURRENT_EVENT,
    }
    return templates.TemplateResponse("start_list.html", context)


@router.get("/results", response_class=HTMLResponse, tags=["Pages"])
async def results_page(request: Request):
    """Страница результатов забега"""
    context = {
        "request": request,
        "event": settings.CURRENT_EVENT,
    }
    return templates.TemplateResponse("results.html", context)


# ============================================================================
# СОБЫТИЯ (EVENTS)
# ============================================================================

@router.get("/api/current-event", response_model=CurrentEventResponse, tags=["Events"])
async def get_current_event() -> CurrentEventResponse:
    """Получить текущее активное событие"""
    event_id = settings.CURRENT_EVENT
    config = settings.EVENTS_CONFIG.get(event_id)
    
    if not config:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not configured")
    
    return CurrentEventResponse(
        event=event_id,
        storage_key=f"{event_id}_selected_runners",
        name=config.get('name', event_id),
        title=config.get('title', event_id),
        description=config.get('description', ''),
        route_type='shuttle' if event_id != 'rosneft' else 'loop',
    )


@router.get("/api/events", response_model=EventsListResponse, tags=["Events"])
async def get_events() -> EventsListResponse:
    """Получить список всех доступных событий"""
    events_list = []
    
    for event_id, config in settings.EVENTS_CONFIG.items():
        event_info = {
            "id": event_id,
            "name": config.get('name', event_id),
            "title": config.get('title', event_id),
            "way_id": config.get('osm_way_id', 0),
            "distance": config.get('total_race_km', 0),
        }
        events_list.append(event_info)
    
    return EventsListResponse(
        events=events_list,
        current=settings.CURRENT_EVENT,
    )


# ============================================================================
# УЧАСТНИКИ (RUNNERS)
# ============================================================================

@router.get("/api/search-athletes", tags=["Athletes"])
async def search_athletes(
    q: str = Query("", min_length=1, description="Search query (surname or name)"),
):
    """
    Поиск спортсменов в таблице 'clients' по фамилии и имени
    Возвращает: фамилия, имя, город
    """
    try:
        from src.analytics.db_connection_optimized import search_clients_optimized
        
        results = search_clients_optimized(q)
        
        return {
            'query': q,
            'count': len(results),
            'results': results[:20],  # Ограничиваем до 20 результатов
        }
    
    except Exception as e:
        logger.error(f"Error searching athletes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/athlete/{surname}/{name}", tags=["Athletes"])
async def get_athlete_profile(
    surname: str = PathParam(..., description="Фамилия спортсмена"),
    name: str = PathParam(..., description="Имя спортсмена"),
):
    """
    Получить информацию о спортсмене и его все результаты
    
    Args:
        surname: Фамилия спортсмена
        name: Имя спортсмена
    
    Returns:
        Информация о спортсмене и список его результатов
    """
    try:
        from src.analytics.db_connection_optimized import get_athlete_results_optimized
        
        logger.info(f"📥 Запрос профиля спортсмена: {surname} {name}")
        
        athlete_info, results = get_athlete_results_optimized(surname, name)
        
        logger.info(f"📊 Получено: athlete_info={'OK' if athlete_info else 'EMPTY'}, results={len(results)} items")
        
        if not athlete_info and not results:
            logger.warning(f"❌ Спортсмен не найден: {surname} {name}")
            raise HTTPException(
                status_code=404, 
                detail=f"Спортсмен {surname} {name} не найден в базе данных"
            )
        
        # Форматируем результаты для фронтенда
        formatted_results = []
        for result in results:
            # Преобразуем сложные типы данных в строки для JSON
            formatted_result = {}
            for key, value in result.items():
                if hasattr(value, 'isoformat'):  # datetime объекты
                    formatted_result[key] = value.isoformat()
                elif isinstance(value, (int, float, str, bool, type(None))):
                    formatted_result[key] = value
                else:
                    formatted_result[key] = str(value)
            formatted_results.append(formatted_result)
        
        # Форматируем информацию о спортсмене
        formatted_athlete_info = {}
        for key, value in athlete_info.items():
            if hasattr(value, 'isoformat'):  # datetime объекты
                formatted_athlete_info[key] = value.isoformat()
            elif isinstance(value, (int, float, str, bool, type(None))):
                formatted_athlete_info[key] = value
            else:
                formatted_athlete_info[key] = str(value)
        
        logger.info(f"✅ Успешно вернул результат: {formatted_athlete_info.get('name', '?')} {formatted_athlete_info.get('surname', '?')} - {len(formatted_results)} гонок")
        
        return {
            'athlete': formatted_athlete_info,
            'results': formatted_results,
            'total_races': len(formatted_results),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка при получении профиля спортсмена {surname} {name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")


@router.post("/api/select-runner", response_model=SelectedRunnersResponse, tags=["Runners"])
async def select_runner(
    request: RunnerSelectionRequest,
    event: str = Query(settings.CURRENT_EVENT),
    state: AppState = Depends(get_app_state),
) -> SelectedRunnersResponse:
    """
    Добавить участника в список отслеживания
    """
    if event not in state.selected_runners:
        state.selected_runners[event] = set()
    
    state.selected_runners[event].add(request.runner_id)
    
    # Ограничиваем максимальное количество
    if len(state.selected_runners[event]) > settings.MAX_SELECTED_RUNNERS:
        # Удаляем старый элемент
        state.selected_runners[event].pop()
    
    return SelectedRunnersResponse(
        event=event,
        selected_ids=list(state.selected_runners[event]),
        count=len(state.selected_runners[event]),
    )


@router.post("/api/deselect-runner", response_model=SelectedRunnersResponse, tags=["Runners"])
async def deselect_runner(
    request: RunnerSelectionRequest,
    event: str = Query(settings.CURRENT_EVENT),
    state: AppState = Depends(get_app_state),
) -> SelectedRunnersResponse:
    """
    Удалить участника из списка отслеживания
    """
    if event in state.selected_runners:
        state.selected_runners[event].discard(request.runner_id)
    
    return SelectedRunnersResponse(
        event=event,
        selected_ids=list(state.selected_runners.get(event, set())),
        count=len(state.selected_runners.get(event, set())),
    )


@router.get("/api/selected-runners", response_model=SelectedRunnersResponse, tags=["Runners"])
async def get_selected_runners(
    event: str = Query(settings.CURRENT_EVENT),
    state: AppState = Depends(get_app_state),
) -> SelectedRunnersResponse:
    """
    Получить список отслеживаемых участников
    """
    selected = state.selected_runners.get(event, set())
    
    return SelectedRunnersResponse(
        event=event,
        selected_ids=list(selected),
        count=len(selected),
    )


# ============================================================================
# СЕГМЕНТЫ РЕЗУЛЬТАТОВ (SEGMENTS)
# ============================================================================

@router.get("/api/runner/{runner_id}/segments", tags=["Segments"])
async def get_runner_segments(
    runner_id: int = PathParam(..., description="ID спортсмена (client_id)"),
    event: str = Query(settings.CURRENT_EVENT, description="Event ID"),
) -> SegmentsListResponse:
    """
    Получить список сегментов (контрольных точек) спортсмена.
    
    Используется трекером для отслеживания прохождения контрольных точек (kt1, kt2, и т.д.)
    и динамической корректировки темпа при достижении каждой точки.
    
    Args:
        runner_id: ID спортсмена (client_id из таблицы results)
        event: ID события (например, 'night_run')
    
    Returns:
        SegmentsListResponse с списком пройденных сегментов и их метриками
    """
    try:
        from src.analytics.db_connection_optimized import get_result_segments, find_result_by_client_id

        # Лог входящего идентификатора
        settings.logger.info(f"[segments] requested runner_id={runner_id} event={event}")

        # Если передан client_id, пытаемся найти соответствующий result_id
        # get_result_segments ожидает result_id (id из таблицы results)
        result_row = find_result_by_client_id(runner_id)
        if not result_row:
            # Попробуем ещё как числовой result_id
            try:
                numeric_result_id = int(runner_id)
            except Exception:
                numeric_result_id = None

            if numeric_result_id:
                result_id = numeric_result_id
            else:
                return SegmentsListResponse(
                    success=True,
                    runner_id=runner_id,
                    event=event,
                    segments=[],
                    count=0,
                )
        else:
            result_id = result_row.get('id') or result_row.get('result_id') or None

        if not result_id:
            return SegmentsListResponse(
                success=True,
                runner_id=runner_id,
                event=event,
                segments=[],
                count=0,
            )

        settings.logger.info(f"[segments] resolved result_id={result_id} for runner_id={runner_id}")

        # Получаем сегменты спортсмена по result_id
        segments_data = get_result_segments(result_id)
        settings.logger.info(f"[segments] found {len(segments_data) if segments_data else 0} segments for result_id={result_id}")
        
        # Преобразуем в Pydantic модели
        segments_models = []
        for seg in segments_data:
            segment = Segment(
                id=seg.get('id', 0),
                result_id=seg.get('result_id', 0),
                segment_code=seg.get('segment_code', ''),
                sg_time_clear=seg.get('sg_time_clear'),
                sg_pace_avg=seg.get('sg_pace_avg'),
                sg_rank_absolute=seg.get('sg_rank_absolute'),
                sg_rank_sex=seg.get('sg_rank_sex'),
                sg_rank_category=seg.get('sg_rank_category'),
            )
            segments_models.append(segment)
        
        return SegmentsListResponse(
            success=True,
            runner_id=runner_id,
            event=event,
            segments=segments_models,
            count=len(segments_models),
        )
    
    except Exception as e:
        logger.error(f"Error getting segments for runner {runner_id}: {e}")
        return SegmentsListResponse(
            success=False,
            runner_id=runner_id,
            event=event,
            segments=[],
            count=0,
            message=str(e),
        )


@router.get("/api/runner/{runner_id}/latest-segment", tags=["Segments"])
async def get_runner_latest_segment(
    runner_id: int = PathParam(..., description="ID спортсмена (client_id)"),
    event: str = Query(settings.CURRENT_EVENT, description="Event ID"),
) -> SegmentsListResponse:
    """
    Получить ПОСЛЕДНИЙ завершённый сегмент спортсмена.
    
    Используется для отслеживания текущего положения спортсмена на маршруте
    и определения необходимости смены направления движения маркера.
    
    Args:
        runner_id: ID спортсмена
        event: ID события
    
    Returns:
        SegmentsListResponse с одним последним сегментом (если есть)
    """
    try:
        from src.analytics.db_connection_optimized import get_result_segments, find_result_by_client_id

        settings.logger.info(f"[latest-segment] requested runner_id={runner_id} event={event}")

        # Аналогично: сначала конвертируем client_id в result_id
        result_row = find_result_by_client_id(runner_id)
        if not result_row:
            try:
                numeric_result_id = int(runner_id)
            except Exception:
                numeric_result_id = None

            if numeric_result_id:
                result_id = numeric_result_id
            else:
                return SegmentsListResponse(
                    success=True,
                    runner_id=runner_id,
                    event=event,
                    segments=[],
                    count=0,
                )
        else:
            result_id = result_row.get('id') or result_row.get('result_id') or None

        if not result_id:
            return SegmentsListResponse(
                success=True,
                runner_id=runner_id,
                event=event,
                segments=[],
                count=0,
            )

        settings.logger.info(f"[latest-segment] resolved result_id={result_id} for runner_id={runner_id}")

        # Получаем все сегменты и берём последний
        segments_data = get_result_segments(result_id)
        settings.logger.info(f"[latest-segment] found {len(segments_data) if segments_data else 0} segments for result_id={result_id}")
        
        if not segments_data:
            return SegmentsListResponse(
                success=True,
                runner_id=runner_id,
                event=event,
                segments=[],
                count=0,
            )
        
        # Берём последний сегмент (последний в массиве)
        latest_seg_data = segments_data[-1]
        
        segment = Segment(
            id=latest_seg_data.get('id', 0),
            result_id=latest_seg_data.get('result_id', 0),
            segment_code=latest_seg_data.get('segment_code', ''),
            sg_time_clear=latest_seg_data.get('sg_time_clear'),
            sg_pace_avg=latest_seg_data.get('sg_pace_avg'),
            sg_rank_absolute=latest_seg_data.get('sg_rank_absolute'),
            sg_rank_sex=latest_seg_data.get('sg_rank_sex'),
            sg_rank_category=latest_seg_data.get('sg_rank_category'),
        )
        
        return SegmentsListResponse(
            success=True,
            runner_id=runner_id,
            event=event,
            segments=[segment],
            count=1,
        )
    
    except Exception as e:
        logger.error(f"Error getting latest segment for runner {runner_id}: {e}")
        return SegmentsListResponse(
            success=False,
            runner_id=runner_id,
            event=event,
            segments=[],
            count=0,
            message=str(e),
        )


# ============================================================================
# КОНФИГУРАЦИЯ ГОНКИ (RACE CONFIG)
# ============================================================================

@router.get("/api/race-config", response_model=RaceConfig, tags=["Config"])
async def get_race_config(
    event: str = Query(settings.CURRENT_EVENT),
) -> RaceConfig:
    """
    Получить конфигурацию гонки (контрольные точки, дистанция)
    """
    if event not in settings.EVENTS_CONFIG:
        raise HTTPException(status_code=404, detail=f"Event '{event}' not found")
    
    config = settings.EVENTS_CONFIG[event]
    route_type = 'shuttle' if event != 'rosneft' else 'loop'
    
    return RaceConfig(
        total_distance=config.get('total_race_km', 0),
        event_name=config.get('name', event),
        event_id=event,
        route_type=route_type,
        one_way_length=config.get('one_way_length_km'),
        laps=config.get('laps'),
        lap_length=config.get('distances', {}).get(f"{config.get('total_race_km')}km", {}).get('lap_length'),
        checkpoints=[],
    )


# ============================================================================
# АНАЛИТИКА (ANALYTICS)
# ============================================================================

@router.get("/api/analytics", response_model=AnalyticsResponse, tags=["Analytics"])
async def get_analytics(
    event: str = Query(settings.CURRENT_EVENT),
) -> AnalyticsResponse:
    """
    Получить полную аналитику гонки
    - Общая статистика (всего, бегут, финишировали)
    - Статистика по полам
    - Топ 3 финишёров в целом, среди мужчин, среди женщин
    """
    try:
        analytics_data = get_formatted_analytics()
        
        analytics = Analytics(
            event=event,
            timestamp=datetime.now().isoformat(),
            general_stats={
                'total_runners': analytics_data['general_stats']['total_runners'],
                'not_started': analytics_data['general_stats']['not_started'],
                'on_track': analytics_data['general_stats']['on_track'],
                'finished': analytics_data['general_stats']['finished'],
            },
            gender_stats={
                'male_count': analytics_data['gender_stats']['male_count'],
                'female_count': analytics_data['gender_stats']['female_count'],
                'male_avg_time': analytics_data['gender_stats'].get('male_avg_time', 'Н/Д'),
                'female_avg_time': analytics_data['gender_stats'].get('female_avg_time', 'Н/Д'),
            },
            top_finishers={
                'overall': analytics_data['top_finishers']['overall'],
                'male': analytics_data['top_finishers']['male'],
                'female': analytics_data['top_finishers']['female'],
            },
        )
        
        return AnalyticsResponse(success=True, data=analytics)
    
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        return AnalyticsResponse(
            success=False,
            message=str(e),
        )


@router.post("/api/analytics/refresh", tags=["Analytics"])
async def refresh_analytics(
    event: str = Query(settings.CURRENT_EVENT),
):
    """
    Пересчитать аналитику (силовой рефреш)
    """
    try:
        # Пересчитываем аналитику
        analytics_data = get_formatted_analytics()
        
        return {
            'success': True,
            'message': 'Analytics refreshed',
            'timestamp': datetime.now().isoformat(),
            'data': analytics_data,
        }
    except Exception as e:
        logger.error(f"Error refreshing analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/registered-runners", response_model=RegisteredRunnersListResponse, tags=["Analytics"])
async def get_registered_runners(
    limit: int = Query(10000, ge=1, le=10000),
    event_name: str = Query("Ночной забег"),
    event_year: int = Query(2026),
) -> RegisteredRunnersListResponse:
    """
    Получить список зарегистрированных участников из БД MySQL
    Интегрирована работа с базой данных через db_connection модуль
    
    Фильтры:
    - event_name: "Ночной забег" (по умолчанию)
    - event_year: 2026 (по умолчанию)
    """
    try:
        from src.analytics.db_connection_optimized import get_test_table_data
        from src.tracker.models.analytics import RegisteredRunnerInfo
        
        logger.info(f"Fetching registered runners (limit: {limit}, event_name: {event_name}, event_year: {event_year})")
        
        # Получаем данные из БД (или тестовые, если БД недоступна)
        all_runners_data = get_test_table_data()
        
        # Применяем фильтры: event_name и event_year
        filtered_runners = []
        for runner_data in all_runners_data:
            # Проверяем фильтры event_name и event_year если они присутствуют в БД
            if 'event_name' in runner_data:
                if runner_data.get('event_name') != event_name:
                    continue
            
            if 'event_year' in runner_data:
                try:
                    runner_year = int(runner_data.get('event_year', 0))
                    if runner_year != event_year:
                        continue
                except (ValueError, TypeError):
                    pass
            
            filtered_runners.append(runner_data)
        
        # Применяем лимит если нужно
        if limit and len(filtered_runners) > limit:
            filtered_runners = filtered_runners[:limit]
        
        # Преобразуем в список объектов RegisteredRunnerInfo
        runners: List[RegisteredRunnerInfo] = []
        for idx, runner_data in enumerate(filtered_runners):
            full_name = f"{runner_data.get('surname', '')} {runner_data.get('name', '')}".strip()
            
            # Конвертируем birthday в строку (может быть datetime.date или строка)
            birthday = runner_data.get('birthday', '')
            if birthday and hasattr(birthday, 'isoformat'):
                birthday = birthday.isoformat()  # datetime.date -> строка "YYYY-MM-DD"
            birthday = str(birthday) if birthday else ''
            
            # Получаем дистанцию из БД
            distance = str(runner_data.get('event_distance', runner_data.get('distance', ''))).strip()
            
            # Вспомогательная функция для очистки null значений
            def clean_null_value(value):
                if value is None:
                    return None
                value_str = str(value).strip() if value else ''
                if value_str.lower() in ('null', 'none', ''):
                    return None
                return value_str
            
            runner_info = RegisteredRunnerInfo(
                id=str(idx + 1),
                name=clean_null_value(runner_data.get('name')),
                surname=clean_null_value(runner_data.get('surname')),
                full_name=full_name,
                category=clean_null_value(runner_data.get('category')),
                city=clean_null_value(runner_data.get('city')),
                sex=clean_null_value(runner_data.get('sex')),
                club=clean_null_value(runner_data.get('club')),
                birthday=birthday,
                distance=distance,
                registration_date=None,  # Может быть добавлено из БД если есть
            )
            runners.append(runner_info)
        
        logger.info(f"Successfully fetched {len(runners)} registered runners from database (filtered: {event_name}, {event_year})")
        
        return RegisteredRunnersListResponse(
            total=len(runners),
            runners=runners,
        )
    except Exception as e:
        logger.error(f"Error getting registered runners from database: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/api/event-results", response_model=RaceResultsResponse, tags=["Analytics"])
async def get_event_results(
    event_id: int = Query(None, description="ID события в БД"),
    event_name: str = Query(None, description="Название события"),
    year: int = Query(None, description="Год события"),
) -> RaceResultsResponse:
    """
    Получить результаты события из БД по event_id или по названию и году
    
    Examples:
    - /api/event-results?event_id=67
    - /api/event-results?event_name=Ночной%20забег&year=2025
    """
    try:
        import json as _json
        from datetime import date as _date, timedelta as _td
        from src.analytics.db_connection_optimized import (
            get_race_results_by_event_id,
            get_race_results_by_event_id_and_year,
            get_event_info_by_id,
            get_event_info,
            get_category_avg_paces,
            get_prev_year_results,
        )
        from src.tracker.services.runners_service import calculate_live_position
        from src.tracker.services.pace_calculator import parse_pace_to_kmh

        results_data = []

        # Получаем результаты по event_id или по названию и году
        if event_id:
            logger.info(f"Загрузка результатов для event_id={event_id}")
            results_data = get_race_results_by_event_id(event_id)
        elif event_name and year:
            logger.info(f"Загрузка результатов для {event_name} {year}")
            results_data = get_race_results_by_event_id_and_year(event_name, year)
        else:
            raise HTTPException(
                status_code=400,
                detail="Укажите event_id или event_name + year"
            )

        # Получаем данные события для расчёта live-скоростей (один раз на запрос)
        current_year = datetime.now().year
        if event_id:
            ev_info = get_event_info_by_id(event_id)
        else:
            ev_info = get_event_info(event_name, year or current_year)

        race_date = ev_info.get('event_date') or _date.today()
        ev_name = ev_info.get('event_name', event_name or '')
        ev_distance = ev_info.get('event_distance')
        ev_year = ev_info.get('event_year', current_year)

        raw_cp = ev_info.get('checkpoint_distances')
        if raw_cp:
            checkpoint_distances = (
                [float(x) for x in raw_cp]
                if isinstance(raw_cp, list)
                else [float(x) for x in _json.loads(raw_cp)]
            )
        else:
            total_km = float(ev_distance) if ev_distance else 5.0
            checkpoint_distances = [0.0, total_km]

        category_speeds = get_category_avg_paces(ev_name, ev_distance, ev_year) if ev_name else {}

        # --- Исторические данные для первого участка (кэш на весь процесс) ---
        cache_key = f"{ev_name}|{ev_distance}|{ev_year}"
        if cache_key not in _hist_cache:
            prev_year = (ev_year or current_year) - 1
            prev_rows = get_prev_year_results(ev_name, ev_distance, prev_year) if ev_name else []
            personal: dict = {}
            cat_raw: dict = {}
            for row in prev_rows:
                bday = row.get('birthday')
                bday_str = bday.isoformat() if hasattr(bday, 'isoformat') else str(bday or '')
                key = f"{(row.get('surname') or '').strip()}|{(row.get('name') or '').strip()}|{bday_str}".upper()
                pace_val = row.get('finish_pace_avg_clean')
                if isinstance(pace_val, _td):
                    _s = int(pace_val.total_seconds())
                    pace_val = f"{_s // 60}:{_s % 60:02d}"
                spd = parse_pace_to_kmh(str(pace_val) if pace_val else '')
                if spd > 0:
                    personal[key] = spd
                # Нормализуем категорию: убираем суффикс с годами рождения "(1976 г.р. и младше)"
                cat = (row.get('category') or '').strip().split(' (')[0].strip()
                if cat and spd > 0:
                    cat_raw.setdefault(cat, []).append(spd)
            _hist_cache[cache_key] = {
                'personal': personal,
                'category_avg': {c: sum(v) / len(v) for c, v in cat_raw.items()},
                'prev_year': prev_year,
            }
            logger.info(f"Исторические данные загружены: {len(personal)} личных, {len(cat_raw)} категорий за {prev_year} год")
        hist_data = _hist_cache[cache_key]

        logger.info(
            f"hist_data: personal={len(hist_data['personal'])}, "
            f"categories={list(hist_data['category_avg'].keys())[:5]}, "
            f"prev_year={hist_data['prev_year']}"
        )

        # Преобразуем результаты в нужный формат
        results = []
        _debug_count = 0
        for runner in results_data:
            # Исторический темп для первого участка
            bday = runner.get('birthday')
            bday_str = bday.isoformat() if hasattr(bday, 'isoformat') else str(bday or '')
            runner_key = f"{(runner.get('surname') or '').strip()}|{(runner.get('name') or '').strip()}|{bday_str}".upper()
            if runner_key in hist_data['personal']:
                r_hist_speed = hist_data['personal'][runner_key]
                r_hist_source = 'personal'
            elif (runner.get('category') or '').strip().split(' (')[0].strip() in hist_data['category_avg']:
                r_hist_speed = hist_data['category_avg'][(runner.get('category') or '').strip().split(' (')[0].strip()]
                r_hist_source = 'category'
            else:
                r_hist_speed = None
                r_hist_source = None

            # Рассчитываем live-скорость и дистанцию
            try:
                speed_kmh, current_dist, pace_str = calculate_live_position(
                    runner, checkpoint_distances, race_date, category_speeds,
                    hist_speed=r_hist_speed,
                )
            except Exception as _e:
                logger.warning(f"calculate_live_position error for runner {runner.get('id')}: {_e}")
                speed_kmh, current_dist, pace_str = 10.0, 0.0, "6:00"

            # Источник темпа: только для участников до первой КТ
            if runner.get('time_clear_finish') or runner.get('time_clear_kt1'):
                pace_source = ''
            else:
                pace_source = r_hist_source or ''
                if _debug_count < 20 and runner.get('race_status') == 'Running':
                    logger.info(
                        f"[DEBUG] #{runner.get('start_number')} {runner.get('surname')} {runner.get('name')}: "
                        f"cat='{(runner.get('category') or '').split(' (')[0]}' "
                        f"hist={f'{r_hist_speed:.2f}' if r_hist_speed else 'None'} ({r_hist_source}), "
                        f"speed={speed_kmh:.2f}, pace={pace_str}"
                    )
                    _debug_count += 1

            result_item = {
                'id': runner.get('id') or runner.get('client_id'),
                'start_number': runner.get('start_number'),
                'surname': runner.get('surname', ''),
                'name': runner.get('name', ''),
                'full_name': f"{runner.get('surname', '')} {runner.get('name', '')}".strip(),
                'sex': runner.get('sex'),
                'category': runner.get('category'),
                'birthday': runner.get('birthday'),
                'race_status': runner.get('race_status'),
                'status': runner.get('race_status'),
                'rank_absolute': runner.get('rank_absolute'),
                'rank_sex': runner.get('rank_sex'),
                'rank_category': runner.get('rank_category'),
                'rank_absolute_clean': runner.get('rank_absolute_clean'),
                'rank_sex_clean': runner.get('rank_sex_clean'),
                'rank_category_clean': runner.get('rank_category_clean'),
                'time_gun_finish': runner.get('time_gun_finish'),
                'time_clear_finish': runner.get('time_clear_finish'),
                'finish_pace_avg': runner.get('finish_pace_avg'),
                # Добавляем дистанцию от события
                'distance': runner.get('distance', runner.get('distance_from_event', '5 км')),
                'event': runner.get('distance', runner.get('distance_from_event', '5 км')),
                'checkpoints': {
                    'kt1': {
                        'time': runner.get('time_clear_kt1'),
                        'pace': runner.get('pace_avg_kt1')
                    },
                    'kt2': {
                        'time': runner.get('time_clear_kt2'),
                        'pace': runner.get('pace_avg_kt2')
                    },
                    'kt3': {
                        'time': runner.get('time_clear_kt3'),
                        'pace': runner.get('pace_avg_kt3')
                    },
                    'kt4': {
                        'time': runner.get('time_clear_kt4'),
                        'pace': runner.get('pace_avg_kt4')
                    },
                    'kt5': {
                        'time': runner.get('time_clear_kt5'),
                        'pace': runner.get('pace_avg_kt5')
                    }
                },
                # Live-данные для анимации маркера
                'speed': round(speed_kmh, 2),
                'current_distance': round(current_dist, 3),
                'current_pace': pace_str,
                'pace_source': pace_source,
                'prev_year': hist_data['prev_year'],
            }
            results.append(result_item)
        
        return RaceResultsResponse(
            event=event_name or f"event_{event_id}",
            total_results=len(results_data),
            results=results,
            timestamp=datetime.now().isoformat(),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting event results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/result-segments", response_model=list, tags=["Analytics"])
async def get_result_segments_api(result_id: int = Query(..., description="ID результата")) -> list:
    """
    Получить сегменты (контрольные точки) для конкретного результата
    
    Returns список сегментов с данными:
    - id: ID сегмента
    - result_id: ID результата
    - segment_code: Код сегмента (напр. 'start-kt1', 'kt1-kt2', 'kt1-finish')
    - sg_time_clear: Время преодоления участка
    - sg_pace_avg: Средний темп на участке (мин/км)
    - sg_rank_absolute: Позиция в абсолюте
    - sg_rank_sex: Позиция по полу
    - sg_rank_category: Позиция по возрастной категории
    
    Examples:
    - /api/result-segments?result_id=716
    """
    try:
        from src.analytics.db_connection_optimized import get_result_segments
        
        logger.info(f"Загрузка сегментов для result_id={result_id}")
        segments = get_result_segments(result_id)
        
        # Преобразуем в список словарей для сериализации
        result = []
        for segment in segments:
            if isinstance(segment, dict):
                result.append(segment)
            else:
                # Если это объект, конвертируем в словарь
                result.append(dict(segment))
        
        logger.info(f"✅ Получено {len(result)} сегментов для result_id={result_id}")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка получения сегментов результата: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка получения сегментов: {str(e)}")


# ============================================================================
# СТАТИСТИКА ПО ЗАБЕГАМ / СОБЫТИЯМ
# ============================================================================

@router.get("/api/race-stats-db", tags=["Race Analysis"])
async def get_race_stats_from_db(
    race_name: str = Query(None, description="Название забега"),
):
    """
    Получить статистику по забегу из БД MySQL:
    - Лучший результат (время и темп)
    - Средний темп всех участников
    - Средний темп мужчин и женщин
    - Распределение участников по годам (для графика)
    """
    try:
        from src.analytics.db_connection_optimized import get_race_stats_from_db as get_stats
        
        if not race_name:
            raise HTTPException(status_code=400, detail="race_name parameter is required")
        
        # Получаем статистику из БД
        stats = get_stats(race_name)
        
        if not stats or not stats.get('years_data'):
            raise HTTPException(
                status_code=404,
                detail=f"No race data found for event: {race_name}"
            )
        
        return stats
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting race stats from DB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/race-stats", tags=["Race Analysis"])
async def get_race_stats(
    event_name: str = Query(None, description="Название события (например, '7 km', '5 km')"),
):
    """
    Получить статистику по забегу:
    - Название и距离
    - Лучший результат (время и темп)
    - Средний темп всех участников
    - Средний темп мужчин
    - Средний темп женщин
    - Распределение участников по статусам
    """
    try:
        # Загружаем данные из race_data.json
        race_data_path = Path(settings.RACE_DATA_FILE)
        with open(race_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        runners_data = data.get('data', [])
        
        # Фильтруем по типу события
        if event_name:
            runners_data = [r for r in runners_data if r.get('event') == event_name]
        
        if not runners_data:
            raise HTTPException(
                status_code=404,
                detail=f"No runners found for event: {event_name}" if event_name else "No runners found"
            )
        
        # Вспомогательная функция для парсинга времени из формата минуты'секунды"
        def parse_pace_to_seconds(pace_str):
            """Парсит строку вида '4\'22\"/Km' в количество секунд на км"""
            if not pace_str or isinstance(pace_str, (int, float)):
                return None
            try:
                # pace_str формат: "4'22\"/Km" -> 4 минуты 22 секунды на км
                pace_str = str(pace_str).strip()
                # Удаляем '/Km' и другие суффиксы
                pace_str = pace_str.split('/')[0].strip()
                # Разбираем минуты и секунды
                parts = pace_str.replace('"', '').split("'")
                if len(parts) == 2:
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    return minutes * 60 + seconds
            except:
                pass
            return None
        
        # Вспомогательная функция для преобразования секунд в строку мин/км
        def seconds_to_pace_string(seconds):
            """Преобразует секунды в строку типа '4\'22\"/Km'"""
            if not seconds:
                return "N/A"
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}'{secs:02d}\"/Km"
        
        # Парсим данные участников
        male_paces = []
        female_paces = []
        all_paces = []
        best_pace = None
        best_runner = None
        
        finished_runners = [r for r in runners_data if r.get('status') == 'finished' or 
                           r.get('times.official_:::finish:::') is not None]
        
        for runner in finished_runners:
            pace_str = runner.get('intervalaverages_:::full-1:::')
            pace_seconds = parse_pace_to_seconds(pace_str)
            
            if pace_seconds:
                all_paces.append(pace_seconds)
                
                # Отслеживаем лучший результат
                if best_pace is None or pace_seconds < best_pace:
                    best_pace = pace_seconds
                    # Вычисляем время финиша в минутах
                    official_time = runner.get('times.official_:::finish:::')
                    if official_time and isinstance(official_time, (int, float)):
                        finish_time_seconds = official_time / 1000  # конвертируем из мс
                        finish_minutes = int(finish_time_seconds / 60)
                        finish_secs = int(finish_time_seconds % 60)
                        best_runner = {
                            'name': runner.get('name', ''),
                            'surname': runner.get('surname', ''),
                            'full_name': runner.get('fullName', ''),
                            'gender': runner.get('gender', ''),
                            'time': f"{finish_minutes}:{finish_secs:02d}",
                            'pace': pace_str,
                        }
                
                # Разделяем по полам
                gender = runner.get('gender', '').lower()
                if gender in ['male', 'm', 'мужчина']:
                    male_paces.append(pace_seconds)
                elif gender in ['female', 'f', 'женщина']:
                    female_paces.append(pace_seconds)
        
        # Вычисляем средние темпы
        avg_pace = sum(all_paces) / len(all_paces) if all_paces else None
        male_avg_pace = sum(male_paces) / len(male_paces) if male_paces else None
        female_avg_pace = sum(female_paces) / len(female_paces) if female_paces else None
        
        # Формируем ответ
        response = {
            'event_name': event_name or 'All Events',
            'total_runners': len(runners_data),
            'finished_runners': len(finished_runners),
            'running_runners': sum(1 for r in runners_data if r.get('status') == 'running'),
            'not_started_runners': sum(1 for r in runners_data if r.get('status') == 'notstarted'),
            'best_result': {
                'runner': best_runner,
                'pace': seconds_to_pace_string(best_pace) if best_pace else 'N/A',
            } if best_runner else None,
            'average_pace': {
                'all': seconds_to_pace_string(avg_pace) if avg_pace else 'N/A',
                'male': seconds_to_pace_string(male_avg_pace) if male_avg_pace else 'N/A',
                'female': seconds_to_pace_string(female_avg_pace) if female_avg_pace else 'N/A',
            },
            'statistics': {
                'male_count': len(male_paces),
                'female_count': len(female_paces),
            },
        }
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting race stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ENDPOINTS
# ============================================================================

@router.get("/api/status", tags=["System"])
async def api_status(state: AppState = Depends(get_app_state)):
    """Статус приложения"""
    return {
        'status': 'ok',
        'event': settings.CURRENT_EVENT,
        'cached_routes': len(state.osm_route_data),
        'selected_runners': {k: len(v) for k, v in state.selected_runners.items()},
    }


# --- COPERNICO FETCHER ENDPOINTS ---

@router.post("/api/fetch-now", tags=["Data"])
async def fetch_race_data_now():
    """
    Получить данные гонки с Copernico API один раз
    Полезно для принудительного обновления без запуска фонового процесса
    """
    from src.tracker.parsers import fetch_data, save_to_file
    
    try:
        data = fetch_data()
        if data is not None:
            success = save_to_file(data)
            num_records = len(data) if isinstance(data, list) else len(data.get('data', []))
            
            return {
                "success": success,
                "message": f"✅ Получено и сохранено {num_records} записей",
                "records_count": num_records,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "message": "❌ Ошибка при получении данных из API",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        logger.error(f"Error in fetch_race_data_now: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"❌ Ошибка: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@router.get("/api/fetcher-status", tags=["Data"])
async def fetcher_status():
    """
    Информация о состоянии race_data.json
    Показывает время последнего обновления и количество записей
    """
    try:
        race_data_path = Path(settings.RACE_DATA_FILE)
        
        if not race_data_path.exists():
            return {
                "exists": False,
                "message": "Файл race_data.json еще не создан",
                "file_path": str(race_data_path)
            }
        
        with open(race_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        last_updated = data.get('last_updated', 'Unknown')
        records = data.get('data', [])
        
        return {
            "exists": True,
            "file_path": str(race_data_path),
            "last_updated": last_updated,
            "records_count": len(records) if isinstance(records, list) else 0,
            "file_size_kb": race_data_path.stat().st_size / 1024,
            "copernico_api_url": settings.COPERNICO_API_URL[:80] + "..." if settings.COPERNICO_API_URL else "Not configured"
        }
    except Exception as e:
        logger.error(f"Error in fetcher_status: {str(e)}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# --- DATABASE DEBUG ENDPOINTS ---

@router.get("/api/db-debug", tags=["Debug"])
async def database_debug():
    """
    Отладочный endpoint для проверки подключения к БД и структуры таблиц
    Оптимизирован с использованием кэшированной информации о таблицах
    """
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
        
        # Используем оптимизированную функцию с INFORMATION_SCHEMA и кэшем
        optimized_info = get_database_info_optimized()
        debug_info.update(optimized_info)
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Error in database_debug: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "message": "Check server logs for details"
        }


@router.get("/api/db-test-fetch", tags=["Debug"])
async def test_fetch_runners():
    """
    Тестирует загрузку данных участников из БД
    Показывает какие данные получены и формат
    """
    try:
        from src.analytics.db_connection_optimized import get_test_table_data
        
        logger.info("Testing runner data fetch from database...")
        
        runners = get_test_table_data()
        
        test_result = {
            "success": True,
            "total_runners": len(runners),
            "sample_runner": runners[0] if runners else None,
            "all_runners": runners[:10] if len(runners) > 10 else runners,  # First 10 records
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"✅ Successfully retrieved {len(runners)} runners from database")
        
        return test_result
        
    except Exception as e:
        logger.error(f"Error in test_fetch_runners: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

