CREATE TABLE IF NOT EXISTS maas_data.writer_heads (
 name text PRIMARY KEY,
 input_version text NOT NULL REFERENCES maas_data.input_versions(version),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS maas_data.writer_run_logs (
 logical_path text PRIMARY KEY,
 sha256 text NOT NULL,
 payload_json text NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO maas_data.schema_versions(version) VALUES (7) ON CONFLICT DO NOTHING;
