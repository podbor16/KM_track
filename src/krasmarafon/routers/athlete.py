"""Личный кабинет спортсмена: вход по коду из почты и /me (этап А,
спецификация docs/superpowers/specs/2026-11-03-athlete-login-design.md)."""

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse

from src.krasmarafon.routers.pages import templates, _diploma_event_ids
from src.krasmarafon.services import athlete_auth as aa
from src.krasmarafon.services.athlete_cabinet import cabinet

logger = logging.getLogger(__name__)
router = APIRouter()

ERR_CODE = "Код неверный или устарел"
ERR_LINK = "Ссылка устарела — запросите новый код"
ERR_LIMIT = "Слишком много попыток, попробуйте позже"
ERR_MAIL = "Не удалось отправить код, попробуйте через минуту"


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
    if "@" not in email or len(email) > 255:
        return _login_page(request, "email", error="Проверьте почту", email=email, shared=bool(shared))
    try:
        await run_in_threadpool(aa.request_code, email, _client_ip(request))
    except aa.TooManyRequests:
        return _login_page(request, "email", error=ERR_LIMIT, email=email, shared=bool(shared))
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


@router.get("/me", response_class=HTMLResponse)
async def me_page(request: Request, km_athlete: str | None = Cookie(default=None)):
    email = await run_in_threadpool(aa.session_email, km_athlete)
    if not email:
        return RedirectResponse("/me/login", status_code=302)
    people = await run_in_threadpool(cabinet, email)
    return templates.TemplateResponse("krasmarafon/me.html", {
        "request": request, "email": email, "people": people,
        "diploma_event_ids": set(_diploma_event_ids()),
    })
