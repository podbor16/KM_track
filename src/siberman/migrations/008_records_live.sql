-- Разделяем НЕИЗМЕННЫЙ исторический baseline (никогда не перезаписывается)
-- от текущего best_s/holder_*/year_set (пересчитывается заново на каждом
-- apply — см. write_best_record()/_recompute_records() в db.py/service.py).
-- Причина: рекорд должен быть виден в LIVE-режиме (как только участник
-- реально финишировал СВОЙ сегмент, не обязательно всю гонку), но должен
-- "откатываться" назад, если этот участник позже получает DNF — без
-- отдельного baseline некуда было бы откатываться (2026-08-05, второй
-- раунд решения по рекордам).
ALTER TABLE siberman_records
  ADD COLUMN baseline_s INT NULL,
  ADD COLUMN baseline_holder_name VARCHAR(255) NULL,
  ADD COLUMN baseline_holder_team VARCHAR(255) NULL,
  ADD COLUMN baseline_year_set SMALLINT NULL;

-- Текущие best_s/holder_*/year_set на момент миграции — это ровно
-- исходные 13 значений из 006_records.sql (живых полных финишей в
-- текущем тестовом прогоне ещё не было) — фиксируем их как baseline.
UPDATE siberman_records SET
  baseline_s = best_s,
  baseline_holder_name = holder_name,
  baseline_holder_team = holder_team,
  baseline_year_set = year_set;
