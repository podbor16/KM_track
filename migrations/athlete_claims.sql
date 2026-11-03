-- Личный кабинет Б1 (2026-11-03): привязка карточки спортсмена к аккаунту-почте («Это я»).
-- birthday — ДР, подтверждённая человеком; привязка действует, пока clients.birthday совпадает.
-- Идемпотентно.

CREATE TABLE IF NOT EXISTS athlete_claims (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  client_id INT NOT NULL,
  birthday DATE NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ac_client (client_id),
  KEY idx_ac_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS athlete_claim_attempts (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  client_id INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_aca (email, client_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
