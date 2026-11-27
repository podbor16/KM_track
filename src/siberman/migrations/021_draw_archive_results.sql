CREATE TABLE IF NOT EXISTS siberman_draw_archive_results (
  draw_year SMALLINT NOT NULL,
  source_group VARCHAR(20) NOT NULL,
  position SMALLINT NOT NULL,
  participant_name VARCHAR(200) NOT NULL,
  outcome ENUM('paid','unpaid','no_offer') NOT NULL,
  person_id INT DEFAULT NULL,
  PRIMARY KEY (draw_year, source_group, position),
  KEY ix_archive_results_person (person_id, draw_year),
  CONSTRAINT fk_archive_results_person FOREIGN KEY (person_id)
    REFERENCES siberman_persons(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
