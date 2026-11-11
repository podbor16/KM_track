-- Нормализация клубов для DataLens «Топ клубов» (2026-11-11, решения пользователя).
-- club_names: написание клуба (как в clients/leads) → клуб. Ключ = нижний регистр без пробелов и знаков
-- (ё→е); у одного ключа — самое частое написание. Правила склейки:
--   *supersport*, *ilovetriathlon* → «I Love Supersport»; *полюс* → «Полюс»; *рнванкор* → «РН-Ванкор».
--   «КЛБ …» и региональные отделения (Бегодевочки Абакан и т.п.) НЕ склеиваются.
-- «Не клуб» (noclub, Лично, Красноярск, Нет, «-», Без клуба…) → NULL.
-- Пересчёт — событие раз в час (требуется event_scheduler = ON). Таблица производная: при смене схемы —
-- DROP TABLE IF EXISTS club_names перед CREATE.
-- Применять от root: mysql -u root krasmarafon < migrations/club_names.sql

CREATE TABLE IF NOT EXISTS club_names (
    club          VARCHAR(768) NOT NULL,   -- clients/leads.club — TEXT (максимум 282 символа); 768 — предел ключа InnoDB
    club_key      VARCHAR(768) NOT NULL,
    club_name     VARCHAR(768) NULL,
    refreshed_at  DATETIME     NOT NULL,
    PRIMARY KEY (club)
) DEFAULT CHARSET = utf8mb4;

DROP PROCEDURE IF EXISTS refresh_club_names;
DELIMITER //
CREATE DEFINER = `root`@`localhost` PROCEDURE refresh_club_names()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN DO RELEASE_LOCK('refresh_club_names'); RESIGNAL; END;
    IF COALESCE(GET_LOCK('refresh_club_names', 60), 0) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'refresh_club_names уже выполняется';
    END IF;
    SET SESSION lock_wait_timeout = 30;
    DROP TABLE IF EXISTS club_names_new;
    CREATE TABLE club_names_new LIKE club_names;
    INSERT INTO club_names_new (club, club_key, club_name, refreshed_at)
    WITH src AS (
        SELECT TRIM(club) AS club FROM clients WHERE club IS NOT NULL
        UNION ALL
        SELECT TRIM(club) FROM leads WHERE club IS NOT NULL
    ), v AS (
        SELECT MIN(club) AS club,
               LOWER(REGEXP_REPLACE(REPLACE(REPLACE(MIN(club), 'ё', 'е'), 'Ё', 'Е'), '[^[:alnum:]+]', '')) AS k,
               COUNT(*) AS n
        FROM src GROUP BY club
    ), best AS (
        SELECT k, club AS name
        FROM (SELECT k, club, ROW_NUMBER() OVER (PARTITION BY k ORDER BY n DESC, club) AS rn FROM v) t
        WHERE rn = 1
    )
    SELECT v.club, v.k,
           CASE
               WHEN CHAR_LENGTH(v.k) < 2 OR v.k REGEXP '^[0-9]+$'
                    OR v.k IN ('noclub', 'лично', 'красноярск', 'нет', 'нету', 'безклуба', 'нетклуба', 'несостою',
                               'самзасебя', 'сампосебе', 'одиночка', 'null', 'none', 'na', 'нд', 'no')
                   THEN NULL
               WHEN v.k LIKE '%supersport%' OR v.k LIKE '%ilovetriathlon%' THEN 'I Love Supersport'
               WHEN v.k LIKE '%полюс%' THEN 'Полюс'
               WHEN v.k LIKE '%рнванкор%' THEN 'РН-Ванкор'
               ELSE b.name
           END,
           NOW()
    FROM v JOIN best b ON b.k = v.k;
    DROP TABLE IF EXISTS club_names_old;
    RENAME TABLE club_names TO club_names_old, club_names_new TO club_names;
    DROP TABLE IF EXISTS club_names_old;
    DO RELEASE_LOCK('refresh_club_names');
END //
DELIMITER ;

CALL refresh_club_names();

DROP EVENT IF EXISTS ev_refresh_club_names;
CREATE DEFINER = `root`@`localhost` EVENT ev_refresh_club_names
    ON SCHEDULE EVERY 1 HOUR STARTS CURRENT_TIMESTAMP + INTERVAL 7 MINUTE
    DO CALL refresh_club_names();
