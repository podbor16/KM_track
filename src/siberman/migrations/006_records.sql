-- Рекорды Siberman Ultra Triathlon — не привязаны к race_year (действуют
-- "навсегда", пока не побиты). column_key: 'overall' | 'swim' | 'bike_total'
-- | 'run' (в будущем можно добавить 'bike_day1'/'bike_day2'/'day1'/'day2',
-- если появятся данные). category: 'absolute' | 'male' | 'female' |
-- 'male_individual' | 'female_individual' — 'male'/'female' считают и
-- эстафетчиков (у них есть реальный личный пол на этапах/Своде вело),
-- '..._individual' — только личный зачёт. holder_team — NULL у личников.
CREATE TABLE IF NOT EXISTS siberman_records (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  column_key    VARCHAR(20) NOT NULL,
  category      VARCHAR(20) NOT NULL,
  best_s        INT NOT NULL,
  holder_name   VARCHAR(255) NOT NULL,
  holder_team   VARCHAR(255) DEFAULT NULL,
  year_set      SMALLINT DEFAULT NULL,
  UNIQUE KEY uq_column_category (column_key, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO siberman_records (column_key, category, best_s, holder_name, holder_team, year_set) VALUES
  ('overall',    'absolute',        71429, 'Князев Максим',                      NULL,               2023),
  ('overall',    'female_individual', 95387, 'Князева (Заволокина) Олеся',       NULL,               2024),

  ('swim',       'male_individual',  8647, 'Летницкий Дмитрий',                  NULL,               2025),
  ('swim',       'female_individual', 12570, 'Nuppu Hepo-Oja',                   NULL,               2019),
  ('swim',       'absolute',          7588, 'Бурдин Михаил',                     'Триатлета',        2023),
  ('swim',       'female',            9330, 'Николаева Наталья',                 'Ferrum W',         2023),

  ('bike_total', 'absolute',         38943, 'Князев Максим',                     NULL,               2023),
  ('bike_total', 'female_individual', 51112, 'Князева (Заволокина) Олеся',       NULL,               2024),
  ('bike_total', 'female',            47671, 'Острикова Екатерина',              'Женская команда',  2020),

  ('run',        'male_individual',  22793, 'Князев Максим',                     NULL,               2023),
  ('run',        'female_individual', 29795, 'Баранова Анастасия',               NULL,               2024),
  ('run',        'absolute',         21852, 'Тарасов Павел',                     'Автобаланс',       2025),
  ('run',        'female',           28115, 'Мартынова Олеся',                   'KukRusKlan W',     2024)
ON DUPLICATE KEY UPDATE
  best_s = VALUES(best_s), holder_name = VALUES(holder_name),
  holder_team = VALUES(holder_team), year_set = VALUES(year_set);
