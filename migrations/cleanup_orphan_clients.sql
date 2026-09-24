-- Клиенты без заявок и без результатов: карточки, чьи результаты удалили или
-- перезалили. Их создаёт trg_results_before_insert, а при удалении результатов
-- никто не убирает. На 2026-09-24 таких 3375, завышали число клиентов.
-- Выполнять после add_results_after_delete_trigger.sql. Идемпотентно.

DELETE c FROM clients c
WHERE c.id <> 0
  AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.client_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM results r WHERE r.client_id = c.id);

SELECT ROW_COUNT() AS orphan_clients_deleted;
