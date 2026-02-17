"""
Кастомные исключения приложения
"""


class KMTrackException(Exception):
    """Базовое исключение приложения"""
    pass


class EventNotFoundError(KMTrackException):
    """Событие не найдено"""
    def __init__(self, event_id: str):
        self.event_id = event_id
        super().__init__(f"Event '{event_id}' not found")


class RunnerNotFoundError(KMTrackException):
    """Участник не найден"""
    def __init__(self, runner_id: str):
        self.runner_id = runner_id
        super().__init__(f"Runner '{runner_id}' not found")


class RouteError(KMTrackException):
    """Ошибка при загрузке маршрута"""
    def __init__(self, message: str):
        super().__init__(message)


class DatabaseError(KMTrackException):
    """Ошибка базы данных"""
    def __init__(self, message: str):
        super().__init__(message)


class ValidationError(KMTrackException):
    """Ошибка валидации данных"""
    def __init__(self, message: str):
        super().__init__(message)
