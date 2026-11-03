"""Публичный вид участника без согласия на публикацию ПД (leads.pd_refused, с Снежной семёрки 2026):
вместо ФИ — «Спортсмен», без даты рождения и ссылки на карточку. Номер, пол, категория, время и места
остаются. Вызывается в каждой публичной выдаче до кешей — настоящие ФИ не попадают в ответ."""

PLACEHOLDER = "Спортсмен"

# Отказ от публикации ПД (leads.pd_refused) для строки results с алиасом r — по заявке того же события и номера
PD_REFUSED_SQL = ("EXISTS (SELECT 1 FROM leads pl WHERE pl.event_id = r.event_id "
                  "AND pl.start_number = r.start_number AND pl.pd_refused = 1)")
_FULL_NAME_KEYS = ("full_name", "fullName")
_HIDDEN_KEYS = ("birthday", "birth_year", "client_id")


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
