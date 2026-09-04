USE duathlon_222;

-- Точный момент ВХОДА на следующий этап (конец транзитной зоны) — сырые
-- поля Copernico напрямую (bike0 для Т1→Вело, finish_T2-start_R2 для
-- Т2→Бег-2), а не реконструкция run1_s+t1_s/bike_s+t2_s. Та реконструкция
-- теряет до 1-2с из-за раздельного округления run1_s и t1_s каждого до
-- целых секунд ДО сложения — найдено пользователем 2026-09-04.
-- _stage_start_s() в service.py предпочитает эти колонки, если заполнены,
-- иначе падает обратно на старую реконструкцию (для строк без них,
-- например тестовых участников, вписанных вручную SQL).
ALTER TABLE participants ADD COLUMN bike_start_s INT DEFAULT NULL;
ALTER TABLE participants ADD COLUMN run2_start_s INT DEFAULT NULL;
