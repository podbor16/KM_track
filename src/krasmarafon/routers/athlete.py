"""Личный кабинет спортсмена: вход по коду из почты, /me (этап А,
спецификация docs/superpowers/specs/2026-11-03-athlete-login-design.md), «Это я» и /me/history (этап Б1,
спецификация docs/superpowers/specs/2026-11-03-athlete-cards-history-design.md)."""

import datetime as dt
import logging
import re
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Form, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse

from src.krasmarafon.routers.pages import templates, _diploma_event_ids
from src.config import settings
from src.krasmarafon.services import athlete_auth as aa
from src.krasmarafon.services import athlete_claims as acl
from src.krasmarafon.services.athlete_cabinet import cabinet
from src.krasmarafon.services.athlete_claims import ClaimResult
from src.krasmarafon.services.athlete_history import build_history

logger = logging.getLogger(__name__)


def _require_cabinet_open(request: Request) -> None:
    """Пока кабинет не включён в /admin — для посетителей его нет (404), кроме вошедших в админку."""
    if not aa.cabinet_open(request):
        raise HTTPException(status_code=404)


router = APIRouter(dependencies=[Depends(_require_cabinet_open)])

_EMAIL_RE = re.compile(r"[^@\s,;<>()\"']+@[^@\s,;<>()\"']+\.[^@\s,;<>()\"']+")
ERR_CODE = "Код неверный или устарел"
ERR_LINK = "Ссылка устарела — запросите новый код"
ERR_LIMIT = "Слишком много попыток. Попробуйте через {minutes} мин."
ERR_MAIL = "Не удалось отправить код, попробуйте через минуту"
CLAIM_ERRORS = {
    "mismatch": "Дата не совпадает",
    "limit": "Слишком много попыток. Попробуйте завтра или напишите нам на 1@krasmarafon.ru",
    "taken": "Эту карточку уже заявили — напишите нам на 1@krasmarafon.ru",
    "no_birthday": "Подтвердить не получится — напишите нам на 1@krasmarafon.ru",
    "date": "Проверьте дату",
    "not_yours": "Эта карточка не совпадает с данными ваших заявок — напишите нам на 1@krasmarafon.ru",
    "other_person": "У вас уже есть своя карточка с другой датой рождения. Если это ваш ребёнок или близкий — "
                    "доступ к его истории появится позже",
}


def _foreign_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    return bool(origin) and urlparse(origin).netloc != request.headers.get("host")


def _https(request: Request) -> bool:
    # По схеме запроса (nginx: X-Forwarded-Proto), не по settings.DEBUG — на проде он True
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "")


def _login_page(request: Request, step: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse("krasmarafon/me-login.html", {"request": request, "step": step, **ctx})


async def _start_session(request: Request, email: str, shared: bool) -> RedirectResponse:
    token = await run_in_threadpool(aa.create_session, email, shared, request.headers.get("user-agent"))
    response = RedirectResponse("/me", status_code=303)
    response.set_cookie(
        aa.COOKIE_NAME, token, httponly=True, secure=_https(request), samesite="lax",
        max_age=None if shared else aa.SESSION_DAYS * 86400,
    )
    return response


def _forbidden() -> HTMLResponse:
    return HTMLResponse("Forbidden", status_code=403)


@router.get("/me/login", response_class=HTMLResponse)
async def login_page(request: Request, km_athlete: str | None = Cookie(default=None)):
    if km_athlete and await run_in_threadpool(aa.session_email, km_athlete):
        return RedirectResponse("/me", status_code=302)
    return _login_page(request, "email")


@router.post("/me/login", response_class=HTMLResponse)
async def login_send_code(request: Request, email: str = Form(...), shared: str = Form("")):
    if _foreign_origin(request):
        return _forbidden()
    email = aa.normalize_email(email)
    if len(email) > 255 or not _EMAIL_RE.fullmatch(email):
        return _login_page(request, "email", error="Проверьте почту", email=email, shared=bool(shared))
    try:
        await run_in_threadpool(aa.request_code, email, _client_ip(request))
    except aa.TooManyRequests as e:
        if e.recent:  # повторная отправка формы: прежний код ещё действует
            return _login_page(request, "code", email=email, shared=bool(shared), resend_in=e.retry_after,
                               already_sent=True)
        return _login_page(request, "email", error=ERR_LIMIT.format(minutes=-(-e.retry_after // 60)),
                           email=email, shared=bool(shared), retry_in=e.retry_after)
    except Exception:
        logger.exception("Письмо с кодом входа не отправлено")
        return _login_page(request, "email", error=ERR_MAIL, email=email, shared=bool(shared))
    return _login_page(request, "code", email=email, shared=bool(shared))


@router.post("/me/verify", response_class=HTMLResponse)
async def login_verify(request: Request, email: str = Form(...), code: str = Form(...), shared: str = Form("")):
    if _foreign_origin(request):
        return _forbidden()
    email = aa.normalize_email(email)
    if await run_in_threadpool(aa.verify_code, email, code):
        return await _start_session(request, email, bool(shared))
    return _login_page(request, "code", error=ERR_CODE, email=email, shared=bool(shared))


@router.get("/me/link", response_class=HTMLResponse)
async def link_page(request: Request, t: str = ""):
    email = await run_in_threadpool(aa.link_email, t)
    if not email:
        return _login_page(request, "email", error=ERR_LINK)
    return _login_page(request, "link", email=email, token=t)


@router.post("/me/link", response_class=HTMLResponse)
async def link_login(request: Request, t: str = Form(...)):
    if _foreign_origin(request):
        return _forbidden()
    email = await run_in_threadpool(aa.consume_link, t)
    if not email:
        return _login_page(request, "email", error=ERR_LINK)
    return await _start_session(request, email, False)


def _logged_out() -> RedirectResponse:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(aa.COOKIE_NAME)
    return response


@router.post("/me/logout")
async def logout(request: Request, km_athlete: str | None = Cookie(default=None)):
    if _foreign_origin(request):
        return _forbidden()
    if km_athlete:
        await run_in_threadpool(aa.delete_session, km_athlete)
    return _logged_out()


@router.post("/me/logout-all")
async def logout_all(request: Request, km_athlete: str | None = Cookie(default=None)):
    if _foreign_origin(request):
        return _forbidden()
    email = await run_in_threadpool(aa.session_email, km_athlete)
    if email:
        await run_in_threadpool(aa.delete_all_sessions, email)
    return _logged_out()


def _login_redirect() -> RedirectResponse:
    response = RedirectResponse("/me/login", status_code=302)
    response.delete_cookie(aa.COOKIE_NAME)
    return response


@router.get("/me", response_class=HTMLResponse)
async def me_page(request: Request, claim: str = "", r: str = "", changed: str = "",
                  km_athlete: str | None = Cookie(default=None)):
    email = await run_in_threadpool(aa.session_email, km_athlete)
    if not email:
        return _login_redirect()
    claimed, dropped = await run_in_threadpool(acl.claimed_cards, email)
    # привязки, снятые при открытии истории (/me/history → сюда), — для пояснения «Данные карточки изменились»
    dropped = list(dropped) + [int(x) for x in changed.split(",") if x.isascii() and x.isdigit() and len(x) <= 10]
    people = await run_in_threadpool(cabinet, email)
    history_note = await run_in_threadpool(_history_note, claimed, email) if claimed else None
    claim_id = int(claim) if claim.isascii() and claim.isdigit() and len(claim) <= 10 else None
    claim_error = CLAIM_ERRORS.get(r)
    form_shown = any(p["can_claim"] and p["client_id"] == claim_id for p in people)
    not_yours = None if form_shown or r != "not_yours" else claim_error
    return templates.TemplateResponse("krasmarafon/me.html", {
        "request": request, "email": email, "people": people,
        "diploma_event_ids": set(_diploma_event_ids()),
        "claimed": set(claimed), "dropped": set(dropped),
        "claim_id": claim_id, "claim_error": claim_error,
        "claim_error_page": not_yours,       # у «не ваша / нет такой» формы нет — ошибка над списком
        "history_note": history_note,
    })


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    return f"{n} {few}" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else f"{n} {many}"


def _history_note(claimed: list[int], email: str) -> str:
    """Пояснение у заявленного человека на /me: здесь — только заказы с этой почты, вся история — по ссылке.
    Счётчики — те же, что на /me/history."""
    results, leads = acl.history_rows(claimed)
    history = build_history(results, leads, dt.date.today(), {}, set(), email)
    n_leads = sum(len(y["items"]) for y in history["leads_years"])
    n_results = sum(len(y["items"]) for y in history["results_years"])
    return (f"Здесь — заявки, оформленные с этой почты. Все {_plural(n_leads, 'заявка', 'заявки', 'заявок')} "
            f"и {_plural(n_results, 'результат', 'результата', 'результатов')} — в истории")


@router.post("/me/claim")
async def claim_card(request: Request, background_tasks: BackgroundTasks, client_id: int = Form(...),
                     birthday: str = Form(""), km_athlete: str | None = Cookie(default=None)):
    if _foreign_origin(request):
        return _forbidden()
    email = await run_in_threadpool(aa.session_email, km_athlete)
    if not email:
        return RedirectResponse("/me/login", status_code=303)
    try:
        born = dt.date.fromisoformat(birthday.strip())
    except ValueError:
        return RedirectResponse(f"/me?claim={client_id}&r=date", status_code=303)
    try:
        result = await run_in_threadpool(acl.claim, email, client_id, born)
    except ValueError:      # чужая и несуществующая карточка неразличимы
        return RedirectResponse(f"/me?claim={client_id}&r=not_yours", status_code=303)
    if result == ClaimResult.OK:
        background_tasks.add_task(acl.notify_claimed, client_id, email)
    if result in (ClaimResult.OK, ClaimResult.ALREADY_MINE):
        return RedirectResponse("/me", status_code=303)
    return RedirectResponse(f"/me?claim={client_id}&r={result.value}", status_code=303)


@router.post("/me/unclaim")
async def unclaim_card(request: Request, client_id: int = Form(...), km_athlete: str | None = Cookie(default=None)):
    if _foreign_origin(request):
        return _forbidden()
    email = await run_in_threadpool(aa.session_email, km_athlete)
    if not email:
        return RedirectResponse("/me/login", status_code=303)
    await run_in_threadpool(acl.unclaim, email, client_id)
    return RedirectResponse("/me", status_code=303)


@router.get("/me/history", response_class=HTMLResponse)
async def history_page(request: Request, km_athlete: str | None = Cookie(default=None)):
    email = await run_in_threadpool(aa.session_email, km_athlete)
    if not email:
        return _login_redirect()
    claimed, dropped = await run_in_threadpool(acl.claimed_cards, email)
    if not claimed:
        changed = f"?changed={','.join(map(str, dropped))}" if dropped else ""
        return RedirectResponse(f"/me{changed}", status_code=303)
    results, leads = await run_in_threadpool(acl.history_rows, claimed)
    title = await run_in_threadpool(acl.history_title, claimed)
    codes = {ev.name: ev.code for ev in settings.EVENTS.values()}
    history = build_history(results, leads, dt.date.today(), codes, set(_diploma_event_ids()), email)
    return templates.TemplateResponse("krasmarafon/me-history.html", {
        "request": request, "title": title, "history": history, "card_ids": claimed,
    })
