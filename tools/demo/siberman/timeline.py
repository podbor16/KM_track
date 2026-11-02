"""Время гонки Siberman: абсолютные моменты отметок, окна дней, «время без ночей». Чистые функции."""
from bisect import bisect_right
from datetime import datetime, timedelta, timezone

KRSK = timezone(timedelta(hours=7))
PAD_S = 300
DAY_LABELS = {1: 'День 1 · плавание и вело', 2: 'День 2 · вело', 3: 'День 3 · бег'}
_STAGE_DAY = {'swim': 1, 'bike_day1': 1, 'bike_day2': 2, 'run': 3}


def stage_day(stage: str) -> int:
    return _STAGE_DAY[stage]


def _ms(dt: datetime) -> int:
    """Naive datetime трактуется как Красноярск (+07:00)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KRSK)
    return round(dt.timestamp() * 1000)


def abs_ms(stage, cumulative_s, *, race_start, bike2_day_midnight, handicap_s, run_start) -> int:
    """Unix ms отметки. swim/bike_day1 - от race_start, bike_day2 - от полуночи дня 2 +
    личный старт (handicap_s - секунды суток), run - от run_start."""
    if stage in ('swim', 'bike_day1'):
        base = _ms(race_start)
    elif stage == 'bike_day2':
        if handicap_s is None:
            raise ValueError("bike_day2 требует handicap_s (личный старт вело-2)")
        base = _ms(bike2_day_midnight) + round(handicap_s * 1000)
    elif stage == 'run':
        base = _ms(run_start)
    else:
        raise ValueError(f"неизвестный этап: {stage}")
    return base + round(cumulative_s * 1000)


def day_windows(stage_marks, anchors) -> list[dict]:
    """stage_marks: [(day, ms)]. anchors: race_start, bike2_start, run_start (datetime или ms),
    опц. bike2_first_start (самый ранний личный старт вело-2). Только дни, у которых есть отметки."""
    def to_ms(v):
        return _ms(v) if isinstance(v, datetime) else int(v)

    starts = {
        1: to_ms(anchors['race_start']),
        2: to_ms(anchors.get('bike2_first_start') or anchors['bike2_start']),
        3: to_ms(anchors['run_start']),
    }
    last: dict[int, int] = {}
    for day, ms in stage_marks:
        last[day] = max(last.get(day, ms), ms)
    return [
        {'day': d, 'label': DAY_LABELS[d],
         'start_ms': starts[d] - PAD_S * 1000, 'end_ms': last[d] + PAD_S * 1000}
        for d in sorted(last)
    ]


def _offsets(windows) -> list[float]:
    out, acc = [], 0.0
    for w in windows:
        out.append(acc)
        acc += (w['end_ms'] - w['start_ms']) / 1000
    return out


def total_compact_s(windows) -> float:
    return sum((w['end_ms'] - w['start_ms']) / 1000 for w in windows)


def compact_to_abs(t_s, windows) -> int:
    if not windows:
        raise ValueError("нет окон")
    offs = _offsets(windows)
    if t_s <= 0:
        return windows[0]['start_ms']
    if t_s >= total_compact_s(windows):
        return windows[-1]['end_ms']
    i = bisect_right(offs, t_s) - 1
    return windows[i]['start_ms'] + round((t_s - offs[i]) * 1000)


def abs_to_compact(ms, windows) -> float:
    if not windows:
        raise ValueError("нет окон")
    for w, off in zip(windows, _offsets(windows)):
        if ms < w['start_ms']:
            return off  # до первого окна или ночь: начало следующего окна
        if ms <= w['end_ms']:
            return off + (ms - w['start_ms']) / 1000
    return total_compact_s(windows)
