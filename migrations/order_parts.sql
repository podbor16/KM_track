-- Разбор заказа на слот / допы / взнос для DataLens «Финансы» (2026-11-11, решение пользователя: полная разбивка с оговоркой).
-- km_order_parts: одна строка на заявку (без возвратов).
--   gross   — цена до скидки: число после «≡» в составе заказа, если он полный, иначе оплачено + скидка
--             (у 1 457 вебхук-заявок 2025 года сумма в leads = 0, а цена в составе есть);
--   charity — взнос «Счастливые дети» (число после «дети»:»);
--   addons  — сумма цен выбранных позиций «…+ 670 р: Добавить|Да|<размер>» (не «Не …»/«Нет»);
--   slot    — gross − addons − charity;
--   complete = 1, если состав заказа полный (есть «≡»). Обрезанный/пустой состав → допы и взнос не видны, всё в слот.
-- Ограничение: состав заказа пуст у прошедших импортированных событий 2024–2026 и обрезан у части вебхук-заказов.
-- Пересчёт — событие раз в час (требуется event_scheduler = ON). Таблица производная: при смене схемы —
-- DROP TABLE IF EXISTS km_order_parts перед CREATE.
-- Применять от root: mysql -u root krasmarafon < migrations/order_parts.sql

CREATE TABLE IF NOT EXISTS km_order_parts (
    lead_id       INT UNSIGNED   NOT NULL,
    gross         DECIMAL(16,2)  NOT NULL,
    discount      DECIMAL(16,2)  NOT NULL,
    paid          DECIMAL(16,2)  NOT NULL,
    addons        DECIMAL(16,2)  NOT NULL,
    charity       DECIMAL(16,2)  NOT NULL,
    slot          DECIMAL(16,2)  NOT NULL,
    complete      TINYINT        NOT NULL,
    refreshed_at  DATETIME       NOT NULL,
    PRIMARY KEY (lead_id)
) DEFAULT CHARSET = utf8mb4;

DROP PROCEDURE IF EXISTS refresh_order_parts;
DELIMITER //
CREATE DEFINER = `root`@`localhost` PROCEDURE refresh_order_parts()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN DO RELEASE_LOCK('refresh_order_parts'); RESIGNAL; END;
    IF COALESCE(GET_LOCK('refresh_order_parts', 60), 0) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'refresh_order_parts уже выполняется';
    END IF;
    SET SESSION lock_wait_timeout = 30;
    DROP TABLE IF EXISTS km_order_parts_new;
    CREATE TABLE km_order_parts_new LIKE km_order_parts;
    INSERT INTO km_order_parts_new (lead_id, gross, discount, paid, addons, charity, slot, complete, refreshed_at)
    WITH base AS (
        SELECT l.id,
               COALESCE(l.amount, 0) AS paid,
               COALESCE(l.discount, 0) AS discount,
               COALESCE(l.products, '') AS p,
               COALESCE(l.products, '') LIKE '%≡%' AS complete
        FROM leads l
        WHERE l.refund = 0
    ), n AS (
        SELECT 1 AS k UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6
        UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9 UNION ALL SELECT 10 UNION ALL SELECT 11 UNION ALL SELECT 12
    ), adds AS (
        SELECT b.id,
               SUM(CAST(REGEXP_SUBSTR(REGEXP_SUBSTR(b.p, '[0-9]+ *р[^:,)]*\\)?: *(?! )(?!Не|Нет)[^,)]+', 1, n.k), '^[0-9]+')
                        AS UNSIGNED)) AS addons
        FROM base b JOIN n ON b.complete
        WHERE REGEXP_SUBSTR(b.p, '[0-9]+ *р[^:,)]*\\)?: *(?! )(?!Не|Нет)[^,)]+', 1, n.k) IS NOT NULL
        GROUP BY b.id
    )
    SELECT b.id,
           IF(b.complete, COALESCE(CAST(REGEXP_SUBSTR(REGEXP_SUBSTR(b.p, '≡ *[0-9]+'), '[0-9]+$') AS UNSIGNED), b.paid + b.discount),
              b.paid + b.discount),
           b.discount,
           b.paid,
           IF(b.complete, COALESCE(a.addons, 0), 0),
           IF(b.complete, COALESCE(CAST(REGEXP_SUBSTR(REGEXP_SUBSTR(b.p, 'дети»: *[0-9]+'), '[0-9]+$') AS UNSIGNED), 0), 0),
           0, b.complete, NOW()
    FROM base b LEFT JOIN adds a ON a.id = b.id;
    UPDATE km_order_parts_new SET slot = gross - addons - charity;
    DROP TABLE IF EXISTS km_order_parts_old;
    RENAME TABLE km_order_parts TO km_order_parts_old, km_order_parts_new TO km_order_parts;
    DROP TABLE IF EXISTS km_order_parts_old;
    DO RELEASE_LOCK('refresh_order_parts');
END //
DELIMITER ;

CALL refresh_order_parts();

DROP EVENT IF EXISTS ev_refresh_order_parts;
CREATE DEFINER = `root`@`localhost` EVENT ev_refresh_order_parts
    ON SCHEDULE EVERY 1 HOUR STARTS CURRENT_TIMESTAMP + INTERVAL 9 MINUTE
    DO CALL refresh_order_parts();
