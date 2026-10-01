-- Качество данных: запомненные решения по находкам и журнал действий (2026-10-01).
-- Находки считаются на лету (src/analytics/data_quality.py, ~3 с на всю базу) — таблицы для
-- них нет. dq_decisions — «разные люди»/«оставить как есть», чтобы находка не всплывала
-- снова; dq_actions — что сделано из /admin или ночным прогоном, со снимком «до».
-- Идемпотентно.

CREATE TABLE IF NOT EXISTS dq_decisions (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    finding_key VARCHAR(120) NOT NULL,
    decision VARCHAR(30) NOT NULL,
    note VARCHAR(500) NOT NULL DEFAULT '',
    decided_by VARCHAR(100) NOT NULL DEFAULT '',
    decided_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_dq_decisions_key (finding_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS dq_actions (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    action VARCHAR(30) NOT NULL,
    finding_key VARCHAR(120) NOT NULL DEFAULT '',
    details JSON NOT NULL,
    done_by VARCHAR(100) NOT NULL DEFAULT '',
    done_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_dq_actions_done_at (done_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
