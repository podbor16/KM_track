-- Migration: add missing indexes
-- Safe to re-run: duplicates are caught and skipped by deploy script
-- 2026-05-20

-- leads: DBeaver filter by event_name + event_year does full scan (12K rows)
CREATE INDEX idx_leads_event_name_year ON leads(event_name(50), event_year);

-- results: find_result_by_client_id() fallback uses start_number
CREATE INDEX idx_results_start_number ON results(start_number);

-- result_segments: get_event_segment_rankings() filters by event_id AND segment_code
-- idx_rs_event_id and idx_segment_code exist separately but composite is more efficient
CREATE INDEX idx_result_segments_event_segment ON result_segments(event_id, segment_code);
