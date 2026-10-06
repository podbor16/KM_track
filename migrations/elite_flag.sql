-- «Элита» (2026-10-06, пока только Жара 21,1 км): у элитного спортсмена настоящий номер
-- (по нему — диплом), на сайте вместо номера — «Элита». Отметка, а не особый номер.
-- Результаты: ставит загрузчик Copernico / scripts/import_results_xlsx.py (src/analytics/elite.py);
-- заявки: кнопка «Элита» в /admin или «Элита» в колонке «Номер» импорта.
ALTER TABLE results ADD COLUMN is_elite TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN is_elite TINYINT(1) NOT NULL DEFAULT 0;
