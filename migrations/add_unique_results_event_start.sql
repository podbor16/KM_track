-- Migration: UNIQUE KEY (event_id, start_number) on results
-- Prevents duplicate results rows for the same bib within one event
-- (protects against e.g. a repeated --init run inserting twice).
--
-- Blocked by one legacy row: Весна 2025 (event_id=71), №283, id=207,
-- "Подборский Матвей" — same identity has multiple Tilda-webhook test
-- leads (promo codes 99TEST/BIKECORE99, fractional amounts) across many
-- events/years, confirming this specific results row is leftover test
-- data from developing the results loader, not a real participant.
-- Removed before adding the constraint.
-- 2026-08-17

DELETE FROM results WHERE id = 207;

ALTER TABLE results ADD UNIQUE KEY uq_results_event_start (event_id, start_number);
