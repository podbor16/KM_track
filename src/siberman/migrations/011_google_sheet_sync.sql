-- Live-синхронизация данных Siberman из Google-таблицы (альтернатива
-- ручной Excel-загрузке, переключается в админке) — задача, аналогичная
-- Copernico-тумблеру (010), но для всех этапов сразу (не только бега).
-- google_sheet_last_hash хранит sha256 последнего ПРИМЕНЁННОГО содержимого
-- .xlsx-экспорта таблицы, чтобы поллер не перезаписывал БД на каждом
-- цикле опроса, если в таблице ничего не изменилось.
ALTER TABLE race_config
  ADD COLUMN google_sheet_id VARCHAR(200) NULL,
  ADD COLUMN google_sheet_sync_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN google_sheet_last_hash VARCHAR(64) NULL;
