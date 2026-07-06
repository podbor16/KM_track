CREATE TABLE IF NOT EXISTS participants (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  race_year           SMALLINT NOT NULL,
  bib                 VARCHAR(10) NOT NULL,
  surname             VARCHAR(100) NOT NULL,
  name                VARCHAR(100) NOT NULL,
  gender              ENUM('M','F') NOT NULL,
  country             VARCHAR(100) NOT NULL DEFAULT 'Россия',
  city                VARCHAR(100) NOT NULL DEFAULT '',
  format              ENUM('individual','relay') NOT NULL DEFAULT 'individual',
  relay_team_name     VARCHAR(200) DEFAULT NULL,
  relay_stage         ENUM('none','swim','bike','run') NOT NULL DEFAULT 'none',
  status              ENUM('active','dnf','dns','dsq') NOT NULL DEFAULT 'active',
  dnf_stage           ENUM('swim','bike_day1','bike_day2','run') DEFAULT NULL,
  bike_day2_handicap_s INT DEFAULT NULL,
  -- relay team: 3 members share the same bib, distinguished by relay_stage
  UNIQUE KEY uq_year_bib_stage (race_year, bib, relay_stage)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS checkpoints (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  race_year   SMALLINT NOT NULL,
  stage       ENUM('swim','bike_day1','bike_day2','run') NOT NULL,
  seq         TINYINT NOT NULL,
  label       VARCHAR(100) NOT NULL,
  distance_km DECIMAL(6,2) NOT NULL,
  UNIQUE KEY uq_year_stage_seq (race_year, stage, seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS checkpoint_times (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  participant_id INT NOT NULL,
  checkpoint_id  INT NOT NULL,
  cumulative_s   INT DEFAULT NULL,
  split_s        INT DEFAULT NULL,
  UNIQUE KEY uq_part_cp (participant_id, checkpoint_id),
  FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
  FOREIGN KEY (checkpoint_id)  REFERENCES checkpoints(id)  ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS transitions (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  participant_id INT NOT NULL,
  zone           ENUM('T1','T2') NOT NULL,
  duration_s     INT DEFAULT NULL,
  UNIQUE KEY uq_part_zone (participant_id, zone),
  FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS stage_totals (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  participant_id INT NOT NULL,
  stage          ENUM('swim','bike_day1','bike_day2','bike_total','run') NOT NULL,
  total_s        INT DEFAULT NULL,
  rank_stage     SMALLINT DEFAULT NULL,
  rank_gender    SMALLINT DEFAULT NULL,
  avg_pace_s     INT DEFAULT NULL,
  avg_speed_kmh  DECIMAL(5,2) DEFAULT NULL,
  UNIQUE KEY uq_part_stage (participant_id, stage),
  FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS overall_results (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  participant_id INT NOT NULL UNIQUE,
  total_s        INT DEFAULT NULL,
  rank_overall   SMALLINT DEFAULT NULL,
  rank_gender    SMALLINT DEFAULT NULL,
  rank_relay     SMALLINT DEFAULT NULL,
  FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
