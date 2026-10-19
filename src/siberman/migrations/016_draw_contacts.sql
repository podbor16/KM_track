-- Контакты заявителей жеребьёвки (e-mail, телефон) из выгрузки заявок Тильды — для счетов на оплату слота
-- (Excel в админке, 2026-10-19). Отдельно от draw_applicants: перезаливка таблицы организаторов пересоздаёт
-- заявки, а контакты привязаны к формату и ФИ (как ключ заявки в importer.applicant_key) и сохраняются.
-- Публично не отдаются: в снимок жеребьёвки не загружаются.
CREATE TABLE IF NOT EXISTS draw_contacts (
  draw_year  SMALLINT NOT NULL,
  format     ENUM('individual','relay') NOT NULL,
  fio_key    VARCHAR(255) NOT NULL,
  email      VARCHAR(255) NOT NULL DEFAULT '',
  phone      VARCHAR(64) NOT NULL DEFAULT '',
  PRIMARY KEY (draw_year, format, fio_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
