-- «Пейсер» (2026-10-06): пейсмейкеры и замыкающие Жары 21,1 км — в Copernico вместо номера
-- текст, номер в results служебный (максимальный + 1000…). На сайте вместо номера — «Пейсер»,
-- как «Элита» (elite_flag.sql). Ставят загрузчик/импорт (src/analytics/elite.py), в заявках —
-- «Пейсер» в колонке «Номер» импорта.
ALTER TABLE results ADD COLUMN is_pacer TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN is_pacer TINYINT(1) NOT NULL DEFAULT 0;
