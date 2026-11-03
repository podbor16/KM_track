-- Кабинет Tilda покупателя в заявке (2026-11-03, задача «вход спортсмена»).
-- Вебхук Tilda присылает ma_id/ma_email (аккаунт, с которого куплено) отдельно от email формы;
-- раньше они выбрасывались. Нужны, чтобы сверить почту формы с почтой кабинета и потом
-- находить заявки человека по его кабинету. Идемпотентно.

SET @has_col := (SELECT COUNT(*) FROM information_schema.columns
                 WHERE table_schema = DATABASE() AND table_name = 'leads' AND column_name = 'ma_id');
SET @ddl := IF(@has_col = 0,
    'ALTER TABLE leads ADD COLUMN ma_id VARCHAR(32) NULL AFTER phone, ADD COLUMN ma_email VARCHAR(255) NULL AFTER ma_id',
    'DO 0');
PREPARE st FROM @ddl;
EXECUTE st;
DEALLOCATE PREPARE st;
