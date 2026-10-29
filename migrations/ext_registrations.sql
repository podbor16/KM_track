-- Внешние регистрации (сборный дамп Tilda «Бум.xlsx», 2016–2022, все забеги) — справочник для «Качества данных»:
-- настоящие ДР для заглушек, двойники по телефону/почте, расхождения ДР. Не заявки: в leads не попадают.
CREATE TABLE IF NOT EXISTS ext_registrations (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(40) NOT NULL,
    source_row INT UNSIGNED NOT NULL,
    surname VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    birthday DATE NULL,
    sex CHAR(1) NOT NULL DEFAULT '',
    phone VARCHAR(10) NOT NULL DEFAULT '',
    email VARCHAR(255) NOT NULL DEFAULT '',
    product VARCHAR(255) NOT NULL DEFAULT '',
    event_year SMALLINT UNSIGNED NULL,
    UNIQUE KEY uq_ext_source_row (source, source_row),
    KEY idx_ext_surname (surname),
    KEY idx_ext_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
