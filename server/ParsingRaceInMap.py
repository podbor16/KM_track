# server/copernico_parser.py
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class CopernicoParser:
    def __init__(self, race_config):
        self.race_config = race_config

    def parse_runner_data(self, raw_runner: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Парсинг данных одного спортсмена из Copernico JSON файла с поддержкой поля dorsal"""
        try:
            # Извлечение и обработка номера участника (dorsal)
            dorsal_value = raw_runner.get('dorsal', 0)
            runner_id = str(dorsal_value)
            
            # Стандартизация номера для bib
            try:
                if isinstance(dorsal_value, str):
                    bib = int(dorsal_value.strip() or '0')
                elif dorsal_value is None:
                    bib = 0
                else:
                    bib = int(dorsal_value)
            except (ValueError, TypeError):
                bib = 0

            # Извлечение ФИО
            name = raw_runner.get('name', '').strip()
            surname = raw_runner.get('surname', '').strip()
            full_name = raw_runner.get('fullName', '').strip()

            if not full_name and (name or surname):
                full_name = f"{name} {surname}".strip()
            elif not full_name:
                full_name = f"Участник {bib}"

            # Категория и пол
            category = raw_runner.get('category', 'Не указана')
            gender = raw_runner.get('gender', 'unknown').lower()
            if gender.startswith('f'):
                gender = 'Female'
            elif gender.startswith('m'):
                gender = 'Male'
            else:
                gender = 'Unknown'

            # Статус участника
            status_raw = raw_runner.get('status', 'notstarted').lower()
            status = self._parse_status(status_raw)

            # Безопасное извлечение временных данных (обработка null)
            def safe_get(field, default=''):
                value = raw_runner.get(field)
                return value if value is not None else default

            start_treal = safe_get('times.real_:::start:::')
            kt2_treal = safe_get('times.real_kt2')
            finish_treal = safe_get('times.real_:::finish:::')

            # Расчет текущей дистанции
            current_distance = self._calculate_current_distance(
                start_treal, kt2_treal, finish_treal, status
            )

            # Расчет позиции на карте
            position = self._calculate_position(current_distance)

            # ФОРМИРОВАНИЕ ИТОГОВОГО СЛОВАРЯ С ПОДДЕРЖКОЙ DORSAL
            runner = {
                'id': runner_id,
                'bib': bib,
                'dorsal': dorsal_value,  # КРИТИЧЕСКИ ВАЖНОЕ ПОЛЕ ДЛЯ ФРОНТЕНДА
                'name': name,
                'surname': surname,
                'full_name': full_name,
                'category': category,
                'gender': gender,
                'status': status,
                'start': {
                    'treal': start_treal,
                    'tofficial': safe_get('times.official_:::start:::')
                },
                'kt2': {
                    'treal': kt2_treal,
                    'tofficial': safe_get('times.official_kt2'),
                    'avg': safe_get('intervalaverages_kt2')
                },
                'finish': {
                    'treal': finish_treal,
                    'tofficial': safe_get('times.official_:::finish:::'),
                    'avg': safe_get('intervalaverages_:::full-1:::')
                },
                'position': position,
                'current_distance': current_distance,
                'last_update': datetime.now().isoformat(),
                'source_data': raw_runner
            }

            return runner

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга участника {raw_runner.get('dorsal', 'N/A')}: {type(e).__name__}: {e}")
            logger.debug(f"Данные участника: {raw_runner}")
            return None

    def _parse_status(self, status_raw: str) -> str:
        """Преобразование статуса из формата Copernico в стандартный"""
        if 'finished' in status_raw or 'complete' in status_raw or status_raw == 'finished':
            return 'Finished'
        elif 'started' in status_raw or 'running' in status_raw or (status_raw == 'started' or status_raw == 'running'):
            return 'Started'
        return 'Not started'

    # ИСПРАВЛЕНО: СИГНАТУРА МЕТОДА СООТВЕТСТВУЕТ ВЫЗОВУ
    def _calculate_current_distance(
        self, 
        start_time: str, 
        kt2_time: str, 
        finish_time: str, 
        status: str
    ) -> float:
        """Расчет текущей дистанции на основе временных меток"""
        # Если финишировал - полная дистанция
        if status == 'Finished':
            return self.race_config.total_distance
        
        # Если не стартовал - 0 км
        if status == 'Not started' or not start_time:
            return 0.0
        
        # Если есть время на 3.5 км (kt2) и нет финиша
        if kt2_time and not finish_time:
            return self.race_config.lap_distance + 1.0  # ~4.5 км
        
        # Если только стартовал
        return 1.75  # ~1.75 км (половина первого круга)

    def _calculate_position(self, distance: float) -> Dict[str, float]:
        """Расчет координат на карте по пройденной дистанции"""
        # Координаты контрольных точек маршрута
        checkpoints = [
            {'distance': 0.0, 'coord': [56.028855, 92.946101]},  # Старт
            {'distance': 1.75, 'coord': [56.02996, 92.949893]},  # 1.75 км
            {'distance': 3.5, 'coord': [56.031108, 92.951328]},  # 3.5 км
            {'distance': 5.25, 'coord': [56.02996, 92.949893]},  # 5.25 км
            {'distance': 7.0, 'coord': [56.028855, 92.946101]}   # Финиш
        ]

        # Нормализация дистанции в пределах трассы
        total_distance = checkpoints[-1]['distance']
        if distance < 0:
            distance = 0.0
        elif distance > total_distance:
            distance = total_distance

        # Поиск сегмента для интерполяции
        for i in range(len(checkpoints) - 1):
            cp1 = checkpoints[i]
            cp2 = checkpoints[i + 1]
            
            if cp1['distance'] <= distance <= cp2['distance']:
                # Расчет коэффициента интерполяции
                segment_length = cp2['distance'] - cp1['distance']
                ratio = (distance - cp1['distance']) / segment_length if segment_length > 0 else 0
                
                # Интерполяция координат
                lat = cp1['coord'][0] + (cp2['coord'][0] - cp1['coord'][0]) * ratio
                lng = cp1['coord'][1] + (cp2['coord'][1] - cp1['coord'][1]) * ratio
                
                return {'lat': lat, 'lng': lng}

        # Защита от некорректных значений
        return {'lat': checkpoints[0]['coord'][0], 'lng': checkpoints[0]['coord'][1]}

    def parse_all_runners(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Массовый парсинг всех участников"""
        runners = []
        for raw_runner in raw_data:
            runner = self.parse_runner_data(raw_runner)
            if runner:
                runners.append(runner)
        return runners