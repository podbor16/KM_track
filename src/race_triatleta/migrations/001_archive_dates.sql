USE triatleta_24h;

-- Архивный протокол может содержать год и время суток без календарной даты.
SET @archive_year_exists := (SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'events' AND column_name = 'archive_year');
SET @archive_ddl := IF(@archive_year_exists = 0,
    'ALTER TABLE events ADD COLUMN archive_year SMALLINT DEFAULT NULL, MODIFY gun_datetime DATETIME DEFAULT NULL',
    'DO 0');
PREPARE tri_archive_stmt FROM @archive_ddl;
EXECUTE tri_archive_stmt;
DEALLOCATE PREPARE tri_archive_stmt;

SET @start_time_exists := (SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'participants' AND column_name = 'start_local_time');
SET @start_time_ddl := IF(@start_time_exists = 0,
    'ALTER TABLE participants ADD COLUMN start_local_time TIME DEFAULT NULL',
    'DO 0');
PREPARE tri_start_time_stmt FROM @start_time_ddl;
EXECUTE tri_start_time_stmt;
DEALLOCATE PREPARE tri_start_time_stmt;
