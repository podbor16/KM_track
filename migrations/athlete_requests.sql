-- Личный кабинет Б3 (2026-11-04): обращения (спор за карточку, «не мой забег», «не могу найти себя») и попытки поиска.
-- Идемпотентно.

CREATE TABLE IF NOT EXISTS athlete_requests (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  kind VARCHAR(16) NOT NULL,
  client_id INT NULL,
  row_table VARCHAR(16) NULL,
  row_id BIGINT NULL,
  payload JSON NULL,
  comment VARCHAR(1000) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'new',
  resolution VARCHAR(16) NULL,
  answer VARCHAR(1000) NULL,
  resolved_by VARCHAR(255) NULL,
  resolved_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_areq_status (status, created_at),
  KEY idx_areq_email (email, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS athlete_find_attempts (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_afa (email, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
