#!/usr/bin/env python3
"""
🏃 KRASMARAFON RACE LOADER v3.0 - COMPLETE
Загружает и обновляет результаты забега из системы хронометража
С полной поддержкой всех полей, времен, темпов, рангов и сегментов

РЕЖИМЫ:
  1. --init --event-id 99       : Первая загрузка (INSERT всех участников)
  2. --event-id 99              : Непрерывное обновление (UPDATE существующих, работает до Ctrl+C)

ПРИМЕРЫ:
  python load_race_results.py --init --event-id 99
  python load_race_results.py --event-id 99
  python load_race_results.py --event-id 99 --interval 3

ЛОГИРОВАНИЕ: Все операции логируются в logs/race_loader_*.log
"""

import sys
import json
import time
import logging
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import os

# Добавляем src в PATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Загружаем конфиг из .env
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    print("❌ Установите: pip install python-dotenv")
    sys.exit(1)

from src.analytics.db_connection import create_connection

# === КОНСТАНТЫ ===
RACE_DATA_FILE = Path(os.getenv("RACE_DATA_FILE", "tracker/race_data.json"))
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
UPDATE_INTERVAL = int(os.getenv("CONTINUOUS_UPDATE_INTERVAL", "5"))
BATCH_SIZE = 1000

LOG_DIR.mkdir(exist_ok=True)


# === ЛОГИРОВАНИЕ ===
def setup_logging(event_id: int) -> logging.LoggerAdapter:
    """Подготовить логирование в файл и консоль"""
    log_file = LOG_DIR / f"race_loader_{event_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logger = logging.getLogger("RaceLoader")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)-8s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    return logging.LoggerAdapter(logger, {'event_id': event_id})


# === КОНВЕРТЕРЫ ===
def milliseconds_to_time(ms: Optional[int]) -> Optional[str]:
    """Конвертировать миллисекунды в HH:MM:SS"""
    if ms is None or ms == 0:
        return None
    try:
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f'{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}'
    except (TypeError, ValueError):
        return None


def convert_pace_format(pace_str: Optional[str]) -> Optional[str]:
    """Конвертировать темп из формата JSON (м'сс\"/км) в БД (мм:сс)"""
    if not pace_str or str(pace_str).lower() == 'null':
        return None
    try:
        match = re.search(r"(\d{1,2})'(\d{2})", str(pace_str))
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            return f'{minutes:02d}:{seconds:02d}'
    except (ValueError, AttributeError):
        pass
    return None


def convert_status(status: Optional[str]) -> str:
    """Конвертировать статус из JSON в БД формат"""
    if not status:
        return 'Not started'
    
    status_map = {
        'notstarted': 'Not started',
        'running': 'Running',
        'finished': 'Finished',
        'dnf': 'DNF',
        'dsq': 'DSQ',
        'withdrawn': 'Withdrawn'
    }
    return status_map.get(status.lower(), 'Not started')


def convert_gender(gender: Optional[str]) -> str:
    """Конвертировать пол из JSON"""
    if not gender:
        return 'Unknown'
    elif gender == 'male' or gender == 'Male':
        return "Мужчина"
    else:
        return "Женщина"


# === КЛАСС ЗАГРУЗЧИКА ===
class RaceLoader:
    """Оптимизированный загрузчик результатов в двух режимах"""
    
    def __init__(self, event_id: int, logger: logging.LoggerAdapter):
        self.event_id = event_id
        self.logger = logger
        self.connection = None
        self.cursor = None
        self.existing_results: Dict[str, Dict] = {}
        self.inserted_count = 0
        self.updated_results_count = 0
        self.updated_segments_count = 0
        self.update_cycles = 0
    
    def connect(self) -> bool:
        """Подключиться к БД"""
        self.logger.info("🔌 Подключение к БД...")
        
        try:
            self.connection = create_connection()
            self.cursor = self.connection.cursor(dictionary=True)
            
            # Проверить событие
            self.cursor.execute(
                "SELECT id, event_name, event_distance FROM events WHERE id = %s",
                (self.event_id,)
            )
            event = self.cursor.fetchone()
            
            if not event:
                self.logger.error(f"❌ События ID {self.event_id} не найдено в БД")
                return False
            
            self.logger.info(f"✅ Подключено. Событие: {event['event_name']} ({event['event_distance']} км)")
            return True
        
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    def load_race_data(self) -> List[Dict]:
        """Прочитать race_data.json"""
        if not RACE_DATA_FILE.exists():
            self.logger.error(f"❌ Файл не найден: {RACE_DATA_FILE}")
            return []
        
        try:
            with open(RACE_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            runners = data.get('data', [])
            if not self.update_cycles:
                self.logger.info(f"📂 Загружено {len(runners)} участников из race_data.json")
            return runners
        
        except Exception as e:
            self.logger.error(f"❌ Ошибка JSON: {e}")
            return []
    
    def load_existing_results(self) -> None:
        """Загрузить существующие результаты в кэш"""
        self.logger.info(f"⏳ Загрузка существующих результатов в кэш...")
        
        try:
            # Загрузить ВСЕ поля из results
            self.cursor.execute(
                """SELECT id, start_number, surname, name, birthday, sex, category, 
                          race_status, time_gun_start, time_clear_start, time_gun_finish, 
                          time_clear_finish, rank_absolute, rank_sex, rank_category, 
                          finish_pace_avg, time_clear_kt1, time_clear_kt2, time_clear_kt3, 
                          time_clear_kt4, time_clear_kt5, pace_avg_kt1, pace_avg_kt2, 
                          pace_avg_kt3, pace_avg_kt4, pace_avg_kt5
                   FROM results WHERE event_id = %s""",
                (self.event_id,)
            )
            
            self.existing_results = {}
            for row in self.cursor.fetchall():
                dorsal = str(row['start_number']) if row['start_number'] else None
                if dorsal:
                    self.existing_results[dorsal] = dict(row)
            
            self.logger.info(f"✅ Кэш загружен: {len(self.existing_results)} результатов")
        except Exception as e:
            self.logger.error(f"❌ Ошибка кэша: {e}")
    
    def init_mode(self, runners: List[Dict]) -> bool:
        """РЕЖИМ INIT: Загрузить один раз всех участников с INSERT"""
        self.logger.info("\n" + "="*70)
        self.logger.info("🚀 РЕЖИМ ИНИЦИАЛИЗАЦИИ (--init)")
        self.logger.info("="*70)
        self.logger.info(f"Загрузка {len(runners)} участников в БД...")
        
        batch = []
        start_time = time.time()
        
        try:
            for idx, runner in enumerate(runners, 1):
                dorsal = runner.get('dorsal')
                surname = runner.get('surname', '').strip()
                name = runner.get('name', '').strip()
                
                if not dorsal or not surname or not name:
                    continue
                
                batch.append((
                    self.event_id,
                    str(dorsal),
                    surname,
                    name,
                    runner.get('birthdate'),
                    convert_gender(runner.get('gender')),
                    runner.get('category', 'Unknown'),
                    'Not started'
                ))
                
                if len(batch) >= BATCH_SIZE or idx == len(runners):
                    count = self._bulk_insert(batch)
                    self.inserted_count += count
                    batch = []
                    
                    elapsed = time.time() - start_time
                    self.logger.info(f"   ⏱️ {idx}/{len(runners)} участников ({elapsed:.1f}с)")
            
            elapsed = time.time() - start_time
            self.logger.info(f"\n✅ INIT завершена")
            self.logger.info(f"   Вставлено: {self.inserted_count} участников")
            self.logger.info(f"   Время: {elapsed:.1f}с ({elapsed/len(runners):.3f}с/участник)")
            self.logger.info("="*70 + "\n")
            
            self.connection.commit()
            return True
        
        except Exception as e:
            self.logger.error(f"❌ Ошибка INIT: {e}")
            self.connection.rollback()
            return False
    
    def continuous_mode(self, runners: List[Dict], interval: int, reset_cache_interval: int = 15) -> None:
        """РЕЖИМ CONTINUOUS: Постоянное обновление до Ctrl+C
        
        Args:
            runners: Начальные данные (не используются, перечитываются каждый цикл)
            interval: Интервал между циклами в сек
            reset_cache_interval: Интервал для перезагрузки кэша из БД (по умолчанию 5 мин)
        """
        self.logger.info("\n" + "="*70)
        self.logger.info("🔄 РЕЖИМ НЕПРЕРЫВНОГО ОБНОВЛЕНИЯ (CONTINUOUS)")
        self.logger.info(f"Интервал: {interval} сек")
        self.logger.info(f"Перезагрузка кэша: каждые {reset_cache_interval} сек")
        self.logger.info(f"Стоп: Нажмите Ctrl+C в терминале")
        self.logger.info("="*70 + "\n")
        
        last_cache_reload = time.time()
        
        try:
            while True:
                self.update_cycles += 1
                cycle_start = time.time()
                
                # Перезагрузить кэш периодически (каждые 5 минут) чтобы синхронизироваться с БД
                if time.time() - last_cache_reload > reset_cache_interval:
                    self.logger.debug("🔄 Перезагрузка кэша из БД...")
                    self.load_existing_results()
                    last_cache_reload = time.time()
                
                runners = self.load_race_data()
                if not runners:
                    self.logger.warning("⚠️ Ошибка чтения JSON, повторим...")
                    time.sleep(interval)
                    continue
                
                updated_r, updated_s = self._update_existing(runners)
                
                cycle_time = time.time() - cycle_start
                if updated_r > 0:
                    self.logger.info(f"📊 Цикл #{self.update_cycles}: {updated_r} results + {updated_s} segments ({cycle_time:.2f}с)")
                else:
                    self.logger.debug(f"📊 Цикл #{self.update_cycles}: 0 изменений ({cycle_time:.2f}с)")
                
                sleep_time = max(0, interval - cycle_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)
        
        except KeyboardInterrupt:
            self.logger.info("\n⛔ Остановка (Ctrl+C)...")
            self.logger.info("\n" + "="*70)
            self.logger.info(f"📊 ФИНАЛЬНАЯ СТАТИСТИКА")
            self.logger.info(f"   Циклов: {self.update_cycles}")
            self.logger.info(f"   Всего обновлено results: {self.updated_results_count} записей")
            self.logger.info(f"   Всего обновлено segments: {self.updated_segments_count} записей")
            self.logger.info("="*70 + "\n")
    
    def _update_existing(self, runners: List[Dict]) -> Tuple[int, int]:
        """Обновить все поля существующих записей И их сегменты"""
        results_batch = []
        segments_batch = []
        updated_dorsals = []  # Для логирования какие записи обновляются
        
        for runner in runners:
            dorsal = str(runner.get('dorsal'))
            
            if dorsal not in self.existing_results:
                continue
            
            existing = self.existing_results[dorsal]
            result_id = existing['id']
            
            # === РЕЗУЛЬТАТЫ ===
            surname = runner.get('surname', '').strip()
            name = runner.get('name', '').strip()
            birthdate = runner.get('birthdate')
            sex = convert_gender(runner.get('gender'))
            category = runner.get('category', 'Unknown')
            race_status = convert_status(runner.get('status'))
            
            # Времена со старта и финиша (конвертировать из мс)
            time_gun_start = milliseconds_to_time(runner.get('times.official_:::start:::'))
            time_clear_start = milliseconds_to_time(runner.get('times.real_:::start:::'))
            time_gun_finish = milliseconds_to_time(runner.get('times.official_:::finish:::'))
            time_clear_finish = milliseconds_to_time(runner.get('times.real_:::finish:::'))
            
            # Ранги (по чистому времени)
            rank_absolute = runner.get('netrankings_:::full-1:::')
            rank_sex = runner.get('netrankings.gen_:::full-1:::')
            rank_category = runner.get('netrankings.cat_:::full-1:::')
            
            # Темп финиша (конвертировать из м'сс"/км в мм:сс)
            finish_pace_avg = convert_pace_format(runner.get('netintervalaverages_:::full-1:::'))
            
            # Промежуточные времена КТ1-5 (конвертировать из мс)
            time_clear_kt1 = milliseconds_to_time(runner.get('times.real_kt1'))
            time_clear_kt2 = milliseconds_to_time(runner.get('times.real_kt2'))
            time_clear_kt3 = milliseconds_to_time(runner.get('times.real_kt3'))
            time_clear_kt4 = milliseconds_to_time(runner.get('times.real_kt4'))
            time_clear_kt5 = milliseconds_to_time(runner.get('times.real_kt5'))
            
            # Темпы КТ (конвертировать из м'сс"/км в мм:сс)
            pace_avg_kt1 = convert_pace_format(runner.get('netintervalaverages_kt1'))
            pace_avg_kt2 = convert_pace_format(runner.get('netintervalaverages_kt2'))
            pace_avg_kt3 = convert_pace_format(runner.get('netintervalaverages_kt3'))
            pace_avg_kt4 = convert_pace_format(runner.get('netintervalaverages_kt4'))
            pace_avg_kt5 = convert_pace_format(runner.get('netintervalaverages_kt5'))
            
            # === ПОЛНОЕ сравнение всех полей ===
            changed_fields = []
            if surname != existing.get('surname'):
                changed_fields.append(f'surname: "{existing.get("surname")}" → "{surname}"')
            if name != existing.get('name'):
                changed_fields.append(f'name: "{existing.get("name")}" → "{name}"')
            if race_status != existing.get('race_status'):
                changed_fields.append(f'race_status: "{existing.get("race_status")}" → "{race_status}"')
            if time_gun_finish != existing.get('time_gun_finish'):
                changed_fields.append(f'time_gun_finish: {existing.get("time_gun_finish")} → {time_gun_finish}')
            if rank_absolute != existing.get('rank_absolute'):
                changed_fields.append(f'rank_absolute: {existing.get("rank_absolute")} → {rank_absolute}')
            if rank_sex != existing.get('rank_sex'):
                changed_fields.append(f'rank_sex: {existing.get("rank_sex")} → {rank_sex}')
            if rank_category != existing.get('rank_category'):
                changed_fields.append(f'rank_category: {existing.get("rank_category")} → {rank_category}')
            if finish_pace_avg != existing.get('finish_pace_avg'):
                changed_fields.append(f'finish_pace_avg: {existing.get("finish_pace_avg")} → {finish_pace_avg}')
            if time_gun_start != existing.get('time_gun_start'):
                changed_fields.append(f'time_gun_start: {existing.get("time_gun_start")} → {time_gun_start}')
            if time_clear_start != existing.get('time_clear_start'):
                changed_fields.append(f'time_clear_start: {existing.get("time_clear_start")} → {time_clear_start}')
            if time_clear_finish != existing.get('time_clear_finish'):
                changed_fields.append(f'time_clear_finish: {existing.get("time_clear_finish")} → {time_clear_finish}')
            
            if not changed_fields:
                continue
            
            # Логирование изменений (только первые 2 для каждого цикла)
            if len(updated_dorsals) < 2:
                self.logger.debug(f"📝 Dorsal #{dorsal} ({surname} {name}): {', '.join(changed_fields)}")
            updated_dorsals.append(dorsal)
            
            # Добавляем в батч для UPDATE
            results_batch.append((
                surname, name, birthdate, sex, category, race_status,
                time_gun_start, time_clear_start, time_gun_finish, time_clear_finish,
                rank_absolute, rank_sex, rank_category, finish_pace_avg,
                time_clear_kt1, time_clear_kt2, time_clear_kt3, time_clear_kt4, time_clear_kt5,
                pace_avg_kt1, pace_avg_kt2, pace_avg_kt3, pace_avg_kt4, pace_avg_kt5,
                result_id
            ))
            
            # === СЕГМЕНТЫ ===
            segments = self._prepare_segments(result_id, runner)
            segments_batch.extend(segments)
            
            # Обновляем кэш
            self.existing_results[dorsal] = {
                'id': result_id,
                'surname': surname,
                'name': name,
                'birthday': birthdate,
                'sex': sex,
                'category': category,
                'race_status': race_status,
                'time_gun_start': time_gun_start,
                'time_clear_start': time_clear_start,
                'time_gun_finish': time_gun_finish,
                'time_clear_finish': time_clear_finish,
                'rank_absolute': rank_absolute,
                'rank_sex': rank_sex,
                'rank_category': rank_category,
                'finish_pace_avg': finish_pace_avg,
                'time_clear_kt1': time_clear_kt1,
                'time_clear_kt2': time_clear_kt2,
                'time_clear_kt3': time_clear_kt3,
                'time_clear_kt4': time_clear_kt4,
                'time_clear_kt5': time_clear_kt5,
                'pace_avg_kt1': pace_avg_kt1,
                'pace_avg_kt2': pace_avg_kt2,
                'pace_avg_kt3': pace_avg_kt3,
                'pace_avg_kt4': pace_avg_kt4,
                'pace_avg_kt5': pace_avg_kt5,
            }
        
        # Выполнить bulk UPDATE results
        updated_results = 0
        if results_batch:
            try:
                update_query = """
                    UPDATE results SET 
                        surname = %s, name = %s, birthday = %s, sex = %s, category = %s, 
                        race_status = %s, time_gun_start = %s, time_clear_start = %s, 
                        time_gun_finish = %s, time_clear_finish = %s,
                        rank_absolute = %s, rank_sex = %s, rank_category = %s, finish_pace_avg = %s,
                        time_clear_kt1 = %s, time_clear_kt2 = %s, time_clear_kt3 = %s, 
                        time_clear_kt4 = %s, time_clear_kt5 = %s,
                        pace_avg_kt1 = %s, pace_avg_kt2 = %s, pace_avg_kt3 = %s, 
                        pace_avg_kt4 = %s, pace_avg_kt5 = %s
                    WHERE id = %s
                """
                self.cursor.executemany(update_query, results_batch)
                self.connection.commit()
                updated_results = len(results_batch)
                self.updated_results_count += updated_results
            except Exception as e:
                self.logger.error(f"❌ UPDATE results: {e}")
                self.connection.rollback()
        
        # Выполнить bulk UPDATE/INSERT segments
        updated_segments = 0
        if segments_batch:
            try:
                insert_query = """
                    INSERT INTO result_segments (result_id, segment_code, sg_time_clear, sg_pace_avg, sg_rank_absolute, sg_rank_sex, sg_rank_category)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        sg_time_clear = VALUES(sg_time_clear),
                        sg_pace_avg = VALUES(sg_pace_avg),
                        sg_rank_absolute = VALUES(sg_rank_absolute),
                        sg_rank_sex = VALUES(sg_rank_sex),
                        sg_rank_category = VALUES(sg_rank_category)
                """
                self.cursor.executemany(insert_query, segments_batch)
                self.connection.commit()
                updated_segments = len(segments_batch)
                self.updated_segments_count += updated_segments
            except Exception as e:
                self.logger.error(f"❌ INSERT/UPDATE segments: {e}")
                self.connection.rollback()
        
        return updated_results, updated_segments
    
    def _prepare_segments(self, result_id: int, runner_data: Dict) -> List[Tuple]:
        """Подготовить данные сегментов"""
        segments = []
        
        # Все возможные сегменты
        segment_pairs = [
            ('start', 'kt1'), ('start', 'kt2'), ('start', 'kt3'),
            ('kt1', 'kt2'), ('kt1', 'kt3'), ('kt2', 'kt3'),
            ('start', 'finish'), ('kt1', 'finish'), ('kt2', 'finish'), ('kt3', 'finish')
        ]
        
        for from_point, to_point in segment_pairs:
            # Получить время FROM
            if from_point == 'start':
                from_ms = runner_data.get('times.real_:::start:::')
            else:
                from_ms = runner_data.get(f'times.real_{from_point}')
            
            # Получить время TO
            if to_point == 'finish':
                to_ms = runner_data.get('times.real_:::finish:::')
            else:
                to_ms = runner_data.get(f'times.real_{to_point}')
            
            # Пропустить если нет обоих времен
            if not from_ms or not to_ms:
                continue
            
            # Вычислить время сегмента
            segment_ms = to_ms - from_ms
            segment_time = milliseconds_to_time(segment_ms) if segment_ms > 0 else None
            
            if not segment_time:
                continue
            
            segment_code = f'{from_point}-{to_point}'
            
            # Получить темп и ранги для этого сегмента
            if to_point == 'finish':
                sg_pace = convert_pace_format(runner_data.get('netintervalaverages_:::full-1:::'))
                sg_rank_absolute = runner_data.get('netrankings_:::full-1:::')
                sg_rank_sex = runner_data.get('netrankings.gen_:::full-1:::')
                sg_rank_category = runner_data.get('netrankings.cat_:::full-1:::')
            else:
                sg_pace = convert_pace_format(runner_data.get(f'netintervalaverages_{to_point}'))
                sg_rank_absolute = runner_data.get(f'netrankings_{to_point}')
                sg_rank_sex = None  # Не расчитываются для промежуточных
                sg_rank_category = None
            
            segments.append((
                result_id,
                segment_code,
                segment_time,
                sg_pace,
                sg_rank_absolute,
                sg_rank_sex,
                sg_rank_category
            ))
        
        return segments
    
    def _bulk_insert(self, batch: List[Tuple]) -> int:
        """Bulk INSERT для новых результатов"""
        if not batch:
            return 0
        
        try:
            insert_query = """
                INSERT IGNORE INTO results (
                    event_id, start_number, surname, name, birthday,
                    sex, category, race_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            self.cursor.executemany(insert_query, batch)
            return self.cursor.rowcount
        except Exception as e:
            self.logger.error(f"❌ INSERT: {e}")
            return 0
    
    def close(self):
        """Закрыть соединение с БД"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()


# === MAIN ===
def main():
    parser = argparse.ArgumentParser(
        description='🏃 KRASMARAFON Race Loader v3.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:

  Режим INIT (первоначальная загрузка всех участников):
  $ python load_race_results.py --init --event-id 99

  Режим CONTINUOUS (непрерывное обновление):
  $ python load_race_results.py --event-id 99

  С кастомным интервалом обновления:
  $ python load_race_results.py --event-id 99 --interval 3

ВАЖНО:
  • INIT режим: Загружает всех участников один раз с "Not started"
  • CONTINUOUS режим: Постоянно обновляет все поля, работает до Ctrl+C
  • Логи: logs/race_loader_*.log
  • Credentials: .env файл (не выгружается на GitHub)
        """
    )
    
    parser.add_argument(
        '--event-id',
        type=int,
        required=True,
        help='🔴 ОБЯЗАТЕЛЬНЫЙ: ID события в БД'
    )
    
    parser.add_argument(
        '--init',
        action='store_true',
        help='Режим инициализации: загрузить всех участников один раз'
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=UPDATE_INTERVAL,
        help=f'Интервал обновления в сек (по умолчанию {UPDATE_INTERVAL})'
    )
    
    parser.add_argument(
        '--reset-cache',
        type=int,
        default=300,
        help='Интервал для автоматической перезагрузки кэша из БД (сек, по умолчанию 300)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Показывать DEBUG логи (какие поля изменяются)'
    )
    
    args = parser.parse_args()
    
    # Подготовить логирование
    logger = setup_logging(args.event_id)
    
    # Если --debug флаг, добавить DEBUG обработчик к логгеру
    if args.debug:
        # Уже все логирование на DEBUG уровне идет в файл, здесь просто информируем
        logger.info("🔧 DEBUG режим: будут показаны детали изменений")
    
    # Создать загрузчик
    loader = RaceLoader(event_id=args.event_id, logger=logger)
    
    try:
        # Подключиться к БД
        if not loader.connect():
            return 1
        
        # Загрузить данные из race_data.json
        runners = loader.load_race_data()
        if not runners:
            logger.error("❌ Нет данных для загрузки")
            return 1
        
        # Выбрать режим
        if args.init:
            if not loader.init_mode(runners):
                return 1
        else:
            loader.load_existing_results()
            loader.continuous_mode(runners, args.interval, args.reset_cache)
        
        return 0
    
    finally:
        loader.close()


if __name__ == '__main__':
    sys.exit(main())
