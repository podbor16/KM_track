-- Результат -> карточка через заявку того же забега (2026-10-01, аудит привязки к карточкам).
-- Раньше карточку искали только по точному «фамилия + имя + ДР»: заглушка ДР в протоколе
-- (1900-01-01, «ГГГГ-01-01») или опечатка создавали новую карточку, хотя заявка этого
-- человека на этот же забег с этим же номером уже была. Теперь сначала заявка: тот же
-- event_id, тот же start_number, те же ФИ (collation ai_ci: регистр и ё/е не важны;
-- поля могут быть переставлены); ДР не сравниваем. Иначе — как раньше.
-- Похожие, но не равные ФИ (Белоблоцкая/Белоблоцкий) не склеиваем — их ловит
-- scripts/data_quality.py (R-LEAD).
-- Триггеры — только от root через `mysql` (у пользователя приложения нет прав при binlog).
-- Идемпотентно. trg_results_yo_bi остаётся первым (PRECEDES задан при его создании).

SET @has_idx := (SELECT COUNT(*) FROM information_schema.statistics
                 WHERE table_schema = DATABASE() AND table_name = 'leads' AND index_name = 'idx_leads_event_bib');
SET @ddl := IF(@has_idx = 0, 'CREATE INDEX idx_leads_event_bib ON leads (event_id, start_number)', 'DO 0');
PREPARE st FROM @ddl;
EXECUTE st;
DEALLOCATE PREPARE st;

DROP TRIGGER IF EXISTS trg_results_before_insert;

DELIMITER //
CREATE DEFINER=`km_analytic`@`%` TRIGGER trg_results_before_insert BEFORE INSERT ON results FOR EACH ROW
BEGIN
    DECLARE v_client_id INT UNSIGNED;

    IF NEW.start_number IS NOT NULL AND NEW.start_number <> 0 THEN
        SELECT l.client_id INTO v_client_id
        FROM leads l
        WHERE l.event_id = NEW.event_id AND l.start_number = NEW.start_number AND l.client_id <> 0
          AND ((l.surname = NEW.surname AND l.name = NEW.name) OR (l.surname = NEW.name AND l.name = NEW.surname))
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT 1;
    END IF;

    IF v_client_id IS NULL THEN
        SELECT id INTO v_client_id
        FROM clients
        WHERE surname = NEW.surname AND name = NEW.name AND birthday = NEW.birthday
        LIMIT 1;
    END IF;

    IF v_client_id IS NULL THEN
        INSERT INTO clients (surname, name, birthday, last_lead_id, last_result_id)
        VALUES (NEW.surname, NEW.name, NEW.birthday, 0, 0);
        SET v_client_id = LAST_INSERT_ID();
    END IF;

    SET NEW.client_id = v_client_id;
END//
DELIMITER ;
