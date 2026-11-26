-- Стартовая волна заявки. Сейчас используется на 7 км «Снежной семёрки» 2026.
SET @ddl := IF(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'leads'
          AND column_name = 'start_wave'
    ),
    'SELECT 1',
    'ALTER TABLE leads ADD COLUMN start_wave TINYINT UNSIGNED NULL'
);
PREPARE add_leads_start_wave_stmt FROM @ddl;
EXECUTE add_leads_start_wave_stmt;
DEALLOCATE PREPARE add_leads_start_wave_stmt;
