-- Миграция: добавить поля чистых мест в таблицу results
-- Применить: mysql -u USER -p DB_NAME < migrations/add_clean_ranks.sql

ALTER TABLE results
  ADD COLUMN IF NOT EXISTS rank_absolute_clean INT NULL COMMENT 'Абсолютное место по чистому времени',
  ADD COLUMN IF NOT EXISTS rank_sex_clean      INT NULL COMMENT 'Место среди пола по чистому времени',
  ADD COLUMN IF NOT EXISTS rank_category_clean INT NULL COMMENT 'Место в категории по чистому времени';
