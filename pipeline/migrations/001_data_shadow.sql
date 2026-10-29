-- Additive shadow schema. Does not publish data or modify account tables.
CREATE SCHEMA IF NOT EXISTS maas_data;
CREATE TABLE IF NOT EXISTS maas_data.schema_versions (
  version integer PRIMARY KEY, installed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS maas_data.input_versions (
  version text PRIMARY KEY CHECK (version ~ '^in_[0-9a-f]{64}$'),
  parent_version text REFERENCES maas_data.input_versions(version),
  source_commit text NOT NULL CHECK (source_commit ~ '^[0-9a-f]{40}$'),
  origin_run_id text NOT NULL,
  file_count bigint NOT NULL CHECK (file_count >= 0),
  byte_count bigint NOT NULL CHECK (byte_count >= 0),
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Store immutable bytes once, plus queryable structured content. Raw web
-- responses remain in the filesystem store, not PostgreSQL large objects.
CREATE TABLE IF NOT EXISTS maas_data.documents (
  sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  bytes bigint NOT NULL CHECK (bytes >= 0),
  payload jsonb,
  entity_id text,
  revision text
);
CREATE INDEX IF NOT EXISTS documents_entity ON maas_data.documents(entity_id, revision);
-- JSONB rejects escaped NUL and lone surrogate characters found in some
-- historical scraped text. Preserve these exceptional JSON documents losslessly.
ALTER TABLE maas_data.documents ADD COLUMN IF NOT EXISTS payload_json text;
-- A baseline contains all paths; descendants contain only changed paths and
-- explicit tombstones. Parent history is immutable and never auto-pruned.
CREATE TABLE IF NOT EXISTS maas_data.input_deltas (
  input_version text NOT NULL REFERENCES maas_data.input_versions(version),
  logical_path text NOT NULL,
  physical_path text,
  sha256 text REFERENCES maas_data.documents(sha256),
  PRIMARY KEY (input_version, logical_path),
  CHECK ((sha256 IS NULL) = (physical_path IS NULL))
);
INSERT INTO maas_data.schema_versions(version) VALUES (1) ON CONFLICT DO NOTHING;
