# server/copernico_parser.py
import logging
from datetime import datetime, timedelta
import math
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class CopernicoParser:
    def __init__(self, race_config):
        self.race_config = race_config

    def parse_runner_data(self, raw_runner: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Парсинг данных одного спортсмена из Copernico"""
        try:
            # Базовые данные
            runner_id = raw_runner.get('Id', '').strip()
            bib = raw_runner.get('Bib', 0)

            # Обработка номера - может быть строкой или числом
            try:
                if isinstance(bib, str):
                    bib = int(bib.strip()) if bib.strip() else 0
                elif bib is None:
                    bib = 0
            except (ValueError, TypeError):
                bib = 0

            name = raw_runner.get('Name', '').strip()
            surname = raw_runner.get('Surname', '').strip()
            full_name = raw_runner.get('Full name', '').strip()

            if not full_name and (name or surname):
                full_name = f"{name} {surname}".strip()
            elif not full_name:
                full_name = f"Участник {bib}"

            category = raw_runner.get('Category', 'Не указана')
            gender = raw_runner.get('Gender', 'unknown').capitalize()

            # Статус участника
            status = self._parse_status(raw_runner.get('Status', 'Not started'))

            # Рассчитываем текущую дистанцию
            current_distance = self._calculate_current_distance(raw_runner, status)

            # Расчет позиции на карте
            position = self._calculate_position(current_distance)

            runner = {
                'Id': runner_id,
                'Bib': bib,
                'Name': name,
                'Surname': surname,
                'Full name': full_name,
                'Category': category,
                'Gender': gender,
                'Status': status,
                'Start': {
                    'treal': raw_runner.get('Start.treal', ''),
                    'tofficial': raw_runner.get('Start.tofficial', '')
                },
                'kt2': {
                    'treal': raw_runner.get('kt2.treal', ''),
                    'tofficial': raw_runner.get('kt2.tofficial', ''),
                    'avg': raw_runner.get('kt2.avg', '')
                },
                'Finish': {
                    'treal': raw_runner.get('Finish.treal', ''),
                    'tofficial': raw_runner.get('Finish.tofficial', ''),
                    'avg': raw_runner.get('Finish.avg', '')
                },
                'Position': position,
                'current_distance': current_distance,
                'last_update': datetime.now().isoformat(),
                'source_data': raw_runner
            }

            return runner

        except Exception as e:
            logger.error(f"Ошибка парсинга участника: {type(e).__name__}: {e}")
            logger.debug(f"Данные участника: {raw_runner}")
            return None

    def _parse_status(self, status_raw: str) -> str:
        """Парсинг статуса участника"""
        status_raw = status_raw.lower()

        if 'finish' in status_raw:
            return 'Finished'
        elif 'start' in status_raw and 'not' not in status_raw:
            return 'Started'
        else:
            return 'Not started'

    def _calculate_current_distance(self, runner_data: Dict[str, Any], status: str) -> float:
        """Расчет текущей дистанции на основе данных из Copernico"""

        # Если финишировал - дистанция = полная
        if status == 'Finished':
            if runner_data.get('Finish', {}).get('treal'):
                return self.race_config.total_distance
            return self.race_config.total_distance * 0.95  # Почти финишировал

        # Если не стартовал - дистанция = 0
        if status == 'Not started' or not runner_data.get('Start', {}).get('treal'):
            return 0.0

        # Для стартовавших рассчитываем по времени
        start_time = runner_data.get('Start', {}).get('treal', '')
        kt2_time = runner_data.get('kt2', {}).get('treal', '')
        finish_time = runner_data.get('Finish', {}).get('treal', '')

        # Если есть время на 3.5 км (kt2), то прошел первый круг
        if kt2_time:
            # Если есть время финиша, то почти финишировал
            if finish_time:
                return self.race_config.total_distance
            # Иначе на втором круге
            return self.race_config.lap_distance + 1.0  # Примерно 4.5 км

        # Если только стартовал, то на первом круге
        return 1.75  # Примерно 1.75 км (половина первого круга)

    def _calculate_position(self, distance: float):
        """Расчет позиции на карте по дистанции"""

        # Координаты контрольных точек маршрута
        checkpoints = [
            {'distance': 0.0, 'coord': [56.028855, 92.946101]},  # Старт
            {'distance': 1.75, 'coord': [56.02996, 92.949893]},  # 1.75 км
            {'distance': 3.5, 'coord': [56.031108, 92.951328]},  # 3.5 км
            {'distance': 5.25, 'coord': [56.02996, 92.949893]},  # 5.25 км
            {'distance': 7.0, 'coord': [56.028855, 92.946101]}  # Финиш
        ]

        # Находим ближайшие точки для интерполяции
        for i in range(len(checkpoints) - 1):
            cp1 = checkpoints[i]
            cp2 = checkpoints[i + 1]

            if cp1['distance'] <= distance <= cp2['distance']:
                # Линейная интерполяция
                ratio = (distance - cp1['distance']) / (cp2['distance'] - cp1['distance'])
                lat = cp1['coord'][0] + (cp2['coord'][0] - cp1['coord'][0]) * ratio
                lng = cp1['coord'][1] + (cp2['coord'][1] - cp1['coord'][1]) * ratio
                return {'lat': lat, 'lng': lng}

        # Если дистанция больше максимальной, возвращаем финиш
        if distance > checkpoints[-1]['distance']:
            return {'lat': checkpoints[-1]['coord'][0], 'lng': checkpoints[-1]['coord'][1]}

        # Если дистанция меньше 0, возвращаем старт
        return {'lat': checkpoints[0]['coord'][0], 'lng': checkpoints[0]['coord'][1]}