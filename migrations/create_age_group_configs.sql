-- Таблица настраиваемых возрастных групп (per event_name + event_distance,
-- без привязки к году) — заменяет единую хардкод-формулу
-- calculate_age_group() для регистраций (leads/стартовый список).
-- Результаты после финиша (results.category, из Copernico) НЕ затронуты —
-- сознательно вне объёма, категория там приходит из внешней системы.
-- 2026-08-17

CREATE TABLE IF NOT EXISTS age_group_configs (
  id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  event_name VARCHAR(100) NOT NULL,
  event_distance VARCHAR(50) NOT NULL,
  sex ENUM('M','F') NOT NULL,
  min_age INT UNSIGNED NOT NULL,
  max_age INT UNSIGNED NULL,      -- NULL = без верхней границы ("75+")
  label VARCHAR(20) NOT NULL,     -- "М49", "М50-59", "Ж75+"
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_bracket (event_name, event_distance, sex, min_age)
);

-- Сид дефолтными границами (переведены из старой calculate_age_group()
-- в компактный формат) для каждой уже существующей пары
-- (event_name, event_distance) в leads — компактный формат появляется
-- сразу везде, дальше можно переопределить через /admin.

INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'M', 0, 49, 'М49' FROM leads WHERE event_name != '' AND event_distance != '';
INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'M', 50, 59, 'М50-59' FROM leads WHERE event_name != '' AND event_distance != '';
INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'M', 60, 64, 'М60-64' FROM leads WHERE event_name != '' AND event_distance != '';
INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'M', 65, 69, 'М65-69' FROM leads WHERE event_name != '' AND event_distance != '';
INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'M', 70, 74, 'М70-74' FROM leads WHERE event_name != '' AND event_distance != '';
INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'M', 75, NULL, 'М75+' FROM leads WHERE event_name != '' AND event_distance != '';

INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'F', 0, 49, 'Ж49' FROM leads WHERE event_name != '' AND event_distance != '';
INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'F', 50, 59, 'Ж50-59' FROM leads WHERE event_name != '' AND event_distance != '';
INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'F', 60, 64, 'Ж60-64' FROM leads WHERE event_name != '' AND event_distance != '';
INSERT IGNORE INTO age_group_configs (event_name, event_distance, sex, min_age, max_age, label)
SELECT DISTINCT event_name, event_distance, 'F', 65, NULL, 'Ж65+' FROM leads WHERE event_name != '' AND event_distance != '';
