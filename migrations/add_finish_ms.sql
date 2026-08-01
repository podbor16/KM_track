-- Точное время финиша (мс от Copernico) — только для тай-брейка при подсчёте
-- мест внутри одной и той же целой секунды (см. load_race_results.py
-- _recalculate_ranks). Отображаемые time_gun_finish/time_clear_finish
-- (TIME, HH:MM:SS) не меняются и не трогаются этой миграцией.
ALTER TABLE results
  ADD COLUMN IF NOT EXISTS time_gun_finish_ms INT NULL
    COMMENT 'Точное официальное время финиша в мс от Copernico — только тай-брейк для мест, не для отображения',
  ADD COLUMN IF NOT EXISTS time_clear_finish_ms INT NULL
    COMMENT 'Точное чистое время финиша в мс от Copernico — аналогично';
