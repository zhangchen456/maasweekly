-- JSONB object order is not an application ordering contract. Preserve the
-- historical priceStreams order separately so storage migration retains ds IDs.
ALTER TABLE maas_data.input_versions ADD COLUMN IF NOT EXISTS source_order jsonb;
INSERT INTO maas_data.schema_versions(version) VALUES (2) ON CONFLICT DO NOTHING;
