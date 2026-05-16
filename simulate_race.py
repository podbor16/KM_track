#!/usr/bin/env python3
"""
Симуляция забега event_id=106 для участника 9912 (Дедов Геннадий).
Проверяет автоматический пайплайн: запись времён → расчёт темпов → ранги → сегменты.

Запуск:
    conda run -n base python simulate_race.py

Структура теста:
    Фаза 1 (start)  — появляется gun_start (wave offset 0)
    Фаза 2 (kt1)    — приходит время на КТ1 (12:30 от старта)
    Фаза 3 (finish) — приходит время финиша (25:00 от старта)
"""

import sys
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Добавляем корень проекта в PATH
sys.path.insert(0, '.')

from load_race_results import RaceLoader, milliseconds_to_time

EVENT_ID = 106
DORSAL   = '9912'

# Preset-конфиг: говорим loader'у какие ключи в runner-dict использовать.
# gun_start/finish используют дефолтные ключи Copernico.
# kt1 — свой ключ 'kt1_ms'.
PRESET_CFG = {
    "time_fields": {},  # будут использованы дефолты: 'times.official_:::start:::', 'times.official_:::finish:::'
    "checkpoint_fields": {
        "kt1": "kt1_ms",
    },
}

# Фазы симуляции: каждая описывает состояние runner-dict на данном этапе.
# Времена в мс от момента выстрела (gun=0).
# Участник стартует с нулевой волновой задержкой (gun_start = 0).
PHASES = [
    {
        "name": "START",
        "desc": "Участник стартовал (gun_start = 0, нет КТ, нет финиша)",
        "runner": {
            "dorsal": DORSAL,
            "surname": "TEST_Дедов",
            "name": "Геннадий",
            "birthdate": "1940-01-01",
            "gender": "male",
            "status": "running",
            "times.official_:::start:::": 0,        # gun_start ms (wave offset 0)
            "times.official_:::finish:::": None,     # нет финиша
            "kt1_ms": None,                          # нет КТ
        },
    },
    {
        "name": "KT1",
        "desc": "Участник прошёл КТ1 (12:30 от старта, 2.5 км)",
        "runner": {
            "dorsal": DORSAL,
            "surname": "TEST_Дедов",
            "name": "Геннадий",
            "birthdate": "1940-01-01",
            "gender": "male",
            "status": "running",
            "times.official_:::start:::": 0,
            "times.official_:::finish:::": None,
            "kt1_ms": 12 * 60 * 1000 + 30 * 1000,  # 12:30 = 750 000 мс → темп 5:00/км
        },
    },
    {
        "name": "FINISH",
        "desc": "Участник финишировал (25:00 от старта, 5 км)",
        "runner": {
            "dorsal": DORSAL,
            "surname": "TEST_Дедов",
            "name": "Геннадий",
            "birthdate": "1940-01-01",
            "gender": "male",
            "status": "finished",
            "times.official_:::start:::": 0,
            "times.official_:::finish:::": 25 * 60 * 1000,  # 25:00 = 1 500 000 мс → темп 5:00/км
            "kt1_ms": 12 * 60 * 1000 + 30 * 1000,
        },
    },
]


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def query_runner_state(cursor, result_id: int) -> None:
    """Вывести текущее состояние записи участника в results."""
    cursor.execute("""
        SELECT
            race_status,
            time_gun_start, time_clear_start,
            time_clear_kt1, pace_avg_kt1,
            rank_absolute_kt1, rank_sex_kt1, rank_category_kt1,
            time_gun_finish, time_clear_finish,
            finish_pace_avg_gun, finish_pace_avg_clean,
            rank_absolute, rank_sex, rank_category,
            rank_absolute_clean, rank_sex_clean, rank_category_clean
        FROM results WHERE id = %s
    """, (result_id,))
    row = cursor.fetchone()
    if not row:
        print(f"  ⚠️  Запись с id={result_id} не найдена в results!")
        return

    def v(val):
        return str(val) if val is not None else "NULL"

    print("\n  [results]")
    print(f"    race_status          : {v(row['race_status'])}")
    print(f"    time_gun_start       : {v(row['time_gun_start'])}")
    print(f"    time_clear_start     : {v(row['time_clear_start'])}")
    print(f"    time_clear_kt1       : {v(row['time_clear_kt1'])}")
    print(f"    pace_avg_kt1         : {v(row['pace_avg_kt1'])}")
    print(f"    rank_absolute_kt1    : {v(row['rank_absolute_kt1'])}")
    print(f"    rank_sex_kt1         : {v(row['rank_sex_kt1'])}")
    print(f"    rank_category_kt1    : {v(row['rank_category_kt1'])}")
    print(f"    time_gun_finish      : {v(row['time_gun_finish'])}")
    print(f"    time_clear_finish    : {v(row['time_clear_finish'])}")
    print(f"    finish_pace_avg_gun  : {v(row['finish_pace_avg_gun'])}")
    print(f"    finish_pace_avg_clean: {v(row['finish_pace_avg_clean'])}")
    print(f"    rank_absolute        : {v(row['rank_absolute'])}")
    print(f"    rank_sex             : {v(row['rank_sex'])}")
    print(f"    rank_category        : {v(row['rank_category'])}")
    print(f"    rank_absolute_clean  : {v(row['rank_absolute_clean'])}")
    print(f"    rank_sex_clean       : {v(row['rank_sex_clean'])}")
    print(f"    rank_category_clean  : {v(row['rank_category_clean'])}")


def query_segments(cursor, result_id: int) -> None:
    """Вывести сегменты участника из result_segments."""
    cursor.execute("""
        SELECT segment_code, sg_time_clear, sg_time_gun, sg_pace_avg,
               sg_rank_absolute, sg_rank_sex, sg_rank_category
        FROM result_segments WHERE result_id = %s
        ORDER BY segment_code
    """, (result_id,))
    rows = cursor.fetchall()

    print(f"\n  [result_segments] ({len(rows)} записей)")
    if not rows:
        print("    Нет сегментов.")
        return
    for r in rows:
        def v(val): return str(val) if val is not None else "NULL"
        print(f"    {r['segment_code']:15s}  "
              f"clear={v(r['sg_time_clear'])}  "
              f"gun={v(r['sg_time_gun'])}  "
              f"pace={v(r['sg_pace_avg'])}  "
              f"rank_abs={v(r['sg_rank_absolute'])}  "
              f"rank_sex={v(r['sg_rank_sex'])}  "
              f"rank_cat={v(r['sg_rank_category'])}")


def validate_phase(phase_name: str, cursor, result_id: int) -> list:
    """Проверяет ожидаемые значения после каждой фазы. Возвращает список проблем."""
    issues = []
    cursor.execute("""
        SELECT race_status, time_gun_start, time_clear_kt1, pace_avg_kt1,
               rank_absolute_kt1, time_gun_finish, time_clear_finish,
               finish_pace_avg_gun, finish_pace_avg_clean, rank_absolute
        FROM results WHERE id = %s
    """, (result_id,))
    r = cursor.fetchone()
    if not r:
        return ["Запись не найдена"]

    cursor.execute("SELECT COUNT(*) AS cnt FROM result_segments WHERE result_id = %s", (result_id,))
    seg_count = cursor.fetchone()['cnt']

    if phase_name == "START":
        if r['race_status'] != 'Running':
            issues.append(f"race_status={r['race_status']}, ожидается Running")
        if r['time_gun_start'] is None:
            issues.append("time_gun_start = NULL, ожидается 00:00:00")
        if r['time_clear_kt1'] is not None:
            issues.append(f"time_clear_kt1={r['time_clear_kt1']}, ожидается NULL")
        if seg_count > 0:
            issues.append(f"result_segments = {seg_count}, ожидается 0 (нет завершённых сегментов)")

    elif phase_name == "KT1":
        if r['time_clear_kt1'] is None:
            issues.append("time_clear_kt1 = NULL, ожидается 00:12:30")
        if r['pace_avg_kt1'] is None:
            issues.append("pace_avg_kt1 = NULL, ожидается 00:05:00 (автоматический расчёт)")
        if r['rank_absolute_kt1'] is None:
            issues.append("rank_absolute_kt1 = NULL (ранги не пересчитались)")
        if seg_count == 0:
            issues.append("result_segments = 0, ожидается сегмент start-kt1")

    elif phase_name == "FINISH":
        if r['race_status'] != 'Finished':
            issues.append(f"race_status={r['race_status']}, ожидается Finished")
        if r['time_gun_finish'] is None:
            issues.append("time_gun_finish = NULL")
        if r['time_clear_finish'] is None:
            issues.append("time_clear_finish = NULL (должно вычислиться автоматически)")
        if r['finish_pace_avg_gun'] is None:
            issues.append("finish_pace_avg_gun = NULL (должно вычислиться автоматически)")
        if r['finish_pace_avg_clean'] is None:
            issues.append("finish_pace_avg_clean = NULL (должно вычислиться автоматически)")
        if r['rank_absolute'] is None:
            issues.append("rank_absolute = NULL (ранги не пересчитались)")
        if seg_count < 2:
            issues.append(f"result_segments = {seg_count}, ожидается ≥2 (start-kt1, kt1-finish)")

    return issues


def reset_participant(loader: RaceLoader) -> None:
    """Сбросить тестовые данные участника 9912 перед симуляцией."""
    cursor = loader.cursor
    conn   = loader.connection
    cursor.execute("SELECT id FROM results WHERE event_id=%s AND start_number=%s",
                   (EVENT_ID, int(DORSAL)))
    row = cursor.fetchone()
    if not row:
        print(f"  ⚠️  Участник {DORSAL} не найден в event {EVENT_ID}")
        return
    result_id = row['id']

    cursor.execute("""
        UPDATE results SET
            race_status='Running',
            time_gun_start=NULL, time_clear_start=NULL,
            time_clear_kt1=NULL, pace_avg_kt1=NULL,
            rank_absolute_kt1=NULL, rank_sex_kt1=NULL, rank_category_kt1=NULL,
            time_gun_finish=NULL, time_clear_finish=NULL,
            finish_pace_avg_gun=NULL, finish_pace_avg_clean=NULL,
            rank_absolute=NULL, rank_sex=NULL, rank_category=NULL,
            rank_absolute_clean=NULL, rank_sex_clean=NULL, rank_category_clean=NULL
        WHERE id=%s
    """, (result_id,))
    cursor.execute("DELETE FROM result_segments WHERE result_id=%s", (result_id,))
    conn.commit()
    print(f"  ✅ Участник {DORSAL} (id={result_id}) сброшен в нулевое состояние")


def get_result_id(cursor) -> int:
    cursor.execute("SELECT id FROM results WHERE event_id=%s AND start_number=%s",
                   (EVENT_ID, int(DORSAL)))
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"Участник {DORSAL} не найден в event {EVENT_ID}")
    return row['id']


def main():
    # Настройка логгера
    logging.basicConfig(level=logging.WARNING)
    logger = logging.LoggerAdapter(logging.getLogger("sim"), {"event_id": EVENT_ID})

    print_section(f"СИМУЛЯЦИЯ ЗАБЕГА event_id={EVENT_ID} — участник №{DORSAL}")
    print("Цель: проверить автоматический расчёт темпов, рангов и сегментов\n")

    # Создаём и подключаем loader
    loader = RaceLoader(
        event_id=EVENT_ID,
        logger=logger,
        preset_cfg=PRESET_CFG,
    )
    if not loader.connect():
        print("❌ Не удалось подключиться к БД")
        sys.exit(1)

    result_id = get_result_id(loader.cursor)
    print(f"✅ Подключено. Участник №{DORSAL} → result_id={result_id}")
    print(f"   checkpoint_distances: {loader.checkpoint_distances}")

    # Сброс тестовых данных
    print_section("СБРОС ДАННЫХ")
    reset_participant(loader)

    # Загружаем кэш существующих результатов (нужен для _update_existing)
    loader.load_existing_results()

    # Принудительно строим KT-маппинг из preset_cfg
    loader._kt_fields = loader._build_kt_field_map_from_preset()

    all_issues: dict = {}

    # === Прогон по фазам ===
    for phase in PHASES:
        phase_name = phase["name"]
        print_section(f"ФАЗА: {phase_name}")
        print(f"  {phase['desc']}")

        # Обработка через реальный метод пайплайна
        updated_r, updated_s, kt_reads = loader._update_existing([phase["runner"]])
        print(f"\n  _update_existing → results_updated={updated_r}, segments_updated={updated_s}, kt_reads={kt_reads}")

        # Пересчёт рангов (финишных и на КТ)
        loader._recalculate_ranks()
        print("  _recalculate_ranks() → выполнен")

        # Пересчёт рангов по сегментам
        loader._recalculate_segment_ranks()
        print("  _recalculate_segment_ranks() → выполнен")

        # Вывод текущего состояния БД
        query_runner_state(loader.cursor, result_id)
        query_segments(loader.cursor, result_id)

        # Валидация
        issues = validate_phase(phase_name, loader.cursor, result_id)
        all_issues[phase_name] = issues
        if issues:
            print(f"\n  ⚠️  ПРОБЛЕМЫ ({len(issues)}):")
            for iss in issues:
                print(f"     ❌ {iss}")
        else:
            print(f"\n  ✅ Все проверки прошли")

    # === Итоговый отчёт ===
    print_section("ИТОГОВЫЙ АУДИТ-ОТЧЁТ")

    total_issues = sum(len(v) for v in all_issues.values())
    if total_issues == 0:
        print("\n✅ Пайплайн работает корректно — всё автоматически.\n")
    else:
        print(f"\n❌ Обнаружено проблем: {total_issues}\n")

    for phase_name, issues in all_issues.items():
        status = "✅" if not issues else "❌"
        print(f"\n  {status} Фаза {phase_name}:")
        if not issues:
            print("     Всё корректно.")
        for iss in issues:
            print(f"     ❌ {iss}")

    print("\n--- Справка по ожиданиям ---")
    print("  START  : race_status=Running, time_gun_start=00:00:00, нет КТ/финиша/сегментов")
    print("  KT1    : time_clear_kt1=00:12:30, pace_avg_kt1=00:05:00 (авто), rank_kt1 заполнен (авто)")
    print("           result_segments: start-kt1 создан (авто)")
    print("  FINISH : race_status=Finished, time_clear_finish=00:25:00 (авто)")
    print("           finish_pace_avg_gun=00:05:00 (авто), finish_pace_avg_clean=00:05:00 (авто)")
    print("           rank_absolute заполнен (авто)")
    print("           result_segments: start-kt1 + kt1-finish + start-finish созданы (авто)")

    # Закрыть соединение
    try:
        if loader.cursor:
            loader.cursor.close()
        if loader.connection:
            loader.connection.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
