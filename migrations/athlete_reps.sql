-- Личный кабинет Б2 (2026-11-04): представители карточки спортсмена (ребёнок, родитель, подопечный).
-- birthday — ДР карточки, подтверждённая представителем, доступ действует, пока clients.birthday совпадает.
-- У карточки может быть несколько представителей. Идемпотентно.

CREATE TABLE IF NOT EXISTS athlete_reps (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  client_id INT NOT NULL,
  birthday DATE NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ar (email, client_id),
  KEY idx_ar_client (client_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
