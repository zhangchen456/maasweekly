import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {Dataset,DatasetHolder} from '../dataset.js';
import {SiteRuntime} from '../site-runtime.js';
import {capturePage,type AstroHandler} from '../site-http.js';
import {ReleaseFixture} from './fixture.js';
const ds=(n:number)=>'ds_'+String(n).repeat(64);
const input=(n:number)=>'in_'+String(n).repeat(64);
const code='a'.repeat(40);
function fixture(){const root=mkdtempSync(path.join(tmpdir(),'site-runtime-'));return {root,fx:new ReleaseFixture(root)};}
function bind(root:string,n:number){const file=path.join(root,'manifest.json');const m=JSON.parse(readFileSync(file,'utf8'));m.site={inputVersion:input(n),codeCommit:code,formatVersion:1};writeFileSync(path.join(root,'publication.json'),JSON.stringify(m));}
function runtime(){return new SiteRuntime({
  prepare:async manifest=>({inputVersion:manifest.site!.inputVersion,codeCommit:code,projections:new Map([['name',manifest.site!.inputVersion]])}),
  document:async()=>null,revisions:async()=>[],factsForEvidence:async()=>[],
});}
test('page preparation failure preserves the last complete publication',async()=>{
 const {root,fx}=fixture();let reject=false;const rt=runtime();
 const holder=new DatasetHolder(root,{publicationFile:'publication.json',prepare:async d=>{if(reject)throw new Error('page inputs rejected');await rt.prepare(d);}});
 try{fx.writeRelease(ds(1),{changes:[{id:'obs_'+'a'.repeat(64),observationDate:'2026-09-10'}]});bind(root,1);assert.equal(await holder.reloadAsync(),'changed',holder.lastReloadError??'');const first=holder.current!;
  fx.writeRelease(ds(2),{changes:[{id:'obs_'+'b'.repeat(64),observationDate:'2026-09-11'}]});bind(root,2);reject=true;assert.equal(await holder.reloadAsync(),'failed');assert.equal(holder.current,first);
  assert.equal(rt.run(holder.current!,()=>rt.bridge.json('name')),input(1));
 }finally{holder.close();rmSync(root,{recursive:true,force:true});}
});
test('page-only publication changes reload and concurrent requests stay pinned',async()=>{
 const {root,fx}=fixture(),rt=runtime();const holder=new DatasetHolder(root,{publicationFile:'publication.json',prepare:d=>rt.prepare(d)});
 try{fx.writeRelease(ds(1),{changes:[{id:'obs_'+'a'.repeat(64),observationDate:'2026-09-10'}]});bind(root,1);assert.equal(await holder.reloadAsync(),'changed',holder.lastReloadError??'');const first=holder.current!;
  let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
  const old=rt.run(first,async()=>{await gate;return rt.bridge.json('name');});
  bind(root,2);assert.equal(await holder.reloadAsync(),'changed',holder.lastReloadError??'');assert.equal(holder.current!.version,first.version);
  assert.notEqual(holder.current,first);assert.equal(rt.run(holder.current!,()=>rt.bridge.json('name')),input(2));
  release();assert.equal(await old,input(1));assert.throws(()=>rt.bridge.release());
 }finally{holder.close();rmSync(root,{recursive:true,force:true});}
});
test('manifest changes during page preparation cannot activate stale page inputs',async()=>{
 const {root,fx}=fixture();let move=false;
 const holder=new DatasetHolder(root,{publicationFile:'publication.json',prepare:async()=>{if(move)bind(root,3);}});
 try{fx.writeRelease(ds(1),{changes:[{id:'obs_'+'a'.repeat(64),observationDate:'2026-09-10'}]});bind(root,1);assert.equal(await holder.reloadAsync(),'changed',holder.lastReloadError??'');const first=holder.current;
  bind(root,2);move=true;assert.equal(await holder.reloadAsync(),'superseded');assert.equal(holder.current,first);
 }finally{holder.close();rmSync(root,{recursive:true,force:true});}
});
test('capture never forwards credentials and only trusted internal render receives locals',async()=>{
 const handler:AstroHandler=async(req,res,_next,locals)=>{
   assert.equal(req.headers.host,'localhost');assert.equal(req.headers.cookie,undefined);
   res.writeHead(200,{'Content-Type':'text/html'});res.end(locals?.internalWeekly?'PRIVATE':'PUBLIC');
 };
 assert.equal((await capturePage(handler,'/weekly/2026-10-01/','http://localhost')).body.toString(),'PUBLIC');
 assert.equal((await capturePage(handler,'/_internal/weekly-body/2026-10-01/','http://localhost',true)).body.toString(),'PRIVATE');
});
test('oversized page output fails instead of returning partial or cached HTML',async()=>{
 const handler:AstroHandler=async(_req,res)=>{res.writeHead(200);res.end(Buffer.alloc(8*1024*1024+1));};
 await assert.rejects(capturePage(handler,'/','http://localhost'));
});
