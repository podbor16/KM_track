CREATE DATABASE IF NOT EXISTS duathlon_222 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE duathlon_222;

CREATE TABLE IF NOT EXISTS events (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  code         VARCHAR(50) UNIQUE NOT NULL,
  name         VARCHAR(255) NOT NULL,
  gun_datetime DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS participants (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  event_id      INT NOT NULL,
  start_number  INT NOT NULL,
  surname       VARCHAR(255) NOT NULL,
  name          VARCHAR(255) NOT NULL,
  gender        ENUM('M','F') NOT NULL,
  status        ENUM('active','finished','dnf','dsq') NOT NULL DEFAULT 'active',
  -- Личное непрерывное время от общего массового старта (сек), NULL = этап ещё не пройден.
  run1_s        INT DEFAULT NULL,
  bike_s        INT DEFAULT NULL,
  run2_s        INT DEFAULT NULL,
  UNIQUE KEY uq_event_bib (event_id, start_number),
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

GRANT ALL PRIVILEGES ON duathlon_222.* TO 'km_analytic'@'%';
GRANT ALL PRIVILEGES ON duathlon_222.* TO 'km_analytic'@'localhost';
FLUSH PRIVILEGES;
