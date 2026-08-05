-- Переключатель live-опроса Copernico для бегового этапа (задача 6 Live
-- v2) — независимая от самого поллер-процесса точка контроля: поллер
-- продолжает опрашивать Copernico постоянно, но apply_copernico_snapshot()
-- пропускает запись в БД, если флаг выключен. Управляется из админки, без
-- SSH/поиска процесса.
ALTER TABLE race_config
  ADD COLUMN copernico_run_enabled BOOLEAN NOT NULL DEFAULT FALSE;
