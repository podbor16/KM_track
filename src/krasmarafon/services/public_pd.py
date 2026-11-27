"""Публичный вид участника без согласия на публикацию ПД (leads.pd_refused, с Снежной семёрки 2026):
вместо ФИ — «Спортсмен», без даты рождения и ссылки на карточку. Номер, пол, категория, время и места
остаются. Вызывается в каждой публичной выдаче до кешей — настоящие ФИ не попадают в ответ."""

PLACEHOLDER = "Спортсмен"

# Отказ относится к участнику этого события. Номер — основная связь;
# client_id закрывает случай повторной заявки без номера после выдачи.
PD_REFUSED_SQL = ("EXISTS (SELECT 1 FROM leads pl WHERE pl.event_id = r.event_id "
                  "AND pl.pd_refused = 1 AND (pl.start_number = r.start_number "
                  "OR (pl.client_id IS NOT NULL AND pl.client_id <> 0 "
                  "AND pl.client_id = r.client_id)))")
_FULL_NAME_KEYS = ("full_name", "fullName")
_HIDDEN_KEYS = ("birthday", "birth_year", "client_id", "city", "club")


def mask_runner(row: dict, refused) -> dict:
    """refused — копия строки со скрытыми ПД; иначе та же строка."""
    if not refused:
        return row
    out = dict(row)
    if "surname" in out:
        out["surname"] = PLACEHOLDER
    if "name" in out:
        out["name"] = ""
    for key in _FULL_NAME_KEYS:
        if key in out:
            out[key] = PLACEHOLDER
    for key in _HIDDEN_KEYS:
        if key in out:
            out[key] = None
    return out


def invalidate_local_public_pd_caches() -> None:
    """Обновляет все локальные публичные снимки; Redis рассылает вызов воркерам."""
    from src.analytics import db_results
    from src.krasmarafon.services import results_service
    from src.krasmarafon.routers import api

    db_results.invalidate_public_pd_result_rows()
    results_service.invalidate_public_pd_results_cache()
    api._sse_initial_cache.clear()
