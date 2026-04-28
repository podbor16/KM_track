#!/usr/bin/env python3
"""
🏃 KRASMARAFON RACE LOADER v3.4 - COPERNICO INTEGRATION (fixed)
Загружает и обновляет результаты забега из системы хронометража Copernico.
"""

import sys

# UTF-8 вывод в консоль на Windows — должен быть ДО любых других импортов
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import time
import logging
import argparse
import re
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import os

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

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

from src.analytics.db_connection_optimized import create_connection, calculate_age_group

# === КОНСТАНТЫ ===
RACE_DATA_FILE = Path(os.getenv("RACE_DATA_FILE", "src/tracker/race_data.json"))
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
UPDATE_INTERVAL = int(os.getenv("CONTINUOUS_UPDATE_INTERVAL", "5"))
BATCH_SIZE = 1000

LOG_DIR.mkdir(exist_ok=True)


# === КОНФИГ СОБЫТИЙ ===
def _load_event_config(config_path: str, distance: str) -> Dict[str, Any]:
    """Загружает конфиг дистанции из YAML-файла события.

    Args:
        config_path: путь к YAML (напр. config/events/night_run.yaml)
        distance: строка дистанции (напр. "5 км")

    Returns:
        dict дистанции с полями: db_event_id, copernico, gpx_file, и т.д.
    """
    if not _YAML_AVAILABLE:
        raise ImportError("PyYAML не установлен. Выполните: pip install pyyaml")

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Конфиг не найден: {config_path}")

    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    distances = cfg.get("distances") or []
    for dist_cfg in distances:
        if dist_cfg.get("distance") == distance:
            # Добавляем поля верхнего уровня для удобства
            dist_cfg["event_name"] = cfg.get("name")
            dist_cfg["event_display_name"] = cfg.get("display_name") or cfg.get("name")
            dist_cfg["event_code"] = cfg.get("code")
            dist_cfg["event_year"] = cfg.get("year")
            return dist_cfg

    available = [d.get("distance") for d in distances]
    raise ValueError(
        f"Дистанция '{distance}' не найдена в {config_path}. "
        f"Доступные: {available}"
    )


# === МАРШРУТИЗАЦИЯ ===
def _setup_db_route(db_host: str, gateway: str) -> bool:
    """Добавляет Windows-маршрут для сервера БД в обход VPN."""
    import subprocess
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("WARN: Нет прав администратора - маршрут не добавлен. Запустите от имени администратора.")
        return False
    result = subprocess.run(
        ["route", "add", db_host, "mask", "255.255.255.255", gateway],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"INFO: Маршрут добавлен: {db_host} -> {gateway}")
        return True
    else:
        print(f"WARN: Не удалось добавить маршрут {db_host}: {result.stderr.strip()}")
        return False


def _cleanup_db_route(db_host: str) -> None:
    """Удаляет маршрут для сервера БД."""
    import subprocess
    subprocess.run(["route", "delete", db_host], capture_output=True)
    print(f"INFO: Маршрут удален: {db_host}")


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

    # Console handler (encoding='utf-8' чтобы кириллика не ломалась на Windows)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logging.LoggerAdapter(logger, {'event_id': event_id})


# === КОНВЕРТЕРЫ ===
def milliseconds_to_time(ms: Optional[int]) -> Optional[str]:
    """Конвертировать миллисекунды в HH:MM:SS с ведущими нулями"""
    if ms is None:
        return None
    if ms == 0:
        return '00:00:00'
    try:
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f'{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}'
    except (TypeError, ValueError):
        return None


def convert_pace_format(pace_str: Optional[str]) -> Optional[str]:
    """Конвертировать темп из формата JSON (м'сс"/км) в ЧЧ:ММ:СС, где ЧЧ всегда 00"""
    if not pace_str or str(pace_str).lower() == 'null':
        return None
    try:
        match = re.search(r"(\d{1,2})'(\d{2})", str(pace_str))
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            return f"00:{minutes:02d}:{seconds:02d}"
    except (ValueError, AttributeError):
        pass
    return None


def compute_pace(seconds_km: float) -> Optional[str]:
    """Конвертирует секунды на километр в строку 'ЧЧ:ММ:СС' (часы всегда 00)"""
    if seconds_km is None or seconds_km <= 0:
        return None
    minutes = int(seconds_km // 60)
    seconds = int(seconds_km % 60)
    return f"00:{minutes:02d}:{seconds:02d}"


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


def normalize_time(t: Optional[str]) -> Optional[str]:
    """Приводит строку времени HH:MM:SS к формату с ведущими нулями (02:05:36)"""
    if t is None:
        return None
    if isinstance(t, str):
        parts = t.split(':')
        if len(parts) == 3:
            try:
                return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
            except ValueError:
                pass
    return t


def _time_str_to_seconds(t: Optional[str]) -> Optional[float]:
    """'HH:MM:SS' → total seconds. None если невалидно или None."""
    if not t:
        return None
    parts = t.split(':')
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except (ValueError, TypeError):
        return None


def _seconds_to_pace(total_seconds: Optional[float], distance_km: Optional[float]) -> Optional[str]:
    """total_sec / dist_km → '00:mm:ss' темп для хранения в MySQL TIME. None если данных нет."""
    if not total_seconds or not distance_km or distance_km <= 0:
        return None
    secs_per_km = total_seconds / distance_km
    minutes = int(secs_per_km // 60)
    seconds = int(secs_per_km % 60)
    return f"00:{minutes:02d}:{seconds:02d}"


# === КЛАСС ЗАГРУЗЧИКА ===
class RaceLoader:
    """Оптимизированный загрузчик результатов в двух режимах"""

    def __init__(self, event_id: int, logger: logging.LoggerAdapter,
                 copernico_race_id: Optional[str] = None,
                 copernico_login: Optional[str] = None,
                 copernico_preset: Optional[str] = None,
                 copernico_event: Optional[str] = None):
        self.event_id = event_id
        self.logger = logger
        self.connection = None
        self.cursor = None
        self.existing_results: Dict[str, Dict] = {}
        self.inserted_count = 0
        self.updated_results_count = 0
        self.updated_segments_count = 0
        self.update_cycles = 0

        # Данные о событии (дистанция, массив дистанций КТ)
        self.event_distance_km: Optional[float] = None
        self.checkpoint_distances: Optional[List[float]] = None

        # Параметры Copernico API
        self.copernico_race_id = copernico_race_id
        self.copernico_login = copernico_login
        self.copernico_preset = copernico_preset
        self.copernico_event = copernico_event
        self.gun_time_utc: Optional[str] = None

    def connect(self) -> bool:
        """Подключиться к БД и получить данные о событии"""
        self.logger.info("🔌 Подключение к БД...")

        try:
            self.connection = create_connection()
            self.cursor = self.connection.cursor(dictionary=True)

            # Проверить событие
            self.cursor.execute(
                "SELECT id, event_name, event_distance, checkpoint_distances FROM events WHERE id = %s",
                (self.event_id,)
            )
            event = self.cursor.fetchone()
            if not event:
                self.logger.error(f"❌ События ID {self.event_id} не найдено в БД")
                return False

            # Преобразуем дистанцию в число
            self.event_distance_km = float(event['event_distance']) if event['event_distance'] else None
            if self.event_distance_km is None or self.event_distance_km <= 0:
                self.logger.error(f"❌ Некорректная дистанция для события {self.event_id}")
                return False

            # Разбираем JSON checkpoint_distances
            if event['checkpoint_distances']:
                try:
                    self.checkpoint_distances = json.loads(event['checkpoint_distances'])
                    if not isinstance(self.checkpoint_distances, list):
                        self.logger.error("❌ checkpoint_distances не является списком")
                        return False
                except json.JSONDecodeError:
                    self.logger.error("❌ Ошибка разбора checkpoint_distances")
                    return False
            else:
                self.checkpoint_distances = [0.0, self.event_distance_km]

            self.logger.info(f"✅ Подключено. Событие: {event['event_name']} ({self.event_distance_km} км)")
            self.logger.info(f"📌 Контрольные точки: {self.checkpoint_distances}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения: {e}")
            return False

    def fetch_from_copernico(self) -> List[Dict]:
        """Получить данные из Copernico API."""
        if not all([self.copernico_race_id, self.copernico_login, self.copernico_preset, self.copernico_event]):
            self.logger.error("❌ Не заданы все параметры Copernico API")
            return []

        encoded_preset = urllib.parse.quote(self.copernico_preset)
        encoded_event = urllib.parse.quote(self.copernico_event)
        url = f"https://public-api.copernico.cloud/api/races/{self.copernico_race_id}/preset/{self.copernico_login}:::{encoded_preset}/{encoded_event}"
        self.logger.info(f"📡 Запрос к Copernico API: {url}")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                self.logger.debug(f"Ответ API: {data}")
                if isinstance(data, dict) and 'data' in data:
                    runners = data['data']
                    self.gun_time_utc = data.get('gunTime')
                elif isinstance(data, list):
                    runners = data
                else:
                    self.logger.error(f"❌ Неожиданный формат ответа: {type(data)}")
                    return []
                self.logger.info(f"✅ Получено {len(runners)} участников из API")
                return runners
        except Exception as e:
            self.logger.error(f"❌ Ошибка при запросе к API: {e}")
            return []

    def load_race_data(self) -> List[Dict]:
        """Получить данные (из API или из файла) и обновить JSON."""
        # Если указаны параметры Copernico, пытаемся получить из API
        if self.copernico_race_id and self.copernico_login and self.copernico_preset and self.copernico_event:
            try:
                runners = self.fetch_from_copernico()
                # Если запрос выполнился (даже пустой список) – используем результат
                if runners is not None:
                    # Сохраняем в файл для истории
                    try:
                        with open(RACE_DATA_FILE, 'w', encoding='utf-8') as f:
                            json.dump({"data": runners, "last_updated": datetime.now().isoformat()}, f,
                                      ensure_ascii=False, indent=2)
                        self.logger.info(f"💾 Данные сохранены в {RACE_DATA_FILE}")
                    except Exception as e:
                        self.logger.error(f"❌ Ошибка сохранения JSON: {e}")
                    if self.gun_time_utc and self.cursor:
                        try:
                            self.cursor.execute(
                                "UPDATE events SET gun_time_utc = %s WHERE id = %s",
                                (self.gun_time_utc, self.event_id)
                            )
                            self.connection.commit()
                            self.logger.info(f"🕐 gun_time_utc сохранён: {self.gun_time_utc}")
                        except Exception as e:
                            self.logger.warning(f"⚠️ Не удалось сохранить gun_time_utc: {e}")
                    return runners
            except Exception as e:
                self.logger.warning(f"⚠️ Не удалось получить данные из API: {e}, пробуем читать из файла...")
        # Читаем из файла (резервный вариант)
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
        """Загрузить существующие результаты в кэш с нормализацией времен"""
        if self.cursor is None:
            self.logger.error("❌ Нет курсора БД")
            return

        self.logger.info(f"⏳ Загрузка существующих результатов в кэш...")
        try:
            self.cursor.execute(
                """SELECT id, start_number, surname, name, birthday, sex, category, 
                        race_status, time_gun_start, time_clear_start, time_gun_finish, 
                        time_clear_finish, rank_absolute, rank_sex, rank_category, 
                        finish_pace_avg_gun, finish_pace_avg_clean,
                        time_clear_kt1, time_clear_kt2, time_clear_kt3,
                        time_clear_kt4, time_clear_kt5, time_clear_kt6, time_clear_kt7,
                        pace_avg_kt1, pace_avg_kt2, pace_avg_kt3, pace_avg_kt4, pace_avg_kt5,
                        pace_avg_kt6, pace_avg_kt7
                FROM results WHERE event_id = %s""",
                (self.event_id,)
            )
            self.existing_results = {}
            for row in self.cursor.fetchall():
                row_dict = dict(row)
                for field in ['time_gun_start', 'time_clear_start', 'time_gun_finish', 'time_clear_finish']:
                    row_dict[field] = normalize_time(row_dict.get(field))
                for kt in ['time_clear_kt1', 'time_clear_kt2', 'time_clear_kt3', 'time_clear_kt4', 'time_clear_kt5', 'time_clear_kt6', 'time_clear_kt7']:
                    if row_dict.get(kt) is not None:
                        row_dict[kt] = normalize_time(row_dict[kt])

                if row_dict.get('start_number') is not None:
                    dorsal = str(row_dict['start_number'])
                    self.existing_results[dorsal] = row_dict
                else:
                    self.logger.warning(f"⚠️ Пропущен участник {row_dict['surname']} {row_dict['name']} из-за отсутствия start_number")
            self.logger.info(f"✅ Кэш загружен: {len(self.existing_results)} результатов")
        except Exception as e:
            self.logger.error(f"❌ Ошибка кэша: {e}")

    def init_mode(self, runners: List[Dict]) -> bool:
        """РЕЖИМ INIT: Загрузить один раз всех участников с INSERT"""
        if self.cursor is None:
            self.logger.error("❌ Нет курсора БД")
            return False

        self.logger.info("\n" + "="*70)
        self.logger.info("🚀 РЕЖИМ ИНИЦИАЛИЗАЦИИ (--init)")
        self.logger.info("="*70)
        self.logger.info(f"Загрузка {len(runners)} участников в БД...")

        batch = []
        start_time = time.time()

        try:
            for idx, runner in enumerate(runners, 1):
                dorsal = runner.get('dorsal')
                surname = (runner.get('surname') or '').strip()
                name = (runner.get('name') or '').strip()
                birthdate = runner.get('birthdate')

                if not dorsal or not surname or not name or not birthdate:
                    continue

                batch.append((
                    self.event_id,
                    str(dorsal),
                    surname,
                    name,
                    birthdate,
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

            if self.connection:
                self.connection.commit()

            self._recalculate_ranks()
            self._recalculate_segment_ranks()
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка INIT: {e}")
            if self.connection:
                self.connection.rollback()
            return False

    def continuous_mode(self, runners: List[Dict], interval: int, reset_cache_interval: int = 15) -> None:
        """РЕЖИМ CONTINUOUS: Постоянное обновление до Ctrl+C"""
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

                if time.time() - last_cache_reload > reset_cache_interval:
                    self.logger.debug("🔄 Перезагрузка кэша из БД...")
                    self.load_existing_results()
                    last_cache_reload = time.time()

                t_fetch = time.time()
                runners = self.load_race_data()
                fetch_t = time.time() - t_fetch

                if not runners:
                    self.logger.warning("⚠️ Ошибка получения данных, повторим...")
                    time.sleep(interval)
                    continue

                t_calc = time.time()
                updated_r, updated_s = self._update_existing(runners)
                calc_t = time.time() - t_calc

                t_rank = time.time()
                self._recalculate_ranks()
                self._recalculate_segment_ranks()
                rank_t = time.time() - t_rank

                cycle_time = time.time() - cycle_start
                if updated_r > 0:
                    self.logger.info(
                        f"Цикл #{self.update_cycles}: "
                        f"fetch={fetch_t:.2f}s calc={calc_t:.2f}s ranks={rank_t:.2f}s "
                        f"total={cycle_time:.2f}s | updated={updated_r}r/{updated_s}s"
                    )
                else:
                    self.logger.debug(
                        f"Цикл #{self.update_cycles}: "
                        f"fetch={fetch_t:.2f}s calc={calc_t:.2f}s ranks={rank_t:.2f}s "
                        f"total={cycle_time:.2f}s | 0 изменений"
                    )

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
        if self.cursor is None:
            self.logger.error("❌ Нет курсора БД")
            return 0, 0

        results_batch = []
        segments_batch = []
        updated_dorsals = []

        for runner in runners:
            dorsal = str(runner.get('dorsal'))

            if dorsal not in self.existing_results:
                self.logger.warning(f"⚠️ Участник с номером {dorsal} не найден в кэше (возможно, нет start_number в БД)")
                continue

            existing = self.existing_results[dorsal]
            result_id = existing['id']

            # === РЕЗУЛЬТАТЫ ===
            surname = (runner.get('surname') or '').strip()
            name = (runner.get('name') or '').strip()
            birthdate = runner.get('birthdate')
            sex = convert_gender(runner.get('gender'))
            # Категория вычисляется из года рождения и пола, не из Copernico
            category = calculate_age_group(birthdate, sex) or runner.get('category', 'Unknown')
            race_status = convert_status(runner.get('status'))

            # Времена
            time_gun_start = milliseconds_to_time(runner.get('times.official_:::start:::'))
            time_clear_start = milliseconds_to_time(runner.get('times.real_:::start:::'))
            time_gun_finish = milliseconds_to_time(runner.get('times.official_:::finish:::'))
            time_clear_finish = milliseconds_to_time(runner.get('times.real_:::finish:::'))

            # Темпы финиша — вычисляются из времён и дистанции
            finish_pace_avg_gun = _seconds_to_pace(
                _time_str_to_seconds(time_gun_finish), self.event_distance_km
            )
            finish_pace_avg_clean = _seconds_to_pace(
                _time_str_to_seconds(time_clear_finish), self.event_distance_km
            )

            # Времена КТ (чистые — chip time из Copernico)
            time_clear_kt1 = milliseconds_to_time(runner.get('times.real_kt1'))
            time_clear_kt2 = milliseconds_to_time(runner.get('times.real_kt2'))
            time_clear_kt3 = milliseconds_to_time(runner.get('times.real_kt3'))
            time_clear_kt4 = milliseconds_to_time(runner.get('times.real_kt4'))
            time_clear_kt5 = milliseconds_to_time(runner.get('times.real_kt5'))
            time_clear_kt6 = milliseconds_to_time(runner.get('times.real_kt6'))
            time_clear_kt7 = milliseconds_to_time(runner.get('times.real_kt7'))

            # Темпы КТ — вычисляются из чистого времени и дистанции до КТ
            kt_clear_times = [time_clear_kt1, time_clear_kt2, time_clear_kt3, time_clear_kt4, time_clear_kt5, time_clear_kt6, time_clear_kt7]
            pace_avg_kts = []
            for i, kt_time in enumerate(kt_clear_times):
                cp_idx = i + 1
                dist = self.checkpoint_distances[cp_idx] if self.checkpoint_distances and cp_idx < len(self.checkpoint_distances) else None
                pace_avg_kts.append(_seconds_to_pace(_time_str_to_seconds(kt_time), dist))
            pace_avg_kt1, pace_avg_kt2, pace_avg_kt3, pace_avg_kt4, pace_avg_kt5, pace_avg_kt6, pace_avg_kt7 = pace_avg_kts

            # === Сравнение всех полей ===
            changed_fields = []
            if surname != existing.get('surname'):
                changed_fields.append(f'surname: "{existing.get("surname")}" → "{surname}"')
            if name != existing.get('name'):
                changed_fields.append(f'name: "{existing.get("name")}" → "{name}"')
            if race_status != existing.get('race_status'):
                changed_fields.append(f'race_status: "{existing.get("race_status")}" → "{race_status}"')
            if time_gun_finish != existing.get('time_gun_finish'):
                changed_fields.append(f'time_gun_finish: {existing.get("time_gun_finish")} → {time_gun_finish}')
            if finish_pace_avg_gun != existing.get('finish_pace_avg_gun'):
                changed_fields.append(f'finish_pace_avg_gun: {existing.get("finish_pace_avg_gun")} → {finish_pace_avg_gun}')
            if finish_pace_avg_clean != existing.get('finish_pace_avg_clean'):
                changed_fields.append(f'finish_pace_avg_clean: {existing.get("finish_pace_avg_clean")} → {finish_pace_avg_clean}')
            if time_gun_start != existing.get('time_gun_start'):
                changed_fields.append(f'time_gun_start: {existing.get("time_gun_start")} → {time_gun_start}')
            if time_clear_start != existing.get('time_clear_start'):
                changed_fields.append(f'time_clear_start: {existing.get("time_clear_start")} → {time_clear_start}')
            if time_clear_finish != existing.get('time_clear_finish'):
                changed_fields.append(f'time_clear_finish: {existing.get("time_clear_finish")} → {time_clear_finish}')

            if changed_fields:
                updated_dorsals.append(dorsal)
                if len(updated_dorsals) <= 5:
                    self.logger.debug(f"📝 Dorsal #{dorsal} ({surname} {name}): {', '.join(changed_fields)}")
                # Добавляем в батч для UPDATE только если есть изменения
                # Ранги (rank_absolute/sex/category) управляются _recalculate_ranks()
                results_batch.append((
                    surname, name, birthdate, sex, category, race_status,
                    time_gun_start, time_clear_start, time_gun_finish, time_clear_finish,
                    finish_pace_avg_gun, finish_pace_avg_clean,
                    time_clear_kt1, time_clear_kt2, time_clear_kt3, time_clear_kt4, time_clear_kt5, time_clear_kt6, time_clear_kt7,
                    pace_avg_kt1, pace_avg_kt2, pace_avg_kt3, pace_avg_kt4, pace_avg_kt5, pace_avg_kt6, pace_avg_kt7,
                    result_id
                ))

            # === СЕГМЕНТЫ (всегда обновляем) ===
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
                'finish_pace_avg_gun': finish_pace_avg_gun,
                'finish_pace_avg_clean': finish_pace_avg_clean,
                'time_clear_kt1': time_clear_kt1,
                'time_clear_kt2': time_clear_kt2,
                'time_clear_kt3': time_clear_kt3,
                'time_clear_kt4': time_clear_kt4,
                'time_clear_kt5': time_clear_kt5,
                'time_clear_kt6': time_clear_kt6,
                'time_clear_kt7': time_clear_kt7,
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
                        finish_pace_avg_gun = %s, finish_pace_avg_clean = %s,
                        time_clear_kt1 = %s, time_clear_kt2 = %s, time_clear_kt3 = %s,
                        time_clear_kt4 = %s, time_clear_kt5 = %s, time_clear_kt6 = %s, time_clear_kt7 = %s,
                        pace_avg_kt1 = %s, pace_avg_kt2 = %s, pace_avg_kt3 = %s,
                        pace_avg_kt4 = %s, pace_avg_kt5 = %s, pace_avg_kt6 = %s, pace_avg_kt7 = %s
                    WHERE id = %s
                """
                self.cursor.executemany(update_query, results_batch)
                if self.connection:
                    self.connection.commit()
                updated_results = len(results_batch)
                self.updated_results_count += updated_results
                if updated_dorsals:
                    self.logger.debug(f"📝 Обновлены: {', '.join(updated_dorsals[:5])} (всего {len(updated_dorsals)})")
            except Exception as e:
                self.logger.error(f"❌ UPDATE results: {e}")
                if self.connection:
                    self.connection.rollback()

        # Выполнить bulk UPDATE/INSERT segments
        updated_segments = 0
        if segments_batch:
            try:
                insert_query = """
                    INSERT INTO result_segments
                        (result_id, event_id, segment_code, sg_time_clear, sg_time_gun, sg_pace_avg, sg_pace_avg_gun,
                         sg_rank_absolute, sg_rank_sex, sg_rank_category,
                         sg_rank_absolute_gun, sg_rank_sex_gun, sg_rank_category_gun)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        sg_time_clear = VALUES(sg_time_clear),
                        sg_time_gun = VALUES(sg_time_gun),
                        sg_pace_avg = VALUES(sg_pace_avg),
                        sg_pace_avg_gun = VALUES(sg_pace_avg_gun),
                        event_id = VALUES(event_id),
                        sg_rank_absolute = VALUES(sg_rank_absolute),
                        sg_rank_sex = VALUES(sg_rank_sex),
                        sg_rank_category = VALUES(sg_rank_category),
                        sg_rank_absolute_gun = VALUES(sg_rank_absolute_gun),
                        sg_rank_sex_gun = VALUES(sg_rank_sex_gun),
                        sg_rank_category_gun = VALUES(sg_rank_category_gun)
                """
                self.cursor.executemany(insert_query, segments_batch)
                if self.connection:
                    self.connection.commit()
                updated_segments = len(segments_batch)
                self.updated_segments_count += updated_segments
            except Exception as e:
                self.logger.error(f"❌ INSERT/UPDATE segments: {e}")
                if self.connection:
                    self.connection.rollback()

        return updated_results, updated_segments

    @staticmethod
    def _assign_ranks(runners: List[Dict], time_key: str) -> Dict[int, int]:
        """
        Назначает места (RANK) по возрастанию времени.
        Одинаковые времена получают одинаковое место; следующее место пропускается.
        Возвращает {result_id: rank}.
        """
        valid = [(r['id'], r[time_key]) for r in runners if r.get(time_key)]
        valid.sort(key=lambda x: x[1])
        ranks: Dict[int, int] = {}
        for i, (rid, t) in enumerate(valid):
            if i == 0 or t != valid[i - 1][1]:
                ranks[rid] = i + 1
            else:
                ranks[rid] = ranks[valid[i - 1][0]]
        return ranks

    def _recalculate_ranks(self) -> None:
        """
        Пересчитывает все места для event_id:
        - Финишные места (official/clean) в таблице results
        - Места на КТ (clean) в таблице result_segments
        """
        if self.cursor is None:
            return

        try:
            # --- Финишные места ---
            self.cursor.execute(
                """SELECT id, sex, category, time_gun_finish, time_clear_finish
                   FROM results
                   WHERE event_id = %s AND race_status = 'Finished'
                   AND time_gun_finish IS NOT NULL""",
                (self.event_id,)
            )
            finished = [dict(r) for r in self.cursor.fetchall()]

            if not finished:
                return

            # Официальные места (gun time)
            abs_gun = self._assign_ranks(finished, 'time_gun_finish')
            sex_gun: Dict[str, Dict[int, int]] = {}
            cat_gun: Dict[str, Dict[int, int]] = {}
            abs_clean: Dict[int, int] = {}
            sex_clean: Dict[str, Dict[int, int]] = {}
            cat_clean: Dict[str, Dict[int, int]] = {}

            for sex_val in set(r['sex'] for r in finished if r.get('sex')):
                group = [r for r in finished if r.get('sex') == sex_val]
                sex_gun[sex_val] = self._assign_ranks(group, 'time_gun_finish')

            for cat_val in set(r['category'] for r in finished if r.get('category')):
                group = [r for r in finished if r.get('category') == cat_val]
                cat_gun[cat_val] = self._assign_ranks(group, 'time_gun_finish')

            # Чистые места (clean time) — только если есть time_clear_finish
            with_clean = [r for r in finished if r.get('time_clear_finish')]
            abs_clean = self._assign_ranks(with_clean, 'time_clear_finish')

            for sex_val in set(r['sex'] for r in with_clean if r.get('sex')):
                group = [r for r in with_clean if r.get('sex') == sex_val]
                sex_clean[sex_val] = self._assign_ranks(group, 'time_clear_finish')

            for cat_val in set(r['category'] for r in with_clean if r.get('category')):
                group = [r for r in with_clean if r.get('category') == cat_val]
                cat_clean[cat_val] = self._assign_ranks(group, 'time_clear_finish')

            # Bulk UPDATE ranks
            rank_batch = []
            for r in finished:
                rid = r['id']
                sex_val = r.get('sex', '')
                cat_val = r.get('category', '')
                rank_batch.append((
                    abs_gun.get(rid),
                    sex_gun.get(sex_val, {}).get(rid),
                    cat_gun.get(cat_val, {}).get(rid),
                    abs_clean.get(rid),
                    sex_clean.get(sex_val, {}).get(rid),
                    cat_clean.get(cat_val, {}).get(rid),
                    rid,
                ))

            self.cursor.executemany(
                """UPDATE results SET
                       rank_absolute = %s, rank_sex = %s, rank_category = %s,
                       rank_absolute_clean = %s, rank_sex_clean = %s, rank_category_clean = %s
                   WHERE id = %s""",
                rank_batch,
            )
            self.connection.commit()
            self.logger.debug(f"🏆 Места пересчитаны: {len(rank_batch)} финишировавших")

            # --- Места на КТ ---
            kt_keys = ['kt1', 'kt2', 'kt3', 'kt4', 'kt5', 'kt6', 'kt7']
            for kt in kt_keys:
                time_col = f'time_clear_{kt}'
                self.cursor.execute(
                    f"""SELECT r.id, r.sex, r.category, r.{time_col}
                        FROM results r
                        WHERE r.event_id = %s AND r.{time_col} IS NOT NULL""",
                    (self.event_id,)
                )
                kt_runners = [dict(row) for row in self.cursor.fetchall()]
                if not kt_runners:
                    continue

                kt_abs = self._assign_ranks(kt_runners, time_col)
                kt_sex: Dict[str, Dict[int, int]] = {}
                kt_cat: Dict[str, Dict[int, int]] = {}

                for sex_val in set(r['sex'] for r in kt_runners if r.get('sex')):
                    group = [r for r in kt_runners if r.get('sex') == sex_val]
                    kt_sex[sex_val] = self._assign_ranks(group, time_col)

                for cat_val in set(r['category'] for r in kt_runners if r.get('category')):
                    group = [r for r in kt_runners if r.get('category') == cat_val]
                    kt_cat[cat_val] = self._assign_ranks(group, time_col)

                # Обновляем колонки rank_*_kt{i} в таблице results
                kt_batch = []
                seg_batch = []
                seg_code = f'start-{kt}'
                for r in kt_runners:
                    rid = r['id']
                    sex_val = r.get('sex', '')
                    cat_val = r.get('category', '')
                    ra = kt_abs.get(rid)
                    rs = kt_sex.get(sex_val, {}).get(rid)
                    rc = kt_cat.get(cat_val, {}).get(rid)
                    kt_batch.append((ra, rs, rc, rid))
                    seg_batch.append((ra, rs, rc, rid, seg_code))

                self.cursor.executemany(
                    f"""UPDATE results SET
                            rank_absolute_{kt} = %s,
                            rank_sex_{kt} = %s,
                            rank_category_{kt} = %s
                        WHERE id = %s""",
                    kt_batch,
                )
                self.cursor.executemany(
                    """UPDATE result_segments SET
                           sg_rank_absolute = %s, sg_rank_sex = %s, sg_rank_category = %s
                       WHERE result_id = %s AND segment_code = %s""",
                    seg_batch,
                )
                self.connection.commit()

        except Exception as e:
            self.logger.error(f"❌ _recalculate_ranks: {e}")
            if self.connection:
                self.connection.rollback()

    def _recalculate_segment_ranks(self) -> None:
        """Пересчитывает net и gun ранги для ВСЕХ сегментных комбинаций события."""
        if not self.cursor or not self.connection:
            return
        try:
            self.cursor.execute("""
                SELECT rs.id AS seg_id, rs.result_id, rs.segment_code,
                       rs.sg_time_clear, rs.sg_time_gun,
                       r.sex, r.category
                FROM result_segments rs
                JOIN results r ON rs.result_id = r.id
                WHERE rs.event_id = %s AND rs.sg_time_clear IS NOT NULL
            """, (self.event_id,))
            rows = [dict(row) for row in self.cursor.fetchall()]
            if not rows:
                return

            from collections import defaultdict
            by_code: Dict[str, list] = defaultdict(list)
            for row in rows:
                by_code[row['segment_code']].append({
                    'id':                    row['result_id'],
                    'seg_id':                row['seg_id'],
                    'sg_time_clear':         row['sg_time_clear'],
                    'sg_time_gun_effective': row['sg_time_gun'] or row['sg_time_clear'],
                    'sex':                   row['sex'],
                    'category':              row['category'],
                })

            batch = []
            for seg_code, segs in by_code.items():
                # Net ranks
                abs_ranks = self._assign_ranks(segs, 'sg_time_clear')
                sex_ranks: Dict[str, Dict[int, int]] = {}
                for sex_val in set(s['sex'] for s in segs if s.get('sex')):
                    sex_ranks[sex_val] = self._assign_ranks(
                        [s for s in segs if s.get('sex') == sex_val], 'sg_time_clear'
                    )
                cat_ranks: Dict[str, Dict[int, int]] = {}
                for cat_val in set(s['category'] for s in segs if s.get('category')):
                    cat_ranks[cat_val] = self._assign_ranks(
                        [s for s in segs if s.get('category') == cat_val], 'sg_time_clear'
                    )

                # Gun ranks (fallback to sg_time_clear where sg_time_gun is NULL)
                abs_ranks_gun = self._assign_ranks(segs, 'sg_time_gun_effective')
                sex_ranks_gun: Dict[str, Dict[int, int]] = {}
                for sex_val in set(s['sex'] for s in segs if s.get('sex')):
                    sex_ranks_gun[sex_val] = self._assign_ranks(
                        [s for s in segs if s.get('sex') == sex_val], 'sg_time_gun_effective'
                    )
                cat_ranks_gun: Dict[str, Dict[int, int]] = {}
                for cat_val in set(s['category'] for s in segs if s.get('category')):
                    cat_ranks_gun[cat_val] = self._assign_ranks(
                        [s for s in segs if s.get('category') == cat_val], 'sg_time_gun_effective'
                    )

                for seg in segs:
                    rid = seg['id']
                    sex_val = seg.get('sex', '')
                    cat_val = seg.get('category', '')
                    batch.append((
                        abs_ranks.get(rid),
                        sex_ranks.get(sex_val, {}).get(rid),
                        cat_ranks.get(cat_val, {}).get(rid),
                        abs_ranks_gun.get(rid),
                        sex_ranks_gun.get(sex_val, {}).get(rid),
                        cat_ranks_gun.get(cat_val, {}).get(rid),
                        seg['seg_id'],
                    ))

            if batch:
                self.cursor.executemany(
                    """UPDATE result_segments
                       SET sg_rank_absolute = %s, sg_rank_sex = %s, sg_rank_category = %s,
                           sg_rank_absolute_gun = %s, sg_rank_sex_gun = %s, sg_rank_category_gun = %s
                       WHERE id = %s""",
                    batch,
                )
                self.connection.commit()
                self.logger.debug(f"🏆 Ранги сегментов пересчитаны: {len(batch)} записей")
        except Exception as e:
            self.logger.error(f"❌ _recalculate_segment_ranks: {e}")
            if self.connection:
                self.connection.rollback()

    def _prepare_segments(self, result_id: int, runner_data: Dict) -> List[Tuple]:
        """Подготовить данные сегментов для всех пар точек из checkpoint_distances."""
        if self.checkpoint_distances is None:
            return []

        num_kt = len(self.checkpoint_distances) - 2
        point_names = ['start'] + [f'kt{i}' for i in range(1, num_kt + 1)] + ['finish']

        times: Dict[str, Optional[int]] = {
            'start': runner_data.get('times.real_:::start:::'),
            'finish': runner_data.get('times.real_:::finish:::'),
        }
        for i in range(1, num_kt + 1):
            times[f'kt{i}'] = runner_data.get(f'times.real_kt{i}')

        # Волновая задержка: время от выстрела до пересечения старта участником
        gun_offset_ms = runner_data.get('times.official_:::start:::') or 0

        segments = []
        for i in range(len(point_names)):
            for j in range(i + 1, len(point_names)):
                from_point = point_names[i]
                to_point = point_names[j]
                from_ms = times.get(from_point)
                to_ms = times.get(to_point)
                if from_ms is None or to_ms is None:
                    continue
                segment_ms = to_ms - from_ms
                if segment_ms <= 0:
                    continue
                segment_time = milliseconds_to_time(segment_ms)
                if not segment_time:
                    continue

                from_dist = self.checkpoint_distances[i]
                to_dist = self.checkpoint_distances[j]
                seg_dist = to_dist - from_dist
                if seg_dist <= 0:
                    continue

                sg_pace = compute_pace((segment_ms / 1000.0) / seg_dist)
                segment_code = f"{from_point}-{to_point}"

                # Официальное время: для первого сегмента (start-*) добавляем волновую задержку;
                # для внутренних сегментов смещение сокращается, gun == net.
                if from_point == 'start' and gun_offset_ms > 0:
                    gun_ms = segment_ms + gun_offset_ms
                    sg_time_gun = milliseconds_to_time(gun_ms)
                    sg_pace_gun = compute_pace((gun_ms / 1000.0) / seg_dist)
                else:
                    sg_time_gun = segment_time
                    sg_pace_gun = sg_pace

                segments.append((
                    result_id,
                    self.event_id,
                    segment_code,
                    segment_time,
                    sg_time_gun,
                    sg_pace,
                    sg_pace_gun,
                    None, None, None,   # sg_rank_absolute, sg_rank_sex, sg_rank_category
                    None, None, None,   # sg_rank_absolute_gun, sg_rank_sex_gun, sg_rank_category_gun
                ))

        return segments

    def _bulk_insert(self, batch: List[Tuple]) -> int:
        """Bulk INSERT для новых результатов"""
        if not batch or self.cursor is None:
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
        description='🏃 KRASMARAFON Race Loader v3.4',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:
  Режим INIT (первоначальная загрузка всех участников):
  $ python load_race_results.py --init --event-id 104

  Режим CONTINUOUS (непрерывное обновление):
  $ python load_race_results.py --event-id 104 --interval 2 --reset-cache 60

ВАЖНО:
  • INIT режим: Загружает всех участников один раз с "Not started"
  • CONTINUOUS режим: Постоянно обновляет все поля, работает до Ctrl+C
  • Логи: logs/race_loader_*.log
  • Credentials: .env файл
        """
    )

    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Путь к YAML-конфигу события (напр. config/events/night_run.yaml)'
    )

    parser.add_argument(
        '--distance',
        type=str,
        default=None,
        help='Дистанция из конфига (напр. "5 км"). Обязателен если задан --config'
    )

    parser.add_argument(
        '--event-id',
        type=int,
        required=False,
        default=None,
        help='ID события в БД. Обязателен если не задан --config'
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

    parser.add_argument(
        '--fix-routing',
        action='store_true',
        help='Добавить маршрут для БД в обход VPN (нужны права администратора)'
    )

    parser.add_argument(
        '--local-gateway',
        type=str,
        default=None,
        help='Локальный шлюз для --fix-routing (если не задан - читается из config/network.yaml)'
    )

    args = parser.parse_args()

    # Разрешаем параметры: --config имеет приоритет над --event-id + хардкодом
    if args.config:
        if not args.distance:
            parser.error("--distance обязателен при использовании --config (напр. --distance \"5 км\")")
        dist_cfg = _load_event_config(args.config, args.distance)
        event_id = dist_cfg.get("db_event_id") or args.event_id
        if not event_id:
            parser.error(
                f"db_event_id не задан в {args.config} для дистанции '{args.distance}' "
                "и не передан через --event-id"
            )
        cop = dist_cfg.get("copernico") or {}
        copernico_race_id = cop.get("race_id")
        copernico_login   = cop.get("login", "podbor250718@gmail.com")
        copernico_preset  = cop.get("preset", "km_analytics")
        copernico_event   = cop.get("event", args.distance)
    else:
        # Обратная совместимость: --event-id + хардкод
        if not args.event_id:
            parser.error("Необходимо указать --config или --event-id")
        event_id          = args.event_id
        copernico_race_id = "--2026-67178"
        copernico_login   = "podbor250718@gmail.com"
        copernico_preset  = "km_analytics"
        copernico_event   = "5 км"

    # Маршрутизация: обход VPN для доступа к БД
    if args.fix_routing:
        gateway = args.local_gateway
        if not gateway:
            net_cfg_path = Path("config/network.yaml")
            if net_cfg_path.exists() and _YAML_AVAILABLE:
                net_cfg = yaml.safe_load(net_cfg_path.read_text(encoding='utf-8'))
                gateway = net_cfg.get('local_gateway')
        if gateway:
            from src.config.settings import DB_HOST
            if _setup_db_route(DB_HOST, gateway):
                import atexit
                atexit.register(_cleanup_db_route, DB_HOST)
        else:
            print("WARN: --fix-routing задан, но local_gateway не найден. Добавьте в config/network.yaml.")

    # Подготовить логирование
    logger = setup_logging(event_id)

    if args.debug:
        logger.info("🔧 DEBUG режим: будут показаны детали изменений")
    if args.config:
        logger.info(f"📋 Конфиг: {args.config} | дистанция: {args.distance} | event_id: {event_id}")

    # Создать загрузчик
    loader = RaceLoader(
        event_id=event_id,
        logger=logger,
        copernico_race_id=copernico_race_id,
        copernico_login=copernico_login,
        copernico_preset=copernico_preset,
        copernico_event=copernico_event
    )

    try:
        if not loader.connect():
            return 1

        # Первая загрузка данных (из API или файла)
        runners = loader.load_race_data()
        if not runners:
            logger.error("❌ Нет данных для загрузки")
            return 1

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