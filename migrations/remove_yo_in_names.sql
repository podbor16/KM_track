-- «ё» -> «е» в фамилии и имени (clients, leads, results) — решение пользователя
-- 2026-09-27: «ё» неудобно искать с клавиатуры. Город и клуб не трогаем.
-- Collation utf8mb4_0900_ai_ci и так не различает е/ё (поиск в SQL, uk_client,
-- триггеры сопоставления) — коллизий уникальности нет; мешал поиск в браузере.
-- Триггеры BEFORE INSERT/UPDATE — чтобы «ё» не возвращалась ни из одного
-- источника (вебхук Tilda, импорт, лоадер Copernico перезаписывает ФИО results).
-- Выполнять ПОСЛЕ scripts/clean_clients.py (в его решениях есть «ё») и при
-- остановленном лоадере. Идемпотентно.

DROP TRIGGER IF EXISTS trg_clients_yo_bi;
DROP TRIGGER IF EXISTS trg_clients_yo_bu;
DROP TRIGGER IF EXISTS trg_leads_yo_bi;
DROP TRIGGER IF EXISTS trg_leads_yo_bu;
DROP TRIGGER IF EXISTS trg_results_yo_bi;
DROP TRIGGER IF EXISTS trg_results_yo_bu;

DELIMITER //
CREATE TRIGGER trg_clients_yo_bi BEFORE INSERT ON clients FOR EACH ROW
BEGIN
    SET NEW.surname = REPLACE(REPLACE(NEW.surname, 'ё', 'е'), 'Ё', 'Е'),
        NEW.name = REPLACE(REPLACE(NEW.name, 'ё', 'е'), 'Ё', 'Е');
END//
CREATE TRIGGER trg_clients_yo_bu BEFORE UPDATE ON clients FOR EACH ROW
BEGIN
    SET NEW.surname = REPLACE(REPLACE(NEW.surname, 'ё', 'е'), 'Ё', 'Е'),
        NEW.name = REPLACE(REPLACE(NEW.name, 'ё', 'е'), 'Ё', 'Е');
END//
-- до trg_leads_before_insert / trg_results_before_insert: карточка клиента
-- ищется и создаётся уже по нормализованным ФИО
CREATE TRIGGER trg_leads_yo_bi BEFORE INSERT ON leads FOR EACH ROW PRECEDES trg_leads_before_insert
BEGIN
    SET NEW.surname = REPLACE(REPLACE(NEW.surname, 'ё', 'е'), 'Ё', 'Е'),
        NEW.name = REPLACE(REPLACE(NEW.name, 'ё', 'е'), 'Ё', 'Е');
END//
CREATE TRIGGER trg_leads_yo_bu BEFORE UPDATE ON leads FOR EACH ROW
BEGIN
    SET NEW.surname = REPLACE(REPLACE(NEW.surname, 'ё', 'е'), 'Ё', 'Е'),
        NEW.name = REPLACE(REPLACE(NEW.name, 'ё', 'е'), 'Ё', 'Е');
END//
CREATE TRIGGER trg_results_yo_bi BEFORE INSERT ON results FOR EACH ROW PRECEDES trg_results_before_insert
BEGIN
    SET NEW.surname = REPLACE(REPLACE(NEW.surname, 'ё', 'е'), 'Ё', 'Е'),
        NEW.name = REPLACE(REPLACE(NEW.name, 'ё', 'е'), 'Ё', 'Е');
END//
CREATE TRIGGER trg_results_yo_bu BEFORE UPDATE ON results FOR EACH ROW
BEGIN
    SET NEW.surname = REPLACE(REPLACE(NEW.surname, 'ё', 'е'), 'Ё', 'Е'),
        NEW.name = REPLACE(REPLACE(NEW.name, 'ё', 'е'), 'Ё', 'Е');
END//
DELIMITER ;

-- существующие данные (триггеры BEFORE UPDATE сами нормализуют строку).
-- trg_leads_after_update переписывает phone/email карточки клиента данными
-- обновлённой заявки — сохраняем контакты карточек и возвращаем после.
DROP TEMPORARY TABLE IF EXISTS _yo_client_contacts;
CREATE TEMPORARY TABLE _yo_client_contacts AS SELECT id, phone, email FROM clients;
UPDATE clients SET surname = surname
WHERE surname LIKE BINARY '%ё%' OR surname LIKE BINARY '%Ё%' OR name LIKE BINARY '%ё%' OR name LIKE BINARY '%Ё%';
SELECT 'clients', ROW_COUNT();
UPDATE leads SET surname = surname
WHERE surname LIKE BINARY '%ё%' OR surname LIKE BINARY '%Ё%' OR name LIKE BINARY '%ё%' OR name LIKE BINARY '%Ё%';
SELECT 'leads', ROW_COUNT();
UPDATE results SET surname = surname
WHERE surname LIKE BINARY '%ё%' OR surname LIKE BINARY '%Ё%' OR name LIKE BINARY '%ё%' OR name LIKE BINARY '%Ё%';
SELECT 'results', ROW_COUNT();

-- сравнение побайтовое: collation ai_ci не видит разницу регистра
UPDATE clients c JOIN _yo_client_contacts t ON t.id = c.id
SET c.phone = t.phone, c.email = t.email
WHERE NOT (BINARY c.phone <=> BINARY t.phone) OR NOT (BINARY c.email <=> BINARY t.email);
SELECT 'contacts_restored', ROW_COUNT();
DROP TEMPORARY TABLE _yo_client_contacts;
