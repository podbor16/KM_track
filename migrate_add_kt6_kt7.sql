-- Миграция: добавить kt6 и kt7 в таблицу results
-- Нужна для Первомайского полумарафона (7 промежуточных КТ)

ALTER TABLE results
    ADD COLUMN time_clear_kt6    TIME         DEFAULT NULL AFTER time_clear_kt5,
    ADD COLUMN time_clear_kt7    TIME         DEFAULT NULL AFTER time_clear_kt6,
    ADD COLUMN pace_avg_kt6      VARCHAR(10)  DEFAULT NULL AFTER pace_avg_kt5,
    ADD COLUMN pace_avg_kt7      VARCHAR(10)  DEFAULT NULL AFTER pace_avg_kt6,
    ADD COLUMN rank_absolute_kt6 VARCHAR(50)  DEFAULT NULL AFTER rank_absolute_kt5,
    ADD COLUMN rank_absolute_kt7 VARCHAR(50)  DEFAULT NULL AFTER rank_absolute_kt6,
    ADD COLUMN rank_sex_kt6      VARCHAR(50)  DEFAULT NULL AFTER rank_sex_kt5,
    ADD COLUMN rank_sex_kt7      VARCHAR(50)  DEFAULT NULL AFTER rank_sex_kt6,
    ADD COLUMN rank_category_kt6 VARCHAR(50)  DEFAULT NULL AFTER rank_category_kt5,
    ADD COLUMN rank_category_kt7 VARCHAR(50)  DEFAULT NULL AFTER rank_category_kt6;
