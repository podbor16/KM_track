-- Реальный пол участника эстафеты (М/Ж), отдельно от gender='E' (маркер
-- формата "эстафета", используемый для фильтрации в рейтингах).
-- Для формата "Лично" дублирует gender для единообразия выборок.
ALTER TABLE participants ADD COLUMN member_gender ENUM('M','F') DEFAULT NULL AFTER gender;
