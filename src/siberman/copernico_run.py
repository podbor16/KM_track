"""
Live-опрос Copernico для бегового этапа Siberman (задача 6 Live v2,
config/copernico/siberman2026.yaml). НЕ использует apply_to_db()/
clear_race_year() — точечный upsert checkpoint_times по уже существующим
участникам (стартовый список загружается заранее обычным Excel-путём,
этот модуль новых участников не создаёт). Причина: соединение открывается
с autocommit=True (db.py:get_siberman_connection) — DELETE в
clear_race_year() коммитится немедленно, до повторной вставки; гонять
такое каждые 15-30с весь день гонки заставило бы публичную страницу
на долю секунды показывать пустую таблицу на каждом цикле опроса.

⚠ ВАЖНО (операционное ограничение, не устранено в этой версии): apply_to_db()
(Excel-путь) по-прежнему делает полный clear_race_year() + пересборку
участников с НОВЫМИ id — если во время активной live-синхронизации
запустить обычный Excel apply (для любого этапа, не только бега), это
сотрёт все уже собранные Copernico-данные бега. Правило на день гонки:
не запускать Excel apply, пока Copernico включён в админке; если нужно
скорректировать данные другого этапа — сначала выключить тумблер.

2026-08-06: основной способ опроса — встроенный лидер-цикл в app.py
(lifespan, _siberman_copernico_run_poller), который крутится всегда во
всех воркерах и сам проверяет race_config.copernico_run_enabled на
каждой итерации — кнопки "Включить"/"Выключить" в админке буквально
запускают/останавливают опрос, без SSH. copernico_run_poller.py
(отдельный CLI-процесс) остаётся как fallback для локальной отладки без
Redis — не запускать его одновременно с продовым приложением (двойной
опрос, не критично благодаря upsert-семантике, но лишняя нагрузка).
"""
import datetime
import logging
import urllib.parse
from typing import Optional

import requests
import yaml

from src.siberman.db import (
    get_checkpoints, get_participants_for_year, get_checkpoint_times_for_year,
    get_stage_starts, upsert_checkpoint_time, update_participant_status,
    get_copernico_run_enabled,
)
from src.siberman.service import recompute_totals_ranks_records

log = logging.getLogger(__name__)

# Тот же словарь, что для Красмарафона (load_race_results.py:197-210,
# convert_status()) — Copernico использует единый набор статусов на всех
# гонках. В Siberman-схеме нет отдельного "Finished"/"Running" статуса —
# всё это 'active' (ещё не закончил/идёт/успешно закончил сегмент), важно
# различаются только dnf/dsq. 'withdrawn' трактуем как dnf (ближайший
# аналог в 4-значном enum active/dnf/dns/dsq).
STATUS_MAP: dict[str, tuple[str, Optional[str]]] = {
    "notstarted": ("active", None),
    "running":    ("active", None),
    "finished":   ("active", None),
    "dnf":        ("dnf", "run"),
    "dsq":        ("dsq", None),
    "withdrawn":  ("dnf", "run"),
}


def load_preset_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_run_snapshot(cfg: dict) -> list[dict]:
    """Обычный GET к Copernico, без токена — как load_race_results.py:374-411.
    При любой ошибке возвращает [] (не падает) — с backoff разбирается сам
    цикл опроса, см. copernico_run_poller.py."""
    login = cfg["login"]
    race_id = cfg["race_id"]
    preset = urllib.parse.quote(cfg["preset"])
    event = urllib.parse.quote(cfg["event"])
    url = f"https://public-api.copernico.cloud/api/races/{race_id}/preset/{login}:::{preset}/{event}"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=(10, 60))
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning(f"Copernico fetch failed: {e}")
        return []


def _fmt_km(km: float) -> str:
    return str(int(km)) if km == int(km) else str(km)


def _lap_fields(cfg: dict) -> list[tuple[int, str]]:
    """[(seq, field_name), ...] — 12 круговых (seq 1..12, последний —
    finish_field вместо "84km") + 12 субметок "-500м до круга" (seq
    101..112, см. миграцию 009)."""
    laps = cfg["laps"]
    count = laps["count"]
    lap_km = laps["lap_km"]
    out: list[tuple[int, str]] = []
    for n in range(1, count + 1):
        km = lap_km * n
        sub_km = km - 0.5  # "-500м до круга", не половина круга
        out.append((100 + n, laps["submark_field_pattern"].format(km=_fmt_km(sub_km))))
        boundary_field = laps["finish_field"] if n == count else laps["boundary_field_pattern"].format(km=_fmt_km(km))
        out.append((n, boundary_field))
    return out


def _parse_copernico_elapsed_ms(raw) -> Optional[int]:
    """times.official_* у Copernico — ЦЕЛОЕ ЧИСЛО миллисекунд, прошедших от
    старта забега, а НЕ ISO8601-таймстамп, как предполагалось на этапе
    дизайна интеграции (см. комментарий про gunTime выше и старую
    _parse_copernico_timestamp). Подтверждено первым живым fetch на
    реальном забеге 2026-08-08: значения вида 1895002 соответствуют ~31
    минуте бега — ровно то время, что прошло с 08:30 (run_start) для
    участников, которых поллер опросил в этот момент. Из-за неверного
    предположения о формате ни одна беговая КТ не записывалась ни разу с
    начала этапа (fromisoformat ловил ValueError на каждой отметке)."""
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as e:
        log.warning(f"Copernico: не удалось распознать отметку времени {raw!r} (ожидалось целое число миллисекунд): {e}")
        return None


def apply_copernico_snapshot(conn, race_year: int, runners: list[dict], cfg: dict) -> dict:
    """Точечно записать снапшот Copernico в checkpoint_times стадии 'run'
    (без clear_race_year) и пересчитать totals/ranks/records. Возвращает
    статистику применения; не бросает исключений на отдельных "плохих"
    записях — пропускает их с логом, чтобы одна битая строка не роняла
    весь батч (défense-in-depth, формат Copernico-таймстампов ещё не
    проверен на реальных живых данных, см. план)."""
    if not get_copernico_run_enabled(conn, race_year):
        log.info(f"Copernico live для race_year={race_year} выключен в админке — снапшот пропущен")
        return {"ok": True, "enabled": False, "checkpoint_writes": 0, "status_updates": 0, "skipped": 0}

    fields = cfg["fields"]
    relay_cfg = cfg.get("relay", {})

    stage_starts = get_stage_starts(conn, race_year)
    run_start = stage_starts.get("run_start")
    if run_start is None:
        log.warning(f"race_config.run_start не задан для {race_year} — пропускаю снапшот Copernico")
        return {"ok": False, "error": "run_start not set"}

    checkpoints = get_checkpoints(conn, race_year)
    cp_id_map = {(row["stage"], row["seq"]): row["id"] for row in checkpoints if row["stage"] == "run"}
    lap_fields = _lap_fields(cfg)

    participants = get_participants_for_year(conn, race_year)
    by_key = {(p["bib"], p["relay_stage"]): p for p in participants}

    checkpoint_writes = 0
    status_updates = 0
    skipped = 0

    for runner in runners:
        raw_bib = runner.get(fields["bib"])
        if raw_bib is None:
            skipped += 1
            continue
        bib = str(raw_bib)
        category = runner.get(fields.get("category"))
        is_relay = category == relay_cfg.get("category_value")
        relay_stage = "run" if is_relay else "none"

        participant = by_key.get((bib, relay_stage))
        if participant is None:
            log.warning(f"Copernico: нет участника bib={bib} relay_stage={relay_stage} в БД (race_year={race_year})")
            skipped += 1
            continue
        pid = participant["id"]

        # Сначала считаем cumulative_s для ВСЕХ КТ этого участника (круговые
        # 1..12 + субметки 101..112), чтобы затем посчитать split_s кругового
        # seq как разницу с cumulative[seq-1] — та же логика, что уже
        # используется для Google Sheet источника (см. apply_race_result в
        # service.py). Раньше split_s писался как None всегда, а
        # upsert_checkpoint_time делает "split_s=VALUES(split_s)" — каждый
        # опрос Copernico затирал split_s обратно в NULL, из-за чего график
        # "Темп/скорость" на вкладке "Бег" оставался пустым весь этап,
        # несмотря на то, что cumulative_s (время/место) записывались верно
        # (найдено пользователем 2026-08-08 на живой гонке).
        cum_by_seq: dict[int, Optional[int]] = {}
        for seq, field_name in lap_fields:
            elapsed_ms = _parse_copernico_elapsed_ms(runner.get(field_name))
            cum_by_seq[seq] = elapsed_ms // 1000 if elapsed_ms is not None else None

        for seq, field_name in lap_fields:
            checkpoint_id = cp_id_map.get(("run", seq))
            if checkpoint_id is None:
                continue
            cumulative_s = cum_by_seq[seq]
            split_s: Optional[int] = None
            if cumulative_s is not None:
                prev_cum = cum_by_seq.get(seq - 1)
                if prev_cum is not None:
                    split_s = cumulative_s - prev_cum
                elif seq == 1:
                    split_s = cumulative_s
            upsert_checkpoint_time(conn, pid, checkpoint_id, cumulative_s, split_s)
            if cumulative_s is not None:
                checkpoint_writes += 1

        raw_status = runner.get(fields.get("status"))
        if raw_status:
            mapped = STATUS_MAP.get(str(raw_status).strip().lower())
            if mapped is not None:
                new_status, dnf_stage = mapped
                # Copernico отдаёт статус ТОЛЬКО по беговому этапу — "notstarted"
                # для всех, кто ещё не финишировал бег, даже если участник уже
                # сошёл на плавании/вело. Без этой проверки такой снапшот тут же
                # затирал уже проставленный dnf/dsq обратно в active (баг,
                # найден пользователем 2026-08-08 в день бегового этапа).
                already_dnf = participant["status"] in ("dnf", "dsq")
                if already_dnf and new_status == "active":
                    continue
                if new_status != participant["status"] or dnf_stage != participant.get("dnf_stage"):
                    update_participant_status(conn, pid, new_status, dnf_stage)
                    status_updates += 1

    fresh_participants = get_participants_for_year(conn, race_year)
    cumulative, _splits = get_checkpoint_times_for_year(conn, race_year)
    pid_cp_times = {
        pid: {(stage, seq): v for stage, seqs in stages.items() for seq, v in seqs.items()}
        for pid, stages in cumulative.items()
    }
    recompute_totals_ranks_records(conn, race_year, fresh_participants, pid_cp_times)

    return {
        "ok": True,
        "enabled": True,
        "checkpoint_writes": checkpoint_writes,
        "status_updates": status_updates,
        "skipped": skipped,
    }
