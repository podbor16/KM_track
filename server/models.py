# server/models.py
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class Checkpoint:
    """Модель контрольной точки"""
    id: str
    name: str
    distance: float  # дистанция от старта в км
    passed: bool
    time: Optional[str] = None  # время прохождения
    timestamp: Optional[str] = None
    position: Optional[int] = None  # позиция на точке

    def to_dict(self):
        return asdict(self)


@dataclass
class RunnerPosition:
    """Модель позиции на карте"""
    lat: float
    lng: float
    segment: Optional[str] = None  # текущий сегмент
    progress: float = 0.0  # прогресс на сегменте от 0 до 1


@dataclass
class Runner:
    """Полная модель данных спортсмена из Copernico"""
    # Основная информация
    id: str
    dorsal: int  # стартовый номер
    name: str
    surname: str
    full_name: str
    gender: str
    birth_year: Optional[int] = None
    city: Optional[str] = None
    country: Optional[str] = None

    # Категорийная информация
    category: str
    category_code: Optional[str] = None
    team: Optional[str] = None
    club: Optional[str] = None

    # Статус и время
    status: str  # 'registered', 'started', 'finished', 'dnf', 'dq'
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    net_time: Optional[str] = None  # чистое время
    gun_time: Optional[str] = None  # время от выстрела

    # Хронометраж
    checkpoints: List[Checkpoint] = None
    split_times: Dict[str, str] = None  # промежуточные времена

    # Текущие показатели
    current_distance: float = 0.0
    current_pace: float = 0.0  # мин/км
    average_pace: float = 0.0
    speed: float = 0.0  # км/ч

    # Позиция
    position: RunnerPosition = None
    overall_position: Optional[int] = None  # общая позиция
    category_position: Optional[int] = None  # позиция в категории

    # Технические поля
    last_update: str = None
    source_data: Dict[str, Any] = None  # сырые данные из Copernico

    def __post_init__(self):
        if self.checkpoints is None:
            self.checkpoints = []
        if self.split_times is None:
            self.split_times = {}
        if self.position is None:
            self.position = RunnerPosition(lat=0, lng=0)
        if self.last_update is None:
            self.last_update = datetime.now().isoformat()

    def to_dict(self, include_source=False):
        """Конвертация в словарь для API"""
        data = {
            'id': self.id,
            'dorsal': self.dorsal,
            'name': self.name,
            'surname': self.surname,
            'full_name': self.full_name,
            'gender': self.gender,
            'category': self.category,
            'status': self.status,
            'current_distance': self.current_distance,
            'current_pace': self.current_pace,
            'position': {
                'lat': self.position.lat,
                'lng': self.position.lng,
                'segment': self.position.segment,
                'progress': self.position.progress
            },
            'checkpoints': [cp.to_dict() for cp in self.checkpoints],
            'last_update': self.last_update
        }

        if include_source:
            data['source_data'] = self.source_data

        return data

    @classmethod
    def from_copernico(cls, raw_data: Dict[str, Any]) -> 'Runner':
        """Создание объекта из сырых данных Copernico"""
        # Эта функция будет парсить данные из Copernico
        # Пока заглушка - реализуем позже
        pass