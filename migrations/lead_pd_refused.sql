-- Отказ от публикации ПД на заявке (2026-11-03, с Снежной семёрки 2026 согласие — на бумаге
-- при получении номера, отдельное на каждое событие). 1 — на публичных страницах вместо ФИ
-- «Спортсмен», без ДР и карточки. Ставится вручную в /admin → «Заявки». Идемпотентно.

SET @has_col := (SELECT COUNT(*) FROM information_schema.columns
                 WHERE table_schema = DATABASE() AND table_name = 'leads' AND column_name = 'pd_refused');
SET @ddl := IF(@has_col = 0,
    'ALTER TABLE leads ADD COLUMN pd_refused TINYINT(1) NOT NULL DEFAULT 0',
    'DO 0');
PREPARE st FROM @ddl;
EXECUTE st;
DEALLOCATE PREPARE st;
