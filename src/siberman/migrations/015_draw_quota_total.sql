-- Жеребьёвка: квоты раундов 2–3 — общие на оба пола, вместе с wild card (правила 2028 от организаторов,
-- 2026-10-19): повторных не меньше quota_repeat, новичков — quota_novice. Квоты по полу больше не нужны.
ALTER TABLE draw_config
  ADD COLUMN quota_repeat SMALLINT DEFAULT NULL AFTER capacity_relay,
  ADD COLUMN quota_novice SMALLINT DEFAULT NULL AFTER quota_repeat,
  DROP COLUMN quota_repeat_men,
  DROP COLUMN quota_repeat_women,
  DROP COLUMN quota_novice_men,
  DROP COLUMN quota_novice_women;
