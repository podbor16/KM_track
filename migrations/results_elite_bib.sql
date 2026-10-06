-- «Элита» (2026-10-06): именной номер (фамилия вместо числа на Жаре 21,1 км) хранится
-- как start_number = 0, на сайте показывается «Элита». Уникальность номера в забеге —
-- для настоящих номеров: функциональный ключ по NULLIF(start_number, 0) — нулей
-- сколько угодно (NULL в уникальном ключе не конфликтует). Выполнять от root.
ALTER TABLE results
    DROP INDEX uq_results_event_start,
    ADD UNIQUE KEY uq_results_event_start (event_id, (NULLIF(start_number, 0)));
