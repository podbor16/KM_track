"""
Поиск участников и профиль для «Истории участия» (/history, /athlete-profile).

Профиль строится по карточке (clients.id), а не по совпадению ФИО в строках результатов:
тёзки (отец и сын «Пцарев Александр») — разные профили, правки «Качества данных»
(перенос строки, склейка карточек) сразу видны на сайте.
"""

import logging
from typing import Any, Dict, List, Tuple

from .db_pool import get_pooled_connection

logger = logging.getLogger(__name__)


def search_clients_optimized(search_query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Карточки по началу фамилии или имени -> [{client_id, surname, name, birth_year, events_count}]."""
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось получить соединение")
        return []
    try:
        cursor = connection.cursor(dictionary=True)
        term = f"{search_query.strip()}%"
        cursor.execute(
            """SELECT c.id AS client_id, c.surname, c.name, c.birthday,
                      (SELECT COUNT(*) FROM results r WHERE r.client_id = c.id) AS events_count
               FROM clients c
               WHERE c.id <> 0 AND (c.surname LIKE %s OR c.name LIKE %s)
               ORDER BY c.surname, c.name, c.birthday
               LIMIT %s""",
            (term, term, int(limit)),
        )
        rows = cursor.fetchall()
        cursor.close()
        for row in rows:
            bd = row.pop("birthday")
            row["birth_year"] = str(bd.year) if bd else "Неизвестно"
        return rows
    except Exception as e:
        logger.error(f"❌ Ошибка поиска: {e}")
        return []
    finally:
        if connection.is_connected():
            connection.close()


def get_athlete_by_client(client_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Карточка и её результаты -> (athlete, results). Нет карточки -> ({}, []).
    athlete: поля последнего результата (пол, категория…) + ФИО и ДР карточки + client_id."""
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return {}, []
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, surname, name, birthday FROM clients WHERE id = %s AND id <> 0", (int(client_id),))
        card = cursor.fetchone()
        if not card:
            cursor.close()
            return {}, []
        cursor.execute(
            """SELECT r.*, e.event_name, e.event_distance, e.event_year, e.event_date
               FROM results r
               LEFT JOIN events e ON r.event_id = e.id
               WHERE r.client_id = %s
               ORDER BY e.event_year DESC, e.event_date DESC, r.id DESC""",
            (card["id"],),
        )
        results = [dict(r) for r in cursor.fetchall()]
        cursor.close()
        athlete = dict(results[0]) if results else {}
        athlete.update(client_id=card["id"], surname=card["surname"], name=card["name"], birthday=card["birthday"])
        return athlete, results
    except Exception as e:
        logger.error(f"❌ Ошибка при получении профиля #{client_id}: {e}")
        return {}, []
    finally:
        if connection.is_connected():
            connection.close()


search_clients = search_clients_optimized
