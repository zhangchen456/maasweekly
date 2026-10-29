CREATE TABLE IF NOT EXISTS maas_data.input_raw_manifests (
 input_version text PRIMARY KEY REFERENCES maas_data.input_versions(version),
 manifest jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO maas_data.schema_versions(version) VALUES (6) ON CONFLICT DO NOTHING;
