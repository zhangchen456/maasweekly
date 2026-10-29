CREATE TABLE IF NOT EXISTS maas_data.page_projections (
  input_version text NOT NULL REFERENCES maas_data.input_versions(version),
  code_commit text NOT NULL CHECK (code_commit ~ '^[0-9a-f]{40}$'),
  name text NOT NULL,
  payload_json text NOT NULL,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  bytes bigint NOT NULL CHECK (bytes >= 0),
  PRIMARY KEY (input_version,code_commit,name)
);
ALTER TABLE maas_data.data_candidates ADD COLUMN IF NOT EXISTS page_format_version integer;
CREATE INDEX IF NOT EXISTS documents_fact_evidence
  ON maas_data.documents ((payload->>'evidence_id')) WHERE left(entity_id,4)='pfv_';
INSERT INTO maas_data.schema_versions(version) VALUES (4) ON CONFLICT DO NOTHING;
