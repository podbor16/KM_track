-- Заявки на Siberman из формы Тильды (вебхук + разовый CSV), статусы директора гонки (2026-10-27,
-- спека docs/superpowers/specs/2026-10-27-siberman-entries-design.md). Одна строка — одна заявка (tranid Тильды);
-- повторная доставка обновляет поля формы, статус и комментарий не трогает.
CREATE TABLE IF NOT EXISTS siberman_entries (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  race_year         SMALLINT NOT NULL,
  tranid            VARCHAR(64) NOT NULL,
  formid            VARCHAR(64) NOT NULL DEFAULT '',
  submitted_at      DATETIME NOT NULL,
  format            ENUM('individual','relay') NOT NULL,
  surname           VARCHAR(100) NOT NULL,
  name              VARCHAR(100) NOT NULL,
  gender            ENUM('M','F') NULL,
  birthdate         DATE NULL,
  city              VARCHAR(150) NOT NULL DEFAULT '',
  email             VARCHAR(255) NOT NULL DEFAULT '',
  phone             VARCHAR(64) NOT NULL DEFAULT '',
  team_name         VARCHAR(150) NOT NULL DEFAULT '',
  relay_swim        VARCHAR(255) NOT NULL DEFAULT '',
  relay_bike        VARCHAR(255) NOT NULL DEFAULT '',
  relay_run         VARCHAR(255) NOT NULL DEFAULT '',
  wildcard_reason   TEXT NULL,
  results_text      TEXT NULL,
  result_url        VARCHAR(500) NOT NULL DEFAULT '',
  raw               JSON NULL,
  status            ENUM('review','admitted','rejected','withdrawn') NOT NULL DEFAULT 'review',
  comment           TEXT NULL,
  status_updated_at DATETIME NULL,
  status_by         VARCHAR(64) NOT NULL DEFAULT '',
  UNIQUE KEY uq_entries_tranid (tranid),
  KEY idx_entries_year_time (race_year, submitted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS siberman_entries_audit (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  entry_id    INT NOT NULL,
  action      ENUM('status','comment') NOT NULL,
  old_value   TEXT NULL,
  new_value   TEXT NULL,
  admin_user  VARCHAR(64) NOT NULL DEFAULT '',
  created_at  DATETIME NOT NULL,
  KEY idx_entries_audit_entry (entry_id),
  CONSTRAINT fk_entries_audit_entry FOREIGN KEY (entry_id) REFERENCES siberman_entries (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
