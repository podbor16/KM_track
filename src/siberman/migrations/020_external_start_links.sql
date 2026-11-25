USE siberman;

CREATE TABLE IF NOT EXISTS siberman_external_start_links (
  person_id INT NOT NULL,
  source ENUM('duathlon_222', 'race_24h') NOT NULL,
  event_id INT NOT NULL,
  result_id INT NOT NULL,
  confirmed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (person_id, source, event_id, result_id),
  CONSTRAINT fk_external_start_person FOREIGN KEY (person_id)
    REFERENCES siberman_persons(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
