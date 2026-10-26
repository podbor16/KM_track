-- Тексты заявки Тильды «Почему wild card» и «О результатах» (2026-10-26): в новом формате таблицы организаторов
-- их нет, берём из CSV-выгрузки заявок вместе с контактами. Хранятся здесь, чтобы пережить перезаливку таблицы шансов.
ALTER TABLE draw_contacts
  ADD COLUMN wildcard_reason TEXT NULL,
  ADD COLUMN results_text TEXT NULL;
