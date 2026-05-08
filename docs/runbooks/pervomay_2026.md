Runbook: Первомайский полумарафон 2026-05-01
Сегодня вечером (30 апреля) — СДЕЛАНО ✅
Статус	Действие
✅	checkpoint_distances 5 км исправлен в YAML и БД → [0, 2.7, 5.0]
✅	kt6/kt7 колонки в БД есть
✅	--init 5 км: 712 участников загружено
✅	--init 21.1 км: 509 участников загружено
Опционально сегодня (если есть время): проверить трекер визуально:


python -m uvicorn src.main:app --reload --port 8000
Открыть http://localhost:8000/tracker → должен показать переключатель дистанций, участников, маршрут.

Утро 1 мая — ДО СТАРТА
1. Добавить 3 участников без даты рождения (если появились в Copernico)
Проверить: запустить один цикл и посмотреть лог — если для их номеров появится предупреждение ⚠️ Участник с номером NNN не найден в кэше, значит Copernico вернул их с датой, но в БД их нет.

Добавить точечно (заменить NNN, Фамилию, Имя, дату):


python -c "
import os; from dotenv import load_dotenv; load_dotenv()
import mysql.connector
conn = mysql.connector.connect(host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT')), database=os.getenv('DB_NAME'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'))
cur = conn.cursor()
cur.execute(\"INSERT INTO results (event_id, start_number, surname, name, birthday, sex, category, race_status, client_id) VALUES (142, NNN, 'Фамилия', 'Имя', '1990-01-01', 'Мужчина', 'М до 49', 'Not started', 0)\")
conn.commit(); print('OK'); cur.close(); conn.close()
"
Если участников нет в Copernico и завтра — просто пропустить. 3 человека не критично.

2. Открыть 3 терминала и запустить в таком порядке:
Терминал 1 — FastAPI сервер (запустить первым):


cd c:\Users\podbo\Работа\КРАСМАРАФОН\KM_track
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2
Ждать: Application startup complete.

Терминал 2 — Loader 5 км (запустить вторым):


python load_race_results.py --config config/events/pervomay.yaml --distance "5 км" --interval 5 --debug
Терминал 3 — Loader 21.1 км (запустить третьим):


python load_race_results.py --config config/events/pervomay.yaml --distance "21.1 км" --interval 5 --debug
Если нужен VPN-обход — добавить --fix-routing и запустить от Администратора.

3. Проверить что данные подтягиваются из Copernico
В логах Терминала 2 и 3 должны появиться строки:


Цикл #1: fetch=1.5s calc=0.3s ranks=0.2s total=2.0s | updated=0r/0s kt_reads=0
Нули — норма до старта (никто ещё не финишировал и не прошёл КТ).

В момент выстрела стартового пистолета
В течение 1–2 минут после выстрела в логах должно появиться:


gun_time_utc сохранён: 2026-05-01T...Z
Это ключевой момент: именно с этого времени маркеры начнут двигаться по карте. Если этой строки нет 5 минут после старта — Copernico ещё не зафиксировал gunTime, маркеры стоят на старте.

Во время забега — что смотреть
Логи Loader (каждые 5 сек при считываниях):


Цикл #47: fetch=1.2s calc=0.8s ranks=1.5s total=3.5s | updated=34r/68s kt_reads=28
kt_reads=28 — 28 человек прошли КТ в этом цикле (считывания чипов)
total=3.5s — полный цикл 3.5 сек, это нормально
Каждые 60 сек:


PERF [120 циклов]: цикл avg=2.1s min=0.8s max=6.3s | chip reads/10s=47
Трекер http://localhost:8000/tracker:

Выбрать участника → маркер движется по маршруту
Попап показывает «Последняя КТ», темп, прогноз финиша
Тревожные сигналы и что делать
Что видим в логе	Диагноз	Действие
❌ Ошибка Copernico: 429	Rate limit превышен	Остановить Ctrl+C, перезапустить с --interval 10
❌ Ошибка Copernico: 401/403	Неверные credentials	Проверить race_id в pervomay.yaml
⚠️ Ошибка получения данных, повторим...	Временная потеря сети	Само восстановится через 1-2 цикла
⚠️ Участник с номером NNN не найден в кэше	Участник не в БД	Не критично, просто не отслеживается
total=15s и растёт	Перегрузка при пике считываний	Нормально в пик, наблюдать за max_t в PERF
gun_time_utc не появляется	Copernico не получил gun	Маркеры стоят — нормально, появится позже
Маркеры стоят у старта после gun	Либо gun_time ещё нет, либо race_gun_unix_ms не обновился	Проверить в БД: SELECT gun_time_utc FROM events WHERE id=142
После финиша последнего участника
Нажать Ctrl+C в обоих Loader-терминалах. В каждом появится финальная статистика:


ФИНАЛЬНАЯ СТАТИСТИКА
Циклов: 720
Всего обновлено results: 12500 записей
Файлы для постанализа будут в logs/:

race_loader_142_*.log — полный лог 5 км
race_loader_143_*.log — полный лог 21.1 км
perf_stats_142.json, perf_stats_143.json — финальная статистика производительности
Быстрые SQL-проверки (если что-то идёт не так)

-- Сколько участников с данными КТ1 (считывания пошли)
SELECT COUNT(*) FROM results WHERE event_id = 142 AND time_clear_kt1 IS NOT NULL;

-- gun_time обновился?
SELECT id, gun_time_utc FROM events WHERE id IN (142, 143);

-- Топ-5 финишировавших 5 км
SELECT start_number, surname, name, time_gun_finish 
FROM results WHERE event_id=142 AND race_status='Finished' 
ORDER BY time_gun_finish LIMIT 5;