USE duathlon_222;

-- Город/страна участника — отображается под ФИ, как на Siberman
-- (src/siberman/migrations/001_init.sql: country/city, тот же паттерн).
-- Свободный текст, без справочника стран/ISO-кодов — фронтенд сравнивает
-- country с литералом 'Россия', чтобы решить, показывать страну или только
-- город (см. cityLabel() в static/js/siberman-common.js). Данные заполняются
-- вручную (Copernico их не отдаёт) — после этой миграции ждём список
-- город/страна по стартовым номерам от пользователя.
ALTER TABLE participants ADD COLUMN country VARCHAR(100) NOT NULL DEFAULT 'Россия';
ALTER TABLE participants ADD COLUMN city VARCHAR(100) NOT NULL DEFAULT '';
