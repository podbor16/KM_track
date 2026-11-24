USE siberman;

CREATE TABLE IF NOT EXISTS siberman_entry_person_links (
  entry_id INT PRIMARY KEY,
  person_id INT DEFAULT NULL,
  is_new BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT fk_entry_person_entry FOREIGN KEY (entry_id) REFERENCES siberman_entries(id) ON DELETE CASCADE,
  CONSTRAINT fk_entry_person_person FOREIGN KEY (person_id) REFERENCES siberman_persons(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS siberman_draw_archive_links (
  draw_year SMALLINT NOT NULL,
  category ENUM('men','women','relay') NOT NULL,
  position INT NOT NULL,
  person_id INT DEFAULT NULL,
  PRIMARY KEY (draw_year, category, position),
  KEY idx_draw_archive_person (person_id),
  CONSTRAINT fk_draw_archive_person FOREIGN KEY (person_id) REFERENCES siberman_persons(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @has_entry_id := (SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='draw_applicants' AND column_name='entry_id');
SET @draw_identity_ddl := IF(@has_entry_id=0,
    'ALTER TABLE draw_applicants
        ADD COLUMN entry_id INT DEFAULT NULL,
        ADD COLUMN person_id INT DEFAULT NULL,
        ADD UNIQUE KEY uq_draw_entry (draw_year, entry_id),
        ADD UNIQUE KEY uq_draw_identity (draw_year, person_id),
        ADD CONSTRAINT fk_draw_identity_entry FOREIGN KEY (entry_id) REFERENCES siberman_entries(id),
        ADD CONSTRAINT fk_draw_identity_person FOREIGN KEY (person_id) REFERENCES siberman_persons(id) ON DELETE SET NULL,
        DROP INDEX uq_draw_person',
    'DO 0');
PREPARE draw_identity_stmt FROM @draw_identity_ddl;
EXECUTE draw_identity_stmt;
DEALLOCATE PREPARE draw_identity_stmt;

ALTER TABLE siberman_entries_audit
    MODIFY action ENUM('status','comment','identity') NOT NULL;
