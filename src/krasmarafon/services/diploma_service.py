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

# У событий без возрастных категорий (напр. благотворительные забеги вроде
# "Достигая цели") поле category в БД — буквально "Мужчины"/"Женщины", т.е.
# то же самое разбиение, что и по полу. Показывать в этом случае и "Пол", и
# "Категория" с одинаковым местом — дублирование; у событий с настоящими
# возрастными категориями ("мужчины до 49 лет" и т.п.) category несёт
# данные, которых нет в строке "Пол", и её нужно показывать.
_GENDER_ONLY_CATEGORY_WORDS = {'мужчины', 'мужчина', 'женщины', 'женщина', 'м', 'ж'}


def _is_gender_only_category(category: str) -> bool:
    return category.strip().lower() in _GENDER_ONLY_CATEGORY_WORDS


def _gender_label(sex: Optional[str]) -> str:
    """'Мужчины'/'Женщины' для подписи строки места по полу — вместо
    нейтрального 'Пол' (та же эвристика распознавания значений sex из БД,
    что и convertSexToGender() в analytics-results.js)."""
    if not sex:
        return 'Пол'
    lowered = str(sex).strip().lower()
    if 'муж' in lowered or lowered in ('male', 'm', 'м'):
        return 'Мужчины'
    if 'жен' in lowered or lowered in ('female', 'f', 'ж'):
        return 'Женщины'
    return 'Пол'


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

    sexes = {str(r.get('sex')).strip().lower() for r in rows if r.get('sex')}
    categories = {str(r.get('category')).strip() for r in rows if r.get('category')}
    show_category_rank = not all(_is_gender_only_category(c) for c in categories) if categories else False

    # Общее правило: время — чистое (net/clean), место — официальное
    # (gun-based). Осознанное решение пользователя: эти дипломы не для
    # награждения (там место объявляют по официальному времени) — а для
    # соцсетей участников, время они хотят видеть своё честное (net), но
    # место должно совпадать с тем, что объявляет судья/показывает сайт.
    #
    # Исключение — «Жара»: с 2026 года на этом событии награждают именно по
    # чистому времени (решение оргкомитета), т.е. судья/сайт объявляют место
    # по _clean-варианту — значит и диплом для Жары должен показывать его,
    # чтобы место на дипломе по-прежнему совпадало с официально объявленным.
    is_zhara = str(target.get('event_name') or '').strip() == 'Жара'
    rank_absolute = target.get('rank_absolute_clean') if is_zhara else target.get('rank_absolute')
    rank_sex = target.get('rank_sex_clean') if is_zhara else target.get('rank_sex')
    rank_category = target.get('rank_category_clean') if is_zhara else target.get('rank_category')

    return {
        'surname': target.get('surname'),
        'name': target.get('name'),
        'category': target.get('category'),
        'time_display': format_finish_time(target.get('time_clear_finish')),
        'rank_absolute': rank_absolute,
        'rank_sex': rank_sex,
        'rank_category': rank_category,
        'sex_label': _gender_label(target.get('sex')),
        'show_sex_rank': len(sexes) > 1,
        'show_category_rank': show_category_rank,
    }
