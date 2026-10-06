-- Флаги заявок, которые не устаревают (2026-10-06).
-- Было: is_name_suspicious считался только в коде при записи заявки — после чисток
-- ФИО (01.10), склеек и правок мимо этого кода 378 заявок остались «подозрительными»
-- с чистым ФИО. Стало: флаг считает БД на любой записи заявки.
--   * name_ok — «Имя в порядке» (кнопка в /admin): снимает флаг; смена ФИО сбрасывает.
--   * dup_main — «Сделать основной» (кнопка в /admin): ручной выбор основной заявки
--     человека на дистанцию; is_duplicate пересчитывает recompute_duplicates() в коде.
--   * trg_leads_after_update переписывал телефон/email карточки на КАЖДОМ обновлении
--     заявки (даже флага) — теперь только когда контакт в заявке изменился.
-- Подозрительно: в фамилии или имени что-то кроме кириллицы и дефиса (латиница,
-- цифры, пробел, точка) — то же правило, что tilda_webhook.is_name_suspicious().
-- Выполнять от root (триггеры при включённом binlog). Один раз (ADD COLUMN).

ALTER TABLE leads
    ADD COLUMN name_ok TINYINT(1) NOT NULL DEFAULT 0 AFTER is_name_suspicious,
    ADD COLUMN dup_main TINYINT(1) NOT NULL DEFAULT 0 AFTER is_duplicate;

DROP TRIGGER IF EXISTS trg_leads_name_flag_bi;
DROP TRIGGER IF EXISTS trg_leads_name_flag_bu;
DROP TRIGGER IF EXISTS trg_leads_after_update;

DELIMITER //
-- после trg_leads_yo_*: проверяется ФИО уже без «ё»
CREATE TRIGGER trg_leads_name_flag_bi BEFORE INSERT ON leads FOR EACH ROW FOLLOWS trg_leads_yo_bi
BEGIN
    SET NEW.is_name_suspicious = NEW.name_ok = 0 AND (
        (COALESCE(NEW.surname, '') <> '' AND NEW.surname NOT REGEXP '^[а-яёА-ЯЁ-]+$')
        OR (COALESCE(NEW.name, '') <> '' AND NEW.name NOT REGEXP '^[а-яёА-ЯЁ-]+$'));
END//
CREATE TRIGGER trg_leads_name_flag_bu BEFORE UPDATE ON leads FOR EACH ROW FOLLOWS trg_leads_yo_bu
BEGIN
    IF NOT (NEW.surname <=> OLD.surname AND NEW.name <=> OLD.name) THEN
        SET NEW.name_ok = 0;
    END IF;
    SET NEW.is_name_suspicious = NEW.name_ok = 0 AND (
        (COALESCE(NEW.surname, '') <> '' AND NEW.surname NOT REGEXP '^[а-яёА-ЯЁ-]+$')
        OR (COALESCE(NEW.name, '') <> '' AND NEW.name NOT REGEXP '^[а-яёА-ЯЁ-]+$'));
END//
CREATE TRIGGER trg_leads_after_update AFTER UPDATE ON leads FOR EACH ROW
BEGIN
    IF OLD.client_id != NEW.client_id THEN
        UPDATE clients SET
            count_leads = count_leads - 1,
            last_lead_id = (SELECT MAX(id) FROM leads WHERE client_id = OLD.client_id),
            last_lead_date = (SELECT MAX(created_at) FROM leads WHERE client_id = OLD.client_id),
            total_amount = total_amount - OLD.amount
        WHERE id = OLD.client_id;

        UPDATE clients SET
            count_leads = count_leads + 1,
            last_lead_id = (SELECT MAX(id) FROM leads WHERE client_id = NEW.client_id),
            last_lead_date = (SELECT MAX(created_at) FROM leads WHERE client_id = NEW.client_id),
            total_amount = total_amount + NEW.amount
        WHERE id = NEW.client_id;

        IF NEW.city IS NOT NULL AND NEW.city != '' THEN
            UPDATE clients SET city = NEW.city WHERE id = NEW.client_id AND city IS NULL;
        END IF;
        IF NEW.club IS NOT NULL AND NEW.club != '' THEN
            UPDATE clients SET club = NEW.club WHERE id = NEW.client_id AND club IS NULL;
        END IF;
        IF NEW.phone IS NOT NULL AND NEW.phone != '' THEN
            UPDATE clients SET phone = NEW.phone WHERE id = NEW.client_id;
        END IF;
        IF NEW.email IS NOT NULL AND NEW.email != '' THEN
            UPDATE clients SET email = NEW.email WHERE id = NEW.client_id AND email != NEW.email;
        END IF;

        UPDATE clients SET
            first_lead_date = (SELECT MIN(created_at) FROM leads WHERE client_id = OLD.client_id)
        WHERE id = OLD.client_id;
    ELSE
        IF OLD.amount != NEW.amount THEN
            UPDATE clients SET
                total_amount = total_amount - OLD.amount + NEW.amount
            WHERE id = NEW.client_id;
        END IF;

        IF OLD.city != NEW.city AND NEW.city IS NOT NULL AND NEW.city != '' THEN
            UPDATE clients SET city = NEW.city WHERE id = NEW.client_id;
        END IF;
        IF OLD.club != NEW.club AND NEW.club IS NOT NULL AND NEW.club != '' THEN
            UPDATE clients SET club = NEW.club WHERE id = NEW.client_id;
        END IF;
        -- контакт заявки изменился — переносим в карточку; иначе (правка флага, ФИО,
        -- номера…) карточку не трогаем
        IF NOT (NEW.phone <=> OLD.phone) AND NEW.phone IS NOT NULL AND NEW.phone != '' THEN
            UPDATE clients SET phone = NEW.phone WHERE id = NEW.client_id;
        END IF;
        IF NOT (NEW.email <=> OLD.email) AND NEW.email IS NOT NULL AND NEW.email != '' THEN
            UPDATE clients SET email = NEW.email WHERE id = NEW.client_id AND email != NEW.email;
        END IF;
    END IF;
END//
DELIMITER ;

-- пересчёт флага по всей таблице (триггер BU считает его сам; меняются только строки,
-- где флаг расходится с ФИО)
UPDATE leads SET is_name_suspicious = 1 - is_name_suspicious
WHERE is_name_suspicious <> (name_ok = 0 AND (
        (COALESCE(surname, '') <> '' AND surname NOT REGEXP '^[а-яёА-ЯЁ-]+$')
        OR (COALESCE(name, '') <> '' AND name NOT REGEXP '^[а-яёА-ЯЁ-]+$')));
