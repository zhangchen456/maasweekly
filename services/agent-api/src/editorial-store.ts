import { z } from 'zod';
import { AccountError, hash } from './account-store.js';
import type { AdminStore } from './admin-store.js';
import { contentSchema } from './pro-store.js';
export const packageSchema=z.object({contents:z.array(contentSchema).min(1).max(12)}).strict().refine(p=>p.contents.filter(c=>c.kind==='briefing').length===1 && new Set(p.contents.map(c=>c.id)).size===p.contents.length,'需要一份统一周报且ID唯一');
export type ContentPackage=z.infer<typeof packageSchema>;
export const bad=(message:string,code='invalid_editorial',status=400)=>new AccountError(status,code,message);
export function monday(value:unknown) {
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))throw bad('请输入真实周一日期');
  const day=new Date(value+'T00:00:00Z');
  if(!Number.isFinite(day.getTime())||day.toISOString().slice(0,10)!==value||day.getUTCDay()!==1)throw bad('统计结束日期必须是真实周一');
  const to=value+'T00:00:00+08:00',from=new Date(day.getTime()-7*86400000).toISOString().slice(0,10)+'T00:00:00+08:00';
  return {from,to};
}
export interface FrozenInput {id:string;revision:number;url:string;observedAt:string;hash:string;providerId:string|null;modelId:string|null;familyId:string|null;title:string;excerpt:string;price:Record<string,unknown>|null;status:string}
export interface Issue {id:string;periodEnd:string;windowFrom:string;windowTo:string;datasetVersion:string|null;coverage:'normal'|'partial'|'failed';coverageNote:string;dataThrough:string|null;selection:string;state:string;currentRevision:number;version:number;inputHash:string|null;budget:number;config:string;createdBy:string;createdAt:number;coverageInfo:string}
export interface Revision {issueId:string;revision:number;payload:string;inputHash:string;outputHash:string;createdBy:string;createdAt:number;runId:string|null;checks:string}
export class EditorialStore {
  readonly db;
  constructor(readonly admin:AdminStore) {
    this.db=admin.db;
    admin.accounts.transaction(()=>{
      if(this.db.prepare('SELECT 1 FROM admin_schema_migrations WHERE version=3').get())return;
      this.db.exec(`CREATE TABLE editorial_issues(id TEXT PRIMARY KEY,periodEnd TEXT UNIQUE NOT NULL,windowFrom TEXT NOT NULL,windowTo TEXT NOT NULL,datasetVersion TEXT,coverage TEXT NOT NULL,coverageNote TEXT NOT NULL,dataThrough TEXT,selection TEXT NOT NULL,state TEXT NOT NULL,currentRevision INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 0,inputHash TEXT,budget REAL NOT NULL,config TEXT NOT NULL,createdBy TEXT NOT NULL,createdAt INTEGER NOT NULL,coverageInfo TEXT NOT NULL DEFAULT '{}');
      CREATE TABLE editorial_inputs(issueId TEXT NOT NULL REFERENCES editorial_issues(id),snapshotId TEXT NOT NULL,position INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(issueId,snapshotId,position));
      CREATE TABLE editorial_revisions(issueId TEXT NOT NULL REFERENCES editorial_issues(id),revision INTEGER NOT NULL,payload TEXT NOT NULL,inputHash TEXT NOT NULL,outputHash TEXT NOT NULL,createdBy TEXT NOT NULL,createdAt INTEGER NOT NULL,runId TEXT,checks TEXT NOT NULL,PRIMARY KEY(issueId,revision));
      CREATE TABLE editorial_reviews(id TEXT PRIMARY KEY,issueId TEXT NOT NULL,revision INTEGER NOT NULL,outputHash TEXT NOT NULL,checklist TEXT NOT NULL,decision TEXT NOT NULL,note TEXT NOT NULL,reviewerId TEXT NOT NULL,createdAt INTEGER NOT NULL);
      CREATE TABLE editorial_runs(id TEXT PRIMARY KEY,issueId TEXT NOT NULL REFERENCES editorial_issues(id),stage TEXT NOT NULL,state TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,leaseOwner TEXT,leaseUntil INTEGER NOT NULL DEFAULT 0,fencingVersion INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 0,inputHash TEXT NOT NULL,config TEXT NOT NULL,budget REAL NOT NULL,reserved REAL NOT NULL DEFAULT 0,estimatedCost REAL,actualCost REAL,usage TEXT NOT NULL DEFAULT '[]',errorCode TEXT,result TEXT,createdAt INTEGER NOT NULL,startedAt INTEGER,finishedAt INTEGER,availableAt INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL);
      CREATE UNIQUE INDEX editorial_runs_active ON editorial_runs(issueId,stage,inputHash) WHERE state IN ('queued','running','needs_review');
      CREATE TABLE editorial_publications(id TEXT PRIMARY KEY,issueId TEXT NOT NULL,revision INTEGER NOT NULL,contentRefs TEXT NOT NULL,publishedAt INTEGER NOT NULL,actorId TEXT NOT NULL,compositionState TEXT NOT NULL DEFAULT 'pending',queueMail INTEGER,summary TEXT NOT NULL DEFAULT '{}',UNIQUE(issueId,revision));`);
      this.db.prepare('INSERT INTO admin_schema_migrations VALUES(3,?)').run(this.now);
    });
  }
  get now(){return this.admin.accounts.now();}
  issue(id:string):Issue {const row=this.db.prepare('SELECT * FROM editorial_issues WHERE id=?').get(id);if(!row)throw bad('期次不存在','not_found',404);return row as unknown as Issue;}
  inputs(id:string):FrozenInput[]{const i=this.issue(id);return this.db.prepare('SELECT payload FROM editorial_inputs WHERE issueId=? AND snapshotId=? ORDER BY position').all(id,i.inputHash??'').map(r=>JSON.parse(String(r.payload)));}
  revision(id:string,n?:number):Revision {const row=this.db.prepare('SELECT * FROM editorial_revisions WHERE issueId=? AND revision=?').get(id,n??this.issue(id).currentRevision);if(!row)throw bad('尚无稿件','not_found',404);return row as unknown as Revision;}
  bump(id:string,state='draft'){this.db.prepare('UPDATE editorial_issues SET state=?,version=version+1 WHERE id=?').run(state,id);}
  run(id:string){const row=this.db.prepare('SELECT * FROM editorial_runs WHERE id=?').get(id);if(!row)throw bad('任务不存在','not_found',404);return row;}
}
export { hash };
