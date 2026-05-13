"""
E2E тест полного цикла забега: регистрация → трекер → результаты → история.
Вставляет тестовые данные в event_id=106 (Весна 2026), затем удаляет их.

Запуск: python tests/e2e_race_test.py
"""
import asyncio
import time
import sys
import httpx
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analytics.db_connection_optimized import get_pooled_connection

BASE = "http://localhost:8000"
EVENT_ID = 106
TEST_PREFIX = "TEST_"

# Тестовые участники
RUNNERS = [
    dict(surname="TEST_Петров",   name="Алексей", sex="Мужчина",  birthday="1990-03-15", bib=9901, category="мужчины до 49 лет (1976 г.р. и младше)"),
    dict(surname="TEST_Сидорова", name="Мария",   sex="Женщина", birthday="1995-07-22", bib=9902, category="женщины до 49 лет (1976 г.р. и младше)"),
    dict(surname="TEST_Кузнецов", name="Игорь",   sex="Мужчина",  birthday="1985-11-01", bib=9903, category="мужчины до 49 лет (1976 г.р. и младше)"),
]

# ─── helpers ──────────────────────────────────────────────────────────────────

def db():
    return get_pooled_connection()

def sql(query, params=None):
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute(query, params or ())
    result = cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()
    return result

def sql_insert(query, params=None):
    conn = db()
    cur = conn.cursor()
    cur.execute(query, params or ())
    conn.commit()
    last_id = cur.lastrowid
    cur.close()
    conn.close()
    return last_id

def hdr(title, step=None):
    prefix = f"  ШАГ {step}" if step else ""
    print(f"\n{'='*60}\n{prefix}  {title}\n{'='*60}")

def ok(msg): print(f"  OK  {msg}")
def warn(msg): print(f"  WARN {msg}")
def fail(msg): print(f"  FAIL {msg}")
def info(msg): print(f"  ...  {msg}")


# ─── cleanup ──────────────────────────────────────────────────────────────────

def cleanup():
    """Удаляет все тестовые записи по TEST_-префиксу."""
    info("Очистка тестовых данных...")
    # Находим result_id тестовых записей
    rows = sql(f"SELECT id FROM results WHERE event_id={EVENT_ID} AND surname LIKE 'TEST_%'")
    result_ids = [r['id'] for r in rows]
    if result_ids:
        ids_str = ','.join(str(i) for i in result_ids)
        sql(f"DELETE FROM result_segments WHERE result_id IN ({ids_str})")
        sql(f"DELETE FROM results WHERE id IN ({ids_str})")
        info(f"Удалено {len(result_ids)} записей из results + segments")

    # Удаляем leads
    rows = sql(f"SELECT id FROM leads WHERE event_id={EVENT_ID} AND surname LIKE 'TEST_%'")
    if rows:
        ids_str = ','.join(str(r['id']) for r in rows)
        sql(f"DELETE FROM leads WHERE id IN ({ids_str})")
        info(f"Удалено {len(rows)} записей из leads")

    # Удаляем clients
    rows = sql("SELECT id FROM clients WHERE surname LIKE 'TEST_%'")
    if rows:
        ids_str = ','.join(str(r['id']) for r in rows)
        sql(f"DELETE FROM clients WHERE id IN ({ids_str})")
        info(f"Удалено {len(rows)} записей из clients")

    # Сбрасываем gun_time_utc
    sql(f"UPDATE events SET gun_time_utc=NULL WHERE id={EVENT_ID}")
    info("gun_time_utc сброшен")
    ok("Очистка завершена")


# ─── browser check ────────────────────────────────────────────────────────────

async def browser_check(page, path, wait_ms=3000, label=""):
    """Загружает страницу, ждёт wait_ms, возвращает (sse_found, api_calls, rows, errors)."""
    sse_urls = []
    api_calls = []
    js_errors = []
    page.on("pageerror", lambda e: js_errors.append(str(e)))

    def on_req(req):
        if "/api/sse/" in req.url:
            sse_urls.append(req.url)
        elif "/api/" in req.url:
            api_calls.append(req.url.split("?")[0].replace(BASE, ""))

    page.on("request", on_req)
    resp = await page.goto(f"{BASE}{path}", wait_until="load", timeout=20000)
    await page.wait_for_timeout(wait_ms)
    rows = len(await page.query_selector_all("tbody tr"))
    status_el = await page.query_selector("#status-message")
    status_txt = await status_el.text_content() if status_el else ""
    return {
        "http": resp.status if resp else "?",
        "sse": sse_urls,
        "apis": list(dict.fromkeys(api_calls)),
        "rows": rows,
        "status_text": status_txt,
        "js_errors": js_errors,
        "markers": len(await page.query_selector_all(".leaflet-marker-icon")),
    }


# ─── main test ────────────────────────────────────────────────────────────────

async def run():
    print("=" * 60)
    print("  KM_track E2E TEST — полный цикл забега")
    print(f"  event_id={EVENT_ID} (Весна 2026 / 5км)")
    print("=" * 60)

    # Убеждаемся что сервер работает
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/health", timeout=5)
            ok(f"Сервер: {r.json()['status']}")
    except Exception as e:
        fail(f"Сервер недоступен: {e}")
        return

    # Чистим прошлые тестовые данные на всякий случай
    cleanup()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # ═══════════════════════════════════════════════════
        hdr("ШАГ 1: Регистрация участников (leads)", step=1)
        # ═══════════════════════════════════════════════════

        client_ids = []
        lead_ids = []
        for r in RUNNERS:
            # Вставляем клиента
            cid = sql_insert(
                "INSERT INTO clients (surname, name, birthday, count_leads) VALUES (%s,%s,%s,1)",
                (r['surname'], r['name'], r['birthday'])
            )
            client_ids.append(cid)

            # Вставляем регистрацию
            lid = sql_insert(
                """INSERT INTO leads (surname, name, sex, city, birthday, event_name, event_distance,
                   event_year, status, products, email, client_id, event_id)
                   VALUES (%s,%s,%s,'Красноярск',%s,'Весна','5 км',2026,1,'5 км',
                   'test@test.ru',%s,%s)""",
                (r['surname'], r['name'], r['sex'], r['birthday'], cid, EVENT_ID)
            )
            lead_ids.append(lid)
            ok(f"Зарегистрирован: {r['surname']} {r['name']} (client_id={cid}, lead_id={lid})")

        # Проверяем стартовый список
        page = await context.new_page()
        info("Открываем /start_list...")
        result = await browser_check(page, "/start_list", wait_ms=4000)
        print(f"  HTTP {result['http']} | SSE: {'OK' if result['sse'] else 'нет'} | rows={result['rows']}")
        print(f"  APIs: {result['apis']}")
        if result['js_errors']:
            warn(f"JS errors: {result['js_errors']}")

        # Проверяем API напрямую
        async with httpx.AsyncClient() as c:
            r2 = await c.get(f"{BASE}/api/registered-runners?event_id={EVENT_ID}", timeout=10)
            reg_data = r2.json()
            test_runners_in_startlist = [
                x for x in reg_data.get('runners', [])
                if x.get('surname', '').startswith(TEST_PREFIX)
            ]
        if test_runners_in_startlist:
            ok(f"Стартовый список API: {len(test_runners_in_startlist)} тестовых участника найдено")
        else:
            warn("Тестовые участники не найдены в /api/registered-runners")
        await page.close()

        # ═══════════════════════════════════════════════════
        hdr("ШАГ 2: Судья загружает участников (results: Running)", step=2)
        # ═══════════════════════════════════════════════════

        # Стартовый выстрел — 15 минут назад
        gun_utc = (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        sql(f"UPDATE events SET gun_time_utc='{gun_utc}' WHERE id={EVENT_ID}")
        ok(f"gun_time_utc установлен: {gun_utc}")

        result_ids = []
        for r in RUNNERS:
            rid = sql_insert(
                """INSERT INTO results
                   (surname, name, birthday, client_id, event_id, sex, start_number, category,
                    race_status, time_gun_start, time_clear_start)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Running','00:00:00','00:00:00')""",
                (r['surname'], r['name'], r['birthday'],
                 client_ids[RUNNERS.index(r)], EVENT_ID,
                 r['sex'], r['bib'], r['category'])
            )
            result_ids.append(rid)
            ok(f"results: {r['surname']} bib={r['bib']} result_id={rid} → Running")

        info("Ждём 3 сек чтобы _tracker_broadcast успел сработать...")
        await asyncio.sleep(3)

        # Проверяем трекер
        page = await context.new_page()
        info("Открываем /tracker...")
        result = await browser_check(page, "/tracker", wait_ms=5000)
        print(f"  HTTP {result['http']} | SSE: {'OK ' + str(result['sse']) if result['sse'] else 'нет'}")
        print(f"  Маркеров на карте: {result['markers']}")
        print(f"  Статус: '{result['status_text']}'")
        print(f"  APIs: {result['apis']}")
        if result['js_errors']:
            warn(f"JS errors: {result['js_errors']}")
        if result['markers'] >= 1:
            ok(f"Трекер показывает маркеры ({result['markers']} шт)")
        else:
            warn("Маркеры не найдены — возможно нет GPX маршрута или данные ещё не загружены")

        # Проверяем API напрямую
        async with httpx.AsyncClient() as c:
            r2 = await c.get(f"{BASE}/api/event-results?event_id={EVENT_ID}", timeout=15)
            api_data = r2.json()
        test_in_results = [
            x for x in api_data.get('results', [])
            if x.get('surname', '').startswith(TEST_PREFIX)
        ]
        if test_in_results:
            ok(f"/api/event-results: {len(test_in_results)} тестовых участника, статусы: {[x['race_status'] for x in test_in_results]}")
        else:
            warn("Тестовые участники не найдены в /api/event-results")
        await page.close()

        # ═══════════════════════════════════════════════════
        hdr("ШАГ 3: Участник достигает КТ1 (2.5 км)", step=3)
        # ═══════════════════════════════════════════════════

        # Петров первым достигает КТ1 через 13 мин
        sql(f"""UPDATE results SET
            time_clear_kt1='00:13:00',
            pace_avg_kt1='00:05:12'
            WHERE id={result_ids[0]}""")
        ok(f"TEST_Петров: КТ1 = 00:13:00 (темп 5:12/км)")

        # Сидорова тоже на КТ1 через 14:30
        sql(f"""UPDATE results SET
            time_clear_kt1='00:14:30',
            pace_avg_kt1='00:05:48'
            WHERE id={result_ids[1]}""")
        ok(f"TEST_Сидорова: КТ1 = 00:14:30 (темп 5:48/км)")

        # Кузнецов ещё бежит к КТ1 (no kt1)
        info("TEST_Кузнецов: ещё не достиг КТ1")

        # Вставляем сегменты для тех кто прошёл КТ1
        # Сегмент start→KT1 (0→2.5km): Петров
        sql_insert(
            """INSERT INTO result_segments (event_id, result_id, segment_code, sg_time_clear, sg_time_gun,
               sg_rank_absolute, sg_rank_sex, sg_rank_category, sg_pace_avg)
               VALUES (%s,%s,'start-kt1','00:13:00','00:13:01',1,1,1,'00:05:12')""",
            (EVENT_ID, result_ids[0])
        )
        sql_insert(
            """INSERT INTO result_segments (event_id, result_id, segment_code, sg_time_clear, sg_time_gun,
               sg_rank_absolute, sg_rank_sex, sg_rank_category, sg_pace_avg)
               VALUES (%s,%s,'start-kt1','00:14:30','00:14:31',2,1,1,'00:05:48')""",
            (EVENT_ID, result_ids[1])
        )
        ok("Сегменты start-kt1 вставлены для Петрова и Сидоровой")

        await asyncio.sleep(3)

        # Проверяем трекер с КТ1
        page = await context.new_page()
        result = await browser_check(page, "/tracker", wait_ms=5000)
        print(f"  Трекер: маркеров={result['markers']}, SSE={'OK' if result['sse'] else 'нет'}")
        async with httpx.AsyncClient() as c:
            r2 = await c.get(f"{BASE}/api/event-results?event_id={EVENT_ID}", timeout=15)
        test_runners = [x for x in r2.json().get('results', []) if x.get('surname','').startswith(TEST_PREFIX)]
        for tr in test_runners:
            kt1 = tr.get('checkpoints', {}).get('kt1', {}).get('time') or 'нет'
            info(f"  {tr['surname']}: status={tr['race_status']}, kt1={kt1}, dist={tr.get('current_distance',0):.2f}km")
        await page.close()

        # ═══════════════════════════════════════════════════
        hdr("ШАГ 4: Участники финишируют", step=4)
        # ═══════════════════════════════════════════════════

        # Петров финишировал 25:30
        sql(f"""UPDATE results SET
            race_status='Finished',
            time_clear_finish='00:25:30',
            time_gun_finish='00:25:31',
            finish_pace_avg_gun='00:05:06',
            finish_pace_avg_clean='00:05:06',
            finish_pace_avg='5:06',
            rank_absolute=1, rank_sex=1, rank_category=1,
            rank_absolute_clean=1, rank_sex_clean=1, rank_category_clean=1
            WHERE id={result_ids[0]}""")
        ok(f"TEST_Петров: Finished 00:25:30 (место 1)")

        # Сидорова финишировала 28:15
        sql(f"""UPDATE results SET
            race_status='Finished',
            time_clear_finish='00:28:15',
            time_gun_finish='00:28:16',
            finish_pace_avg_gun='00:05:39',
            finish_pace_avg_clean='00:05:39',
            finish_pace_avg='5:39',
            rank_absolute=2, rank_sex=1, rank_category=1,
            rank_absolute_clean=2, rank_sex_clean=1, rank_category_clean=1
            WHERE id={result_ids[1]}""")
        ok(f"TEST_Сидорова: Finished 00:28:15 (место 2 общее, место 1 женщины)")

        # Кузнецов финишировал 30:45
        sql(f"""UPDATE results SET
            race_status='Finished',
            time_clear_kt1='00:15:20',
            time_clear_finish='00:30:45',
            time_gun_finish='00:30:46',
            finish_pace_avg_gun='00:06:09',
            finish_pace_avg_clean='00:06:09',
            finish_pace_avg='6:09',
            rank_absolute=3, rank_sex=2, rank_category=2,
            rank_absolute_clean=3, rank_sex_clean=2, rank_category_clean=2
            WHERE id={result_ids[2]}""")
        ok(f"TEST_Кузнецов: Finished 00:30:45 (место 3)")

        # Сегменты КТ1→Финиш
        for i, (rid, kt1, fin, pace, sex_rank) in enumerate([
            (result_ids[0], '00:13:00', '00:25:30', '00:05:00', 1),
            (result_ids[1], '00:14:30', '00:28:15', '00:05:30', 1),
            (result_ids[2], '00:15:20', '00:30:45', '00:06:14', 2),
        ]):
            sql_insert(
                """INSERT INTO result_segments (event_id, result_id, segment_code, sg_time_clear, sg_time_gun,
                   sg_rank_absolute, sg_rank_sex, sg_rank_category, sg_pace_avg)
                   VALUES (%s,%s,'kt1-finish',%s,%s,%s,%s,%s,%s)""",
                (EVENT_ID, rid, fin, fin, i+1, sex_rank, i+1, pace)
            )
        ok("Сегменты kt1-finish вставлены для всех участников")

        await asyncio.sleep(3)

        # ─── Проверяем результаты ──────────────────────────────
        info("\nПроверяем страницу результатов...")
        page = await context.new_page()
        result_page = await browser_check(page, "/results", wait_ms=4000)
        print(f"  HTTP {result_page['http']} | SSE: {'OK' if result_page['sse'] else 'нет'} | rows в таблице={result_page['rows']}")
        print(f"  APIs: {result_page['apis']}")

        async with httpx.AsyncClient() as c:
            r2 = await c.get(f"{BASE}/api/event-results?event_id={EVENT_ID}", timeout=15)
        finished = [x for x in r2.json().get('results', []) if x.get('surname','').startswith(TEST_PREFIX) and x.get('race_status')=='Finished']
        if finished:
            ok(f"/api/event-results: {len(finished)} финишировавших тестовых участника")
            for f in sorted(finished, key=lambda x: x.get('rank_absolute') or 99):
                info(f"  #{f.get('rank_absolute')} {f['surname']}: {f.get('time_clear_finish')} (темп {f.get('finish_pace_avg')})")
        await page.close()

        # ─── Проверяем сегменты ───────────────────────────────
        info("\nПроверяем сегменты через API...")
        async with httpx.AsyncClient() as c:
            r2 = await c.get(f"{BASE}/api/event-segment-codes?event_id={EVENT_ID}", timeout=10)
            seg_codes = r2.json() if r2.status_code == 200 else {}
        if seg_codes:
            ok(f"/api/event-segment-codes: {seg_codes}")
        else:
            warn(f"/api/event-segment-codes: {r2.status_code}")

        # Проверяем сегменты одного участника
        async with httpx.AsyncClient() as c:
            r2 = await c.get(f"{BASE}/api/runner/{result_ids[0]}/segments", timeout=10)
        if r2.status_code == 200:
            segs = r2.json()
            ok(f"/api/runner/{result_ids[0]}/segments: {segs}")
        else:
            warn(f"/api/runner segments: {r2.status_code}")

        # ─── Проверяем историю ────────────────────────────────
        info("\nПроверяем страницу истории...")
        page = await context.new_page()
        hist_result = await browser_check(page, "/history", wait_ms=4000)
        print(f"  HTTP {hist_result['http']} | rows={hist_result['rows']}")

        # Проверяем профиль атлета по реальному имени
        async with httpx.AsyncClient() as c:
            r2 = await c.get(f"{BASE}/api/athlete/TEST_Петров/Алексей", timeout=10)
        if r2.status_code == 200:
            ok(f"/api/athlete/TEST_Петров/Алексей: {r2.json()}")
        else:
            warn(f"/api/athlete: {r2.status_code} — {r2.text[:100]}")
        await page.close()

        # ═══════════════════════════════════════════════════
        hdr("ИТОГИ", step=None)
        # ═══════════════════════════════════════════════════
        print("""
  Что проверено:
  [ШАГ 1] leads→clients: регистрация участников, стартовый список
  [ШАГ 2] results(Running) + gun_time_utc: маркеры на трекере
  [ШАГ 3] КТ1 + сегменты start-kt1: позиция обновилась
  [ШАГ 4] Finished + сегменты kt1-finish: результаты, история

  Как проверить вручную:
  1. СТАРТОВЫЙ СПИСОК: http://localhost:8000/start_list
     → Должны видеть TEST_Петров, TEST_Сидорова, TEST_Кузнецов
  2. ТРЕКЕР: http://localhost:8000/tracker
     → Маркеры участников на карте (если GPX загружен)
     → DevTools → Network → eventsource → /api/sse/tracker?event_id=106
  3. РЕЗУЛЬТАТЫ: http://localhost:8000/results → выбери Весна / 2026
     → Должны видеть 3 тестовых участника с финишными временами
  4. СЕГМЕНТЫ: http://localhost:8000/results → клик по участнику → вкладка Сегменты
  5. ИСТОРИЯ: http://localhost:8000/history → выбери Весна / 2026

  test result_ids: {result_ids}
  test client_ids: {client_ids}
  test lead_ids:   {lead_ids}
        """.format(result_ids=result_ids, client_ids=client_ids, lead_ids=lead_ids))

        await context.close()
        await browser.close()

    # Спрашиваем нужно ли удалить данные
    print("\n" + "="*60)
    ans = input("  Удалить тестовые данные из БД? [y/N]: ").strip().lower()
    if ans == 'y':
        cleanup()
    else:
        print("  Тестовые данные оставлены в БД для ручной проверки.")
        print("  Для удаления: python tests/e2e_race_test.py --cleanup")


def do_cleanup_only():
    print("Запуск очистки тестовых данных...")
    cleanup()


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        do_cleanup_only()
    else:
        asyncio.run(run())
