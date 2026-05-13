-- Performance indexes: prefix search on clients.surname + segments by result_id
-- Apply manually before production deploy

CREATE INDEX idx_clients_surname ON clients(surname(50));

CREATE INDEX idx_result_segments_result_id ON result_segments(result_id);
