-- clients.last_result_id = MAX(results.id) клиента. trg_results_after_insert
-- поддерживает это при вставке, но триггера на DELETE не было: после удаления
-- результатов (перезаливки, ручные чистки) ссылка оставалась на
-- несуществующую строку. На 2026-09-24: 3708 битых ссылок, из них 1600 = 0
-- (заглушка из trg_results_before_insert у клиентов без результатов).
-- Идемпотентно.

DROP TRIGGER IF EXISTS trg_results_after_delete;

DELIMITER //
CREATE TRIGGER trg_results_after_delete
AFTER DELETE ON results
FOR EACH ROW
BEGIN
    UPDATE clients
    SET last_result_id = (SELECT MAX(id) FROM results WHERE client_id = OLD.client_id)
    WHERE id = OLD.client_id AND last_result_id = OLD.id;
END//
DELIMITER ;

-- Разовый пересчёт: MAX(results.id) клиента, NULL если результатов нет
UPDATE clients c
LEFT JOIN (SELECT client_id, MAX(id) AS mx FROM results GROUP BY client_id) r
    ON r.client_id = c.id
SET c.last_result_id = r.mx
WHERE NOT (c.last_result_id <=> r.mx);

SELECT ROW_COUNT() AS clients_fixed;

SELECT COUNT(*) AS dangling_after
FROM clients c LEFT JOIN results r ON r.id = c.last_result_id
WHERE c.last_result_id IS NOT NULL AND r.id IS NULL;
