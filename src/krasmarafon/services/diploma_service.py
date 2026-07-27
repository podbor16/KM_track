"""
Данные для страницы диплома участника — /diploma/{event_id}/{bib}.
Переиспользует уже закэшированный get_race_results_by_event_id() вместо
отдельного SQL-запроса по bib: результаты события и так загружаются
целиком, найти один bib среди них дешевле, чем городить новый метод.
"""

from typing import Optional
from datetime import timedelta

from src.analytics.db_results import get_race_results_by_event_id

# 'fifnished' — не опечатка в этом файле, а реальное значение в БД
# (см. тот же список в templates/krasmarafon/athlete-profile.html:366).
_FINISHED_STATUSES = {'finished', 'fifnished'}


def format_finish_time(td: Optional[timedelta]) -> str:
    """timedelta → 'H:MM:SS' (или 'MM:SS', если меньше часа), '-' для None."""
    if td is None:
        return '-'
    total_seconds = int(td.total_seconds())
    if total_seconds <= 0:
        return '-'
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def get_diploma_data(event_id: int, bib: str) -> Optional[dict]:
    """Данные для рендера диплома, либо None, если участник не найден /
    не финишировал по этой дистанции. show_sex_rank — показывать ли место
    по полу (только если у события есть участники обоих полов)."""
    rows = get_race_results_by_event_id(event_id)
    if not rows:
        return None

    target = next((r for r in rows if str(r.get('start_number')) == str(bib)), None)
    if target is None:
        return None

    status = str(target.get('race_status') or '').lower()
    if status not in _FINISHED_STATUSES:
        return None

    sexes = {r.get('sex') for r in rows if r.get('sex')}

    return {
        'surname': target.get('surname'),
        'name': target.get('name'),
        'category': target.get('category'),
        'time_display': format_finish_time(target.get('time_clear_finish')),
        'rank_absolute': target.get('rank_absolute_clean'),
        'rank_sex': target.get('rank_sex_clean'),
        'rank_category': target.get('rank_category_clean'),
        'show_sex_rank': len(sexes) > 1,
    }
