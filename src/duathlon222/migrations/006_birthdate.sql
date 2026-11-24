USE duathlon_222;

SET @birthdate_exists := (SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'participants' AND column_name = 'birthdate');
SET @birthdate_ddl := IF(@birthdate_exists = 0,
    'ALTER TABLE participants ADD COLUMN birthdate DATE DEFAULT NULL',
    'DO 0');
PREPARE duathlon_birthdate_stmt FROM @birthdate_ddl;
EXECUTE duathlon_birthdate_stmt;
DEALLOCATE PREPARE duathlon_birthdate_stmt;
