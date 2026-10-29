/** Read-only, version-pinned access to published page inputs and archive records. */
import { createHash } from 'node:crypto';
import { Pool, type PoolConfig } from 'pg';
import type { Manifest } from './dataset.js';

const CHAIN = `WITH RECURSIVE chain AS (
 SELECT version,parent_version,0 AS depth FROM maas_data.input_versions WHERE version=$1
 UNION ALL SELECT v.version,v.parent_version,c.depth+1
 FROM maas_data.input_versions v JOIN chain c ON v.version=c.parent_version
)`;
export class SiteDataError extends Error {
  constructor() { super('versioned site data unavailable'); }
}
export interface PageInputs {
  inputVersion: string;
  codeCommit: string;
  projections: ReadonlyMap<string, unknown>;
}
export class SiteDataStore {
  readonly pool: Pool;
  constructor(config: PoolConfig) {
    this.pool = new Pool({ ...config, max: 2, connectionTimeoutMillis: 3000,
      idleTimeoutMillis: 30000, statement_timeout: 5000,
      options: '-c default_transaction_read_only=on' });
    this.pool.on('error', () => { /* idle errors are retried on the next request; never print DSNs */ });
  }
  private async query<T extends Record<string, unknown>>(sql: string, args: unknown[]) {
    try { return await this.pool.query<T>(sql, args); }
    catch { throw new SiteDataError(); }
  }
  async prepare(manifest: Manifest): Promise<PageInputs> {
    if(!manifest.site||manifest.site.formatVersion!==1)throw new SiteDataError();
    const candidate = await this.query<{input_version:string;code_commit:string}>(
      `SELECT input_version,code_commit FROM maas_data.data_candidates
       WHERE dataset_version=$1 AND files=$2::jsonb AND page_format_version=1
       AND input_version=$3 AND code_commit=$4`, [manifest.datasetVersion, JSON.stringify(manifest.files),
         manifest.site.inputVersion,manifest.site.codeCommit]);
    const row = candidate.rows[0];
    if (!row || !/^in_[0-9a-f]{64}$/.test(row.input_version)) throw new SiteDataError();
    const budget = await this.query<{count:string;bytes:string}>(
      `SELECT count(*)::text AS count,coalesce(sum(bytes),0)::text AS bytes
       FROM maas_data.page_projections WHERE input_version=$1 AND code_commit=$2`,
      [row.input_version,row.code_commit]);
    if (Number(budget.rows[0]?.count) > 256 || Number(budget.rows[0]?.bytes) > 128*1024*1024) throw new SiteDataError();
    const values = await this.query<{name:string;payload_json:string;sha256:string;bytes:string}>(
      `SELECT name,payload_json,sha256,bytes::text FROM maas_data.page_projections
       WHERE input_version=$1 AND code_commit=$2 ORDER BY name`, [row.input_version,row.code_commit]);
    const projections = new Map<string,unknown>();
    for (const item of values.rows) {
      if (Buffer.byteLength(item.payload_json) !== Number(item.bytes)
          || createHash('sha256').update(item.payload_json).digest('hex') !== item.sha256) throw new SiteDataError();
      try { projections.set(item.name, JSON.parse(item.payload_json)); }
      catch { throw new SiteDataError(); }
    }
    for (const name of ['daily_changes.json','weekly-digest.json','translations-en.json','record-index.json','price-record-index.json']) {
      if (!projections.has(`site/src/data/${name}`)) throw new SiteDataError();
    }
    return { inputVersion:row.input_version,codeCommit:row.code_commit,projections };
  }
  async document(version: string, logical: string): Promise<unknown | null> {
    if (!/^in_[0-9a-f]{64}$/.test(version) || !/^data\/[a-zA-Z0-9_./-]+$/.test(logical)
        || logical.split('/').includes('..')) throw new SiteDataError();
    const result = await this.query<{payload_json:string|null}>(`${CHAIN}, selected AS (
      SELECT d.sha256 FROM maas_data.input_deltas d JOIN chain c ON c.version=d.input_version
      WHERE d.logical_path=$2 ORDER BY c.depth LIMIT 1
    ) SELECT d.payload_json FROM selected s LEFT JOIN maas_data.documents d ON d.sha256=s.sha256`, [version,logical]);
    const value = result.rows[0]?.payload_json;
    if (value === undefined || value === null) return null;
    try { return JSON.parse(value); } catch { throw new SiteDataError(); }
  }
  async revisions(version: string, id: string, price: boolean): Promise<unknown[]> {
    if (!/^(obs|price)_[0-9a-f]{64}$/.test(id)) throw new SiteDataError();
    const prefix = `data/${price?'price-record-revisions':'record-revisions'}/${id}/`;
    const result = await this.query<{payload_json:string}>(`${CHAIN}
      SELECT d.payload_json FROM maas_data.documents d WHERE d.entity_id=$2
      AND d.revision ~ '^[1-9][0-9]*$'
      AND d.sha256=(SELECT x.sha256 FROM maas_data.input_deltas x JOIN chain c ON c.version=x.input_version
        WHERE x.logical_path=$3||d.revision||'.json' ORDER BY c.depth LIMIT 1)
      ORDER BY d.revision::bigint`, [version,id,prefix]);
    return result.rows.map(row=>JSON.parse(row.payload_json));
  }
  async factsForEvidence(version: string, id: string): Promise<unknown[]> {
    if (!/^ev_[0-9a-f]{64}$/.test(id)) throw new SiteDataError();
    const result = await this.query<{payload_json:string}>(`${CHAIN}
      SELECT d.payload_json FROM maas_data.documents d
      WHERE left(d.entity_id,4)='pfv_' AND (d.payload->>'evidence_id'=$2 OR d.payload IS NULL)
      AND d.sha256=(SELECT x.sha256 FROM maas_data.input_deltas x JOIN chain c ON c.version=x.input_version
        WHERE x.logical_path='data/price-facts/versions/'||d.entity_id||'.json' ORDER BY c.depth LIMIT 1)
      ORDER BY d.entity_id`, [version,id]);
    return result.rows.map(row=>JSON.parse(row.payload_json)).filter(value=>value.evidence_id===id);
  }
  close() { return this.pool.end(); }
}
