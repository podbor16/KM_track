-- Переходы дистанций для DataLens (2026-11-09, spec docs/superpowers/specs/2026-11-09-datalens-distance-transitions-design.md).
-- Одна строка на участие человека в забеге в году; пары «тот же забег» и «любой забег» — оконными LAG.
-- Считается ~3 с, поэтому таблица материализуется и пересчитывается событием раз в час (требуется event_scheduler = ON, проверить `SELECT @@event_scheduler`).
-- Таблица целиком производная: при смене схемы — DROP TABLE IF EXISTS km_transitions перед CREATE, без ALTER.
-- Применять от root: mysql -u root krasmarafon < migrations/km_transitions.sql
-- 2026-11-11: + n_dist/distances (мультидистанции: сколько и какие дистанции человек бежал на забеге в году).

DROP TABLE IF EXISTS km_transitions;

CREATE TABLE IF NOT EXISTS km_transitions (
    client_id       INT UNSIGNED  NOT NULL,
    event_name      VARCHAR(255)  NOT NULL,
    event_year      INT           NOT NULL,
    event_distance  VARCHAR(64)   NULL,
    dist            DECIMAL(5,1)  NULL,
    same_prev_year  INT           NULL,
    same_prev_dist  DECIMAL(5,1)  NULL,
    same_direction  VARCHAR(32)   NULL,
    any_prev_event  VARCHAR(255)  NULL,
    any_prev_year   INT           NULL,
    any_prev_dist   DECIMAL(5,1)  NULL,
    n_dist          INT           NOT NULL DEFAULT 1,
    distances       VARCHAR(255)  NULL,
    refreshed_at    DATETIME      NOT NULL,
    PRIMARY KEY (client_id, event_name, event_year),
    KEY idx_event (event_name, event_year)
) DEFAULT CHARSET = utf8mb4;

DROP PROCEDURE IF EXISTS refresh_km_transitions;
DELIMITER //
CREATE DEFINER = `root`@`localhost` PROCEDURE refresh_km_transitions()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN DO RELEASE_LOCK('refresh_km_transitions'); RESIGNAL; END;
    IF GET_LOCK('refresh_km_transitions', 60) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'refresh_km_transitions уже выполняется';
    END IF;
    SET SESSION lock_wait_timeout = 30;
    DROP TABLE IF EXISTS km_transitions_new;
    CREATE TABLE km_transitions_new LIKE km_transitions;
    INSERT INTO km_transitions_new
        (client_id, event_name, event_year, event_distance, dist, same_prev_year, same_prev_dist,
         same_direction, any_prev_event, any_prev_year, any_prev_dist, n_dist, distances, refreshed_at)
    WITH occ AS (
        SELECT l.client_id, l.event_name, CAST(l.event_year AS UNSIGNED) AS event_year,
               MIN(COALESCE(e.event_date, MAKEDATE(CAST(l.event_year AS UNSIGNED), 183))) AS ev_date,
               MAX(e.event_distance + 0) AS dist,
               SUBSTRING_INDEX(GROUP_CONCAT(l.event_distance ORDER BY e.event_distance + 0 DESC SEPARATOR '|'), '|', 1)
                   AS event_distance,
               COUNT(DISTINCT l.event_distance) AS n_dist,
               GROUP_CONCAT(DISTINCT l.event_distance ORDER BY e.event_distance + 0 SEPARATOR ' + ') AS distances
        FROM leads l JOIN events e ON l.event_id = e.id
        WHERE l.refund = 0 AND l.client_id > 0
        GROUP BY l.client_id, l.event_name, l.event_year
    ), w AS (
        SELECT occ.*,
               LAG(event_year) OVER (PARTITION BY client_id, event_name ORDER BY event_year) AS same_prev_year,
               LAG(dist)       OVER (PARTITION BY client_id, event_name ORDER BY event_year) AS same_prev_dist,
               LAG(event_name) OVER (PARTITION BY client_id ORDER BY ev_date, event_year, event_name) AS any_prev_event,
               LAG(event_year) OVER (PARTITION BY client_id ORDER BY ev_date, event_year, event_name) AS any_prev_year,
               LAG(dist)       OVER (PARTITION BY client_id ORDER BY ev_date, event_year, event_name) AS any_prev_dist
        FROM occ
    )
    SELECT client_id, event_name, event_year, event_distance, dist,
           IF(event_name = 'Детский забег', NULL, same_prev_year),
           IF(event_name = 'Детский забег', NULL, same_prev_dist),
           CASE WHEN event_name = 'Детский забег' THEN NULL
                WHEN same_prev_dist IS NULL THEN 'Впервые на забеге'
                WHEN dist > same_prev_dist THEN 'Выросли'
                WHEN dist < same_prev_dist THEN 'Сократили'
                ELSE 'Та же дистанция' END,
           any_prev_event, any_prev_year, any_prev_dist, n_dist, distances, NOW()
    FROM w;
    DROP TABLE IF EXISTS km_transitions_old;
    RENAME TABLE km_transitions TO km_transitions_old, km_transitions_new TO km_transitions;
    DROP TABLE IF EXISTS km_transitions_old;
    DO RELEASE_LOCK('refresh_km_transitions');
END //
DELIMITER ;

CALL refresh_km_transitions();

DROP EVENT IF EXISTS ev_refresh_km_transitions;
CREATE DEFINER = `root`@`localhost` EVENT ev_refresh_km_transitions
    ON SCHEDULE EVERY 1 HOUR STARTS CURRENT_TIMESTAMP + INTERVAL 5 MINUTE
    DO CALL refresh_km_transitions();
