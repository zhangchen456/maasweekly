/** Durable local relay state. No browser can ingest receipts or execute a job. */
import {createHash} from 'node:crypto';
import type {AdminStore} from './admin-store.js';
import type {AdminMonitor} from './admin-monitor.js';

export function initializePipelineMonitoring(admin: AdminStore) {
  admin.db.exec(`CREATE TABLE IF NOT EXISTS monitor_run_context(
    runId TEXT PRIMARY KEY REFERENCES monitor_runs(id),codeCommit TEXT NOT NULL,
    datasetVersion TEXT,elapsedMs INTEGER NOT NULL,payloadHash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS monitor_pipeline_reports(name TEXT PRIMARY KEY,digest TEXT NOT NULL,receivedAt INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS monitor_pipeline_health(id INTEGER PRIMARY KEY CHECK(id=1),checkedAt INTEGER NOT NULL,payload TEXT NOT NULL);`);
}
const hash = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const exact = (v: any, keys: string[]) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).length === keys.length && keys.every(k => k in v);
export function ingestPipelineReport(monitor: AdminMonitor, name: string, value: any) {
  if (!/^report_[a-f0-9]{64}\.json$/.test(name)
      || !exact(value, ['schemaVersion','batch','contexts']) || value.schemaVersion !== 'pipeline-report-v1'
      || !Array.isArray(value.contexts) || value.contexts.length > 500) throw Error('invalid pipeline report');
  const admin = monitor.admin, digest = hash(value);
  return admin.accounts.transaction(() => {
    const old = admin.db.prepare('SELECT digest FROM monitor_pipeline_reports WHERE name=?').get(name);
    if (old) { if (old.digest !== digest) throw Error('pipeline receipt conflict'); return {duplicate:true}; }
    monitor.ingest(value.batch, true);
    const runIds = new Set((value.batch.runs as {id:string}[]).map(r => r.id));
    const seen = new Set<string>();
    for (const item of value.contexts) {
      if (!exact(item, ['runId','codeCommit','datasetVersion','elapsedMs']) || !runIds.has(item.runId)
          || seen.has(item.runId) || !/^[a-f0-9]{40}$/.test(item.codeCommit)
          || !(item.datasetVersion === null || /^ds_[a-f0-9]{64}$/.test(item.datasetVersion))
          || !Number.isSafeInteger(item.elapsedMs) || item.elapsedMs < 0) throw Error('invalid pipeline context');
      seen.add(item.runId);
      const digest = hash(item), prior = admin.db.prepare('SELECT payloadHash FROM monitor_run_context WHERE runId=?').get(item.runId);
      if (prior && prior.payloadHash !== digest) throw Error('pipeline context conflict');
      admin.db.prepare('INSERT OR IGNORE INTO monitor_run_context VALUES(?,?,?,?,?)').run(item.runId,item.codeCommit,item.datasetVersion,item.elapsedMs,digest);
    }
    admin.db.prepare('INSERT INTO monitor_pipeline_reports VALUES(?,?,?)').run(name,digest,admin.accounts.now());
    return {duplicate:false};
  });
}

export interface PipelineSample {
  alerts: string[];
  currentJob: {id:string;state:string;stage:string;startedAt:number;updatedAt:number;codeCommit:string}|null;
  runtime: {processCode:string;publication:unknown;dataThrough:string|null;latestWeeklyId:string|null}|null;
  disk: {freeBytes:number;totalBytes:number;freeInodes:number}|null;
  importedReports:number;
}
export function savePipelineSample(admin: AdminStore, sample: PipelineSample) {
  admin.db.prepare('INSERT INTO monitor_pipeline_health VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET checkedAt=excluded.checkedAt,payload=excluded.payload')
    .run(admin.accounts.now(),JSON.stringify(sample));
}
export function pipelineHealth(admin: AdminStore) {
  const row = admin.db.prepare('SELECT checkedAt,payload FROM monitor_pipeline_health WHERE id=1').get();
  const now = admin.accounts.now(), stale = !row || now-Number(row.checkedAt)>15*60000;
  const sample = row ? JSON.parse(String(row.payload)) as PipelineSample : null;
  const alerts = [...(sample?.alerts ?? []), ...(stale ? ['monitor_collector_stale'] : [])];
  const last = admin.db.prepare("SELECT max(finishedAt) AS at FROM monitor_runs WHERE kind='data-pipeline'").get();
  return {checkedAt:row?.checkedAt??null,lastRunAt:last?.at??null,stale,
    status:alerts.length?'abnormal':'normal',alerts,...(sample?{currentJob:sample.currentJob,runtime:sample.runtime,disk:sample.disk}:{}),
    summary:stale?'监控同步已超过15分钟未更新或尚未接入':alerts.length?'监控已接入，存在需要核查的状态':'监控同步正常'};
}
