-- Ссылки на фото участников для live-топ-10 трансляции Жары. Заполняется
-- вручную через /admin — организатор один раз до гонки переносит ссылки из
-- анкеты элитного кластера (внешняя гугл-форма, синхронизация с ней вне
-- объёма). У кого нет записи здесь — в JSON подставляется общая заглушка
-- (см. src/krasmarafon/services/live_top10_export.py).
-- 2026-08-18

CREATE TABLE IF NOT EXISTS participant_photos (
  id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  event_id INT UNSIGNED NOT NULL,
  start_number INT UNSIGNED NOT NULL,
  photo_url VARCHAR(500) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_participant_photo (event_id, start_number)
);
