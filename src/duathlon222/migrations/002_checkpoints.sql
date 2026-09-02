USE duathlon_222;

-- Круги/КТ внутри каждого этапа — нужны для «последней пройденной отметки»
-- и прогноза финиша этапа (экстраполяция по средней скорости уже
-- пройденных кругов). participants.run1_s/bike_s/run2_s хранят только
-- ФИНИШ этапа целиком — этой таблицы для них было достаточно, а для
-- живого прогресса ВНУТРИ незавершённого этапа нужны промежуточные точки.
CREATE TABLE IF NOT EXISTS checkpoints (
  id             BIGINT AUTO_INCREMENT PRIMARY KEY,
  participant_id INT NOT NULL,
  stage          ENUM('run1','bike','run2') NOT NULL,
  lap_number     INT NOT NULL,
  cumulative_s   INT NOT NULL,  -- от общего массового старта гонки (как run1_s/bike_s/run2_s)
  UNIQUE KEY uq_participant_stage_lap (participant_id, stage, lap_number),
  FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
