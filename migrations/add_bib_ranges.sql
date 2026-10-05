-- Диапазоны стартовых номеров для кнопки «Присвоить номера» в /admin (2026-10-05).
-- Запоминаются на событие (без года) — в следующем году подставятся в форму.
-- group_key: '' — вся дистанция; год рождения — для Детского забега (src/analytics/bibs.py).
-- Идемпотентно.

CREATE TABLE IF NOT EXISTS bib_ranges (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(255) NOT NULL,
    distance VARCHAR(50) NOT NULL,
    group_key VARCHAR(20) NOT NULL DEFAULT '',
    range_start INT UNSIGNED NOT NULL,
    range_end INT UNSIGNED NOT NULL,
    updated_by VARCHAR(100) NOT NULL DEFAULT '',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_bib_ranges (event_name, distance, group_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
