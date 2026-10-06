-- Разовая правка 2026-10-06 (решения пользователя): пол заявок в канон, элита и пейсеры Жары 2026 21,1 км
UPDATE leads SET sex = 'Женщина' WHERE BINARY sex IN ('Ж', 'ж', 'жен', 'женский', 'Женский', 'женщина');
SELECT ROW_COUNT() AS sex_female;
UPDATE leads SET sex = 'Мужчина' WHERE BINARY sex IN ('М', 'муж', 'мужской', 'Мужской', 'мужчина');
SELECT ROW_COUNT() AS sex_male;
UPDATE leads l JOIN (SELECT client_id, MIN(sex) sx FROM results WHERE client_id > 0 AND sex IN ('Мужчина', 'Женщина')
                     GROUP BY client_id HAVING COUNT(DISTINCT sex) = 1) r ON r.client_id = l.client_id
SET l.sex = r.sx WHERE l.sex = '';
SELECT ROW_COUNT() AS sex_from_results;
UPDATE leads l JOIN (SELECT client_id, MIN(sex) sx FROM leads WHERE client_id > 0 AND sex IN ('Мужчина', 'Женщина')
                     GROUP BY client_id HAVING COUNT(DISTINCT sex) = 1) o ON o.client_id = l.client_id
SET l.sex = o.sx WHERE l.sex = '';
SELECT ROW_COUNT() AS sex_from_leads;

UPDATE leads l JOIN results r ON r.client_id = l.client_id AND r.event_id = 116
SET l.is_elite = 1
WHERE l.event_name = 'Жара' AND l.event_year = 2026 AND l.event_distance = '21.1 км' AND r.start_number BETWEEN 1500 AND 1999;
UPDATE leads SET is_elite = 1 WHERE id IN (37812, 37819, 37821, 37836);      -- элита из списков организатора без результата
UPDATE results SET is_pacer = 1 WHERE event_id = 116 AND start_number BETWEEN 2524 AND 2536;
UPDATE leads l JOIN results r ON r.client_id = l.client_id AND r.event_id = 116
SET l.is_pacer = 1
WHERE l.event_name = 'Жара' AND l.event_year = 2026 AND l.event_distance = '21.1 км' AND r.start_number BETWEEN 2524 AND 2536;

SELECT CAST(sex AS BINARY) sex, COUNT(*) FROM leads GROUP BY CAST(sex AS BINARY);
SELECT SUM(is_elite) elite_leads, SUM(is_pacer) pacer_leads FROM leads WHERE event_name = 'Жара' AND event_year = 2026;
SELECT SUM(is_elite) elite_results, SUM(is_pacer) pacer_results FROM results WHERE event_id = 116;
SELECT surname, name, start_number, is_elite, is_pacer FROM leads
WHERE event_name = 'Жара' AND event_year = 2026 AND event_distance = '21.1 км' AND (start_number IS NULL OR is_elite OR is_pacer) ORDER BY is_pacer, surname;
