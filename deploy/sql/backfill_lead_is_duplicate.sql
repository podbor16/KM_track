-- Разовый бэкофилл: проставить is_duplicate=1 для ВСЕХ строк в каждой группе
-- (client_id, event_id), у которой сейчас >1 строка (trg_leads_before_insert
-- никогда фактически не считал is_duplicate — это мёртвый код
-- `SET NEW.is_duplicate = 0;` на каждой вставке). Идемпотентно: безопасно
-- перезапускать; также нормализует группы из ровно 1 строки обратно в 0.

-- Отчёт до
SELECT COUNT(*) AS rows_currently_flagged FROM leads WHERE is_duplicate = 1;

UPDATE leads l
JOIN (
    SELECT client_id, event_id, COUNT(*) AS cnt
    FROM leads
    WHERE client_id != 0 AND event_id != 0
    GROUP BY client_id, event_id
) grp ON l.client_id = grp.client_id AND l.event_id = grp.event_id
SET l.is_duplicate = IF(grp.cnt > 1, 1, 0);

-- Отчёт после
SELECT COUNT(*) AS rows_now_flagged FROM leads WHERE is_duplicate = 1;

SELECT client_id, event_id, COUNT(*) AS cnt
FROM leads
WHERE client_id != 0 AND event_id != 0
GROUP BY client_id, event_id
HAVING COUNT(*) > 1
ORDER BY cnt DESC;
