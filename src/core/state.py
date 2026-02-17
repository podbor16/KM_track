"""
Управление глобальным состоянием приложения
"""

import threading
from typing import Dict, Optional, Set, List
from datetime import datetime


class AppState:
    """Хранилище глобального состояния приложения"""
    
    def __init__(self):
        # Кеш маршрутов по событиям
        self.osm_route_data: Dict[str, dict] = {}
        
        # Кеш всех участников
        self.cache_data: Optional[List[dict]] = None
        self.cache_time: Optional[datetime] = None
        
        # Lock для потокобезопасности
        self.cache_lock = threading.Lock()
        
        # Выбранные участники по событиям (event_id -> set(runner_ids))
        self.selected_runners: Dict[str, Set[str]] = {}
        
        # Время последней загрузки маршрутов
        self.last_route_fetch_time: Dict[str, float] = {}
    
    def reset(self):
        """Сбросить состояние"""
        with self.cache_lock:
            self.osm_route_data.clear()
            self.cache_data = None
            self.cache_time = None
            self.selected_runners.clear()
            self.last_route_fetch_time.clear()

    def __repr__(self):
        return (
            f"<AppState: "
            f"routes={len(self.osm_route_data)}, "
            f"cache_time={self.cache_time}, "
            f"runners_count={len(self.selected_runners)}>"
        )
