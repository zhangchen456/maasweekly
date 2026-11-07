-- Rare lossless-text records must not force a scan of all historical JSONB facts.
CREATE INDEX IF NOT EXISTS documents_fact_fallback
  ON maas_data.documents (entity_id) WHERE left(entity_id,4)='pfv_' AND payload IS NULL;
INSERT INTO maas_data.schema_versions(version) VALUES (8) ON CONFLICT DO NOTHING;
