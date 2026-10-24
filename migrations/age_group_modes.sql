-- Режим расчёта возраста для возрастной группы — на событие+дистанцию, как age_group_configs
-- (/admin → «Возрастные группы», src/analytics/db_results.py: _age_for_group()).
--   birth_year — на 31.12 года забега (год забега − год рождения); нет записи = birth_year
--   event_date — полных лет на день старта (events.event_date; даты нет — как birth_year)
-- 2026-10-24. Идемпотентно.

CREATE TABLE IF NOT EXISTS age_group_modes (
  event_name VARCHAR(100) NOT NULL,
  event_distance VARCHAR(50) NOT NULL,
  mode ENUM('birth_year', 'event_date') NOT NULL DEFAULT 'birth_year',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (event_name, event_distance)
);
