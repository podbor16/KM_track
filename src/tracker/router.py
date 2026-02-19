"""
API роутеры для трекера маршрутов
Основной модуль с 18+ endpoints для управления гонками и участниками
"""

import logging
import json
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Query, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.config import settings
from src.core.state import AppState
from src.core.dependencies import get_app_state, get_event
from src.tracker.models import (
    Runner, RunnersListResponse, RunnerSelectionRequest, SelectedRunnersResponse,
    Route, RouteResponse, RaceConfig,
    CurrentEventResponse, EventsListResponse, EventInfo,
    Analytics, AnalyticsResponse, RegisteredRunnersListResponse, RaceResultsResponse,
)
from src.tracker.services import (
    fetch_route_from_osm, get_route_calculator,
    fetch_copernico_data, transform_copernico_data, update_runner_positions,
    get_formatted_analytics,
)

logger = logging.getLogger(__name__)

# Создать роутер
router = APIRouter(prefix="", tags=["tracker"])

# Подключить шаблоны (реэкспорт из app.py)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
LEGACY_TEMPLATES_DIR = BASE_DIR / "legacy" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
legacy_templates = Jinja2Templates(directory=str(LEGACY_TEMPLATES_DIR))


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
    return legacy_templates.TemplateResponse("tracker.html", context)


async def tracker_main(request: Request):
    """Главная страница трекера"""
    context = {
        "request": request,
        "event": settings.CURRENT_EVENT,
        "events": list(settings.EVENTS_CONFIG.keys()),
    }
    return legacy_templates.TemplateResponse("tracker.html", context)


@router.get("/analytics", response_class=HTMLResponse, tags=["Pages"])
async def analytics_page(request: Request):
    """Страница аналитики"""
    context = {
        "request": request,
        "event": settings.CURRENT_EVENT,
    }
    return legacy_templates.TemplateResponse("analytics.html", context)


@router.get("/start_list", response_class=HTMLResponse, tags=["Pages"])
async def start_list_page(request: Request):
    """Оригинальная страница стартового списка - возвращает статический HTML"""
    from pathlib import Path
    start_list_path = Path(__file__).resolve().parent.parent.parent.parent / "analytics" / "personal" / "start_list.html"
    
    try:
        with open(start_list_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading start_list: {e}")
        # Fallback на основную страницу трекера
        return await tracker_main(request)


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
# МАРШРУТЫ (ROUTES)
# ============================================================================

@router.get("/api/route", response_model=RouteResponse, tags=["Routes"])
async def get_route(
    event: str = Query(settings.CURRENT_EVENT, description="Event ID"),
    state: AppState = Depends(get_app_state),
) -> RouteResponse:
    """
    Получить маршрут события
    - Кеширует результат на 3600 секунд
    - Поддерживает челночные (shuttle) и кольцевые (loop) маршруты
    """
    # Валидация события
    if event not in settings.EVENTS_CONFIG:
        return RouteResponse(
            success=False,
            cached=False,
            message=f"Event '{event}' not found",
        )
    
    event_config = settings.EVENTS_CONFIG[event]
    route_type = 'shuttle' if event != 'rosneft' else 'loop'
    
    try:
        # Пытаемся загрузить маршрут
        coords = fetch_route_from_osm(event)
        
        if not coords:
            logger.warning(f"No coordinates loaded for event {event}")
            return RouteResponse(
                success=False,
                cached=False,
                message="Could not load route coordinates",
            )
        
        # Инициализируем калькулятор если нужно
        route_calc = get_route_calculator()
        route_calc.set_path(coords)
        
        # Подготовляем ответ
        route = Route(
            coordinates=coords,
            distance=event_config.get('total_race_km', 0),
            way_id=event_config.get('osm_way_id', 0),
            event=event,
            event_name=event_config.get('name', event),
            route_type=route_type,
        )
        
        race_config = RaceConfig(
            total_distance=event_config.get('total_race_km', 0),
            event_name=event_config.get('name', event),
            event_id=event,
            route_type=route_type,
            one_way_length=event_config.get('one_way_length_km'),
            laps=event_config.get('laps'),
            checkpoints=[],
        )
        
        return RouteResponse(
            success=True,
            route=route,
            config=race_config,
            cached=False,
        )
    
    except Exception as e:
        logger.error(f"Error loading route for {event}: {e}")
        return RouteResponse(
            success=False,
            cached=False,
            message=f"Error: {str(e)}",
        )


# ============================================================================
# УЧАСТНИКИ (RUNNERS)
# ============================================================================

@router.get("/api/runners", response_model=RunnersListResponse, tags=["Runners"])
async def get_runners(
    event: str = Query(settings.CURRENT_EVENT, description="Event ID"),
    state: AppState = Depends(get_app_state),
) -> RunnersListResponse:
    """
    Получить список всех участников события из race_data.json
    - Загружает данные участников из файла race_data.json
    - Возвращает полную информацию о каждом участнике с его статусом
    """
    try:
        # Загружаем данные из race_data.json
        import json
        from pathlib import Path
        
        race_data_path = Path(settings.RACE_DATA_FILE)
        with open(race_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        runners_data = data.get('data', [])
        
        # Считаем статусы
        total = len(runners_data)
        running = sum(1 for r in runners_data if r.get('status') == 'running')
        finished = sum(1 for r in runners_data if r.get('status') == 'finished')
        not_started = sum(1 for r in runners_data if r.get('status') == 'notstarted')
        
        # Преобразуем в Pydantic модели
        runners_models = []
        for r in runners_data:
            try:
                dorsal = int(r.get('dorsal', 0))
                name = r.get('name', '')
                surname = r.get('surname', '')
                
                runner = Runner(
                    id=str(dorsal),
                    bib=dorsal,
                    dorsal=dorsal,
                    name=name.strip(),
                    surname=surname.strip(),
                    full_name=r.get('fullName', f"{surname} {name}".strip()).strip(),
                    category=r.get('category', 'N/A'),
                    gender=r.get('gender', 'Unknown'),
                    status=r.get('status', 'notstarted'),
                    current_distance=float(r.get('current_distance', 0)),
                    position={'lat': 56.0, 'lng': 92.0},  # Default position - Kirov
                    speed=float(r.get('speed', 0)),
                    pace=float(r.get('pace', 0)),
                    start={'treal': None, 'tofficial': None},
                    kt2={'treal': None, 'tofficial': None, 'avg': None},
                    finish=None,
                    last_update=datetime.now().isoformat(),
                )
                runners_models.append(runner)
            except Exception as e:
                logger.warning(f"Error converting runner {r.get('dorsal', 'unknown')}: {e}")
                continue
        
        return RunnersListResponse(
            event=event,
            total=total,
            running=running,
            finished=finished,
            not_started=not_started,
            runners=runners_models,
            last_update=datetime.now().isoformat(),
        )
    
    except Exception as e:
        logger.error(f"Error getting runners: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/search-runners", tags=["Runners"])
async def search_runners(
    q: str = Query("", min_length=1, description="Search query (name or bib)"),
    event: str = Query(settings.CURRENT_EVENT),
    state: AppState = Depends(get_app_state),
):
    """
    Поиск участников по имени или номеру
    """
    try:
        raw_data = fetch_copernico_data()
        runners_data = transform_copernico_data(raw_data)
        
        q_lower = q.lower()
        results = []
        
        for runner in runners_data:
            full_name = runner.get('full_name', '').lower()
            bib = str(runner.get('bib', ''))
            
            if q_lower in full_name or q_lower in bib:
                results.append({
                    'id': runner.get('id'),
                    'full_name': runner.get('full_name'),
                    'bib': runner.get('bib'),
                    'status': runner.get('status'),
                })
        
        return {
            'query': q,
            'count': len(results),
            'results': results[:10],  # Ограничиваем до 10 результатов
        }
    
    except Exception as e:
        logger.error(f"Error searching runners: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        from src.analytics.db_connection import get_test_table_data
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
            
            runner_info = RegisteredRunnerInfo(
                id=str(idx + 1),
                name=runner_data.get('name', ''),
                surname=runner_data.get('surname', ''),
                full_name=full_name,
                category=runner_data.get('category', 'Неизвестно'),
                city=runner_data.get('city', ''),
                sex=runner_data.get('sex', ''),
                club=runner_data.get('club', ''),
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


@router.get("/api/race-results", response_model=RaceResultsResponse, tags=["Analytics"])
async def get_race_results(
    event: str = Query(settings.CURRENT_EVENT),
) -> RaceResultsResponse:
    """
    Получить результаты гонки из race_data.json
    """
    try:
        raw_data = fetch_copernico_data()
        
        results = []
        for runner in raw_data[:100]:  # Ограничиваем до 100 результатов
            results.append({
                'id': runner.get('dorsal'),
                'full_name': f"{runner.get('name', '')} {runner.get('surname', '')}",
                'gender': runner.get('gender'),
                'category': runner.get('category'),
                'finish_time': runner.get('times.official_:::finish:::'),
                'status': runner.get('status'),
                'ranking': runner.get('rankings_:::full-1:::'),
            })
        
        return RaceResultsResponse(
            event=event,
            total_results=len(raw_data),
            results=results,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Error getting race results: {e}")
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
    Показывает какие таблицы есть в БД и их содержимое
    """
    try:
        from src.analytics.db_connection import create_connection
        
        debug_info = {
            "db_config": {
                "host": settings.DB_HOST,
                "port": settings.DB_PORT,
                "database": settings.DB_NAME,
                "user": settings.DB_USER,
            },
            "connection": "Testing...",
            "tables": [],
            "errors": []
        }
        
        connection = create_connection()
        
        if not connection:
            debug_info["connection"] = "❌ Failed to connect"
            debug_info["errors"].append("Could not establish database connection")
            return debug_info
        
        debug_info["connection"] = "✅ Connected successfully"
        
        try:
            cursor = connection.cursor(dictionary=True, buffered=True)
            
            # Получаем список таблиц
            cursor.execute("SHOW TABLES")
            tables_result = cursor.fetchall()
            table_names = [list(t.values())[0] for t in tables_result]
            
            debug_info["tables_list"] = table_names
            logger.info(f"📋 Available tables: {table_names}")
            
            # Для каждой таблицы получаем информацию
            for table_name in table_names:
                table_info = {
                    "name": table_name,
                    "row_count": 0,
                    "columns": [],
                    "sample_rows": []
                }
                
                try:
                    # Количество строк
                    cursor.execute(f"SELECT COUNT(*) as count FROM `{table_name}`")
                    count_result = cursor.fetchone()
                    table_info["row_count"] = count_result.get('count', 0) if count_result else 0
                    
                    # Структура таблицы
                    cursor.execute(f"DESCRIBE `{table_name}`")
                    fields = cursor.fetchall()
                    table_info["columns"] = [f.get('Field', '') for f in fields] if fields else []
                    
                    # BeispielRows
                    cursor.execute(f"SELECT * FROM `{table_name}` LIMIT 2")
                    samples = cursor.fetchall()
                    table_info["sample_rows"] = samples if samples else []
                    
                    debug_info["tables"].append(table_info)
                    
                except Exception as table_error:
                    debug_info["errors"].append(f"Error reading table {table_name}: {str(table_error)}")
                    logger.error(f"Error reading table {table_name}: {table_error}")
            
            cursor.close()
            
        finally:
            if connection.is_connected():
                connection.close()
                
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
        from src.analytics.db_connection import get_test_table_data
        
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

