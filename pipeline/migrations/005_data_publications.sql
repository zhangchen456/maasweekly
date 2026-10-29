CREATE TABLE IF NOT EXISTS maas_data.data_publications (
  root text NOT NULL,
  manifest_sha256 text NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
  previous_manifest_sha256 text NOT NULL,
  dataset_version text NOT NULL,
  input_version text NOT NULL,
  code_commit text NOT NULL,
  state text NOT NULL CHECK(state IN ('prepared','published','aborted')),
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  PRIMARY KEY(root,manifest_sha256),
  FOREIGN KEY(dataset_version,input_version,code_commit)
    REFERENCES maas_data.data_candidates(dataset_version,input_version,code_commit)
);
CREATE UNIQUE INDEX IF NOT EXISTS publication_one_prepared ON maas_data.data_publications(root) WHERE state='prepared';
INSERT INTO maas_data.schema_versions(version) VALUES (5) ON CONFLICT DO NOTHING;
