CREATE TABLE IF NOT EXISTS maas_data.data_candidates (
  dataset_version text NOT NULL CHECK (dataset_version ~ '^ds_[0-9a-f]{64}$'),
  input_version text NOT NULL REFERENCES maas_data.input_versions(version),
  code_commit text NOT NULL CHECK (code_commit ~ '^[0-9a-f]{40}$'),
  data_through date NOT NULL,
  files jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (dataset_version,input_version,code_commit)
);
INSERT INTO maas_data.schema_versions(version) VALUES (3) ON CONFLICT DO NOTHING;
