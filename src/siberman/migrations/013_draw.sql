-- Жеребьёвка регистраций Siberman (с 2028). Все таблицы — по году жеребьёвки,
-- жеребьёвка 2029 не затрёт 2028. Спецификация:
-- docs/superpowers/specs/2026-10-14-siberman-draw-2028-design.md
CREATE TABLE IF NOT EXISTS draw_applicants (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  draw_year          SMALLINT NOT NULL,
  format             ENUM('individual','relay') NOT NULL,
  surname            VARCHAR(100) NOT NULL,
  name               VARCHAR(100) NOT NULL DEFAULT '',
  gender             ENUM('M','F') DEFAULT NULL,
  city               VARCHAR(100) NOT NULL DEFAULT '',
  pool               ENUM('wildcard','relay','repeat','novice') NOT NULL,
  is_wildcard        BOOLEAN NOT NULL DEFAULT FALSE,
  chances            SMALLINT NOT NULL,
  starts_individual  SMALLINT NOT NULL DEFAULT 0,
  starts_relay       SMALLINT NOT NULL DEFAULT 0,
  draw_accumulated   SMALLINT NOT NULL DEFAULT 0,
  is_local           SMALLINT NOT NULL DEFAULT 0,
  duathlon_222       SMALLINT NOT NULL DEFAULT 0,
  race_24h           SMALLINT NOT NULL DEFAULT 0,
  tattoo             SMALLINT NOT NULL DEFAULT 0,
  relay_swim         VARCHAR(200) NOT NULL DEFAULT '',
  relay_bike         VARCHAR(200) NOT NULL DEFAULT '',
  relay_run          VARCHAR(200) NOT NULL DEFAULT '',
  wildcard_reason    TEXT,
  results_text       TEXT,
  payment_status     ENUM('none','pending','paid','unpaid') NOT NULL DEFAULT 'none',
  payment_comment    VARCHAR(500) NOT NULL DEFAULT '',
  payment_updated_at DATETIME DEFAULT NULL,
  UNIQUE KEY uq_draw_person (draw_year, format, surname, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- version увеличивается каждой записью — по нему публичный кэш понимает, что
-- снимок устарел. Строка года блокируется (FOR UPDATE) на время каждой записи.
CREATE TABLE IF NOT EXISTS draw_config (
  draw_year          SMALLINT PRIMARY KEY,
  capacity_men       SMALLINT DEFAULT NULL,
  capacity_women     SMALLINT DEFAULT NULL,
  capacity_relay     SMALLINT DEFAULT NULL,
  quota_repeat_men   SMALLINT DEFAULT NULL,
  quota_repeat_women SMALLINT DEFAULT NULL,
  quota_novice_men   SMALLINT DEFAULT NULL,
  quota_novice_women SMALLINT DEFAULT NULL,
  current_round      TINYINT NOT NULL DEFAULT 0,
  auto_invite_until  DATE DEFAULT NULL,
  imported_at        DATETIME DEFAULT NULL,
  version            INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Журнал вытягиваний. Порядок в зачёте — position_key (у новой записи = её id,
-- у исправления — position_key заменённой). Отмена/исправление не удаляют строку.
CREATE TABLE IF NOT EXISTS draw_picks (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  draw_year     SMALLINT NOT NULL,
  applicant_id  INT NOT NULL,
  round         TINYINT NOT NULL,
  category      ENUM('men','women','relay') NOT NULL,
  position_key  INT NOT NULL DEFAULT 0,
  created_at    DATETIME NOT NULL,
  cancelled_at  DATETIME DEFAULT NULL,
  replaced_by   INT DEFAULT NULL,
  KEY ix_draw_picks_year (draw_year),
  FOREIGN KEY (applicant_id) REFERENCES draw_applicants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS draw_audit (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  draw_year        SMALLINT NOT NULL,
  applicant_id     INT NOT NULL,
  action           VARCHAR(30) NOT NULL,
  old_value        VARCHAR(200) NOT NULL DEFAULT '',
  new_value        VARCHAR(200) NOT NULL DEFAULT '',
  ref_applicant_id INT DEFAULT NULL,
  admin_user       VARCHAR(100) NOT NULL DEFAULT '',
  created_at       DATETIME NOT NULL,
  KEY ix_draw_audit_year (draw_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
