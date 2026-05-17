-- Составной индекс: устраняет filesort в главном запросе
-- WHERE event_id = X ORDER BY time_clear_finish ASC
ALTER TABLE results
  ADD INDEX idx_event_finish (event_id, time_clear_finish);
