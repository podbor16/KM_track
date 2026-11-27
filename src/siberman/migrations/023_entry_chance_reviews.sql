CREATE TABLE IF NOT EXISTS siberman_entry_chance_reviews (
  entry_id INT NOT NULL,
  field ENUM('starts_individual','starts_relay') NOT NULL,
  confirmed_value SMALLINT UNSIGNED NOT NULL,
  note VARCHAR(500) NOT NULL,
  confirmed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (entry_id, field),
  CONSTRAINT fk_chance_review_entry FOREIGN KEY (entry_id)
    REFERENCES siberman_entries(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
