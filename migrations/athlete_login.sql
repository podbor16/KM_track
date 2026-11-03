-- Вход спортсмена по коду из почты (2026-11-03, спецификация 2026-11-03-athlete-login-design).
-- Коды и сессии — только хэши секретов. Идемпотентно (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS athlete_login_codes (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  code_hash CHAR(64) NOT NULL,
  link_hash CHAR(64) NOT NULL,
  ip VARCHAR(45) NOT NULL,
  attempts TINYINT NOT NULL DEFAULT 0,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_alc_email (email, created_at),
  KEY idx_alc_ip (ip, created_at),
  UNIQUE KEY uq_alc_link (link_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS athlete_sessions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  token_hash CHAR(64) NOT NULL,
  expires_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at DATETIME NULL,
  user_agent VARCHAR(255) NULL,
  UNIQUE KEY uq_as_token (token_hash),
  KEY idx_as_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
