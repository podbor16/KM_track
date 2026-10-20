"""
Сертификат «Забега Единства»: события страницы и их статистика в /admin → «Сертификаты».

POST /medals/stat — для localhost: на проде этот адрес отвечает nginx (204 + строка в лог,
deploy/nginx.conf), Python в момент пика не участвует. Формат лога — src/analytics/medals_stats.py.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool

from src.analytics import medals_stats
from src.core.auth import api_require_auth

router = APIRouter(tags=["Сертификат «Забега Единства»"])


@router.post("/medals/stat", include_in_schema=False)
async def stat(request: Request, e: str = "", f: str = "") -> Response:
    await run_in_threadpool(medals_stats.append, e, f, request.client.host if request.client else "")
    return Response(status_code=204)


@router.get("/api/admin/medals-stats")
async def stats(user: str = Depends(api_require_auth)) -> dict:
    return medals_stats.summary(await run_in_threadpool(medals_stats.read))


@router.get("/api/admin/medals-stats.xlsx")
async def stats_xlsx(user: str = Depends(api_require_auth)) -> Response:
    data = await run_in_threadpool(lambda: medals_stats.to_xlsx(medals_stats.read()))
    name = f"medals-stats-{datetime.now():%Y%m%d-%H%M}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
