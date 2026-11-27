CREATE TABLE IF NOT EXISTS siberman_draw_balance_decisions (
  entry_id INT PRIMARY KEY,
  balance SMALLINT UNSIGNED NOT NULL,
  reason VARCHAR(500) NOT NULL,
  decided_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_draw_balance_entry FOREIGN KEY (entry_id)
    REFERENCES siberman_entries(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
