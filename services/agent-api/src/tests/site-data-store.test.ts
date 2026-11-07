/** Real PostgreSQL regression for version-pinned evidence reads. Dedicated fixture DB only. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,readdirSync} from 'node:fs';
import {Pool,type PoolConfig} from 'pg';
import {SiteDataStore} from '../site-data-store.js';
const dsn=process.env.MAAS_SHADOW_TEST_DSN;
function config():PoolConfig {
 if(dsn?.startsWith('postgres'))return {connectionString:dsn};
 const fields=Object.fromEntries((dsn??'').trim().split(/\s+/).map(x=>x.split('=')));
 return {host:fields.host,port:fields.port?Number(fields.port):undefined,user:fields.user,password:fields.password,database:fields.dbname};
}
test('evidence lookup preserves inheritance, replacements, tombstones and lossless JSON fallback', {skip:!dsn},async()=>{
 const cfg=config(),db=new Pool(cfg);let store:SiteDataStore|undefined;
 try{
  assert.equal((await db.query('SELECT current_database() AS name')).rows[0].name,'maas_shadow_test','dedicated fixture database required');
  await db.query('DROP SCHEMA IF EXISTS maas_data CASCADE');
  const dir=new URL('../../../../pipeline/migrations/',import.meta.url);
  for(const file of readdirSync(dir).filter(f=>f.endsWith('.sql')).sort())await db.query(readFileSync(new URL(file,dir),'utf8'));
  const versions=[1,2,3].map(n=>'in_'+String(n).repeat(64)),ev='ev_'+'a'.repeat(64),other='ev_'+'b'.repeat(64);
  for(let i=0;i<versions.length;i++)await db.query('INSERT INTO maas_data.input_versions(version,parent_version,source_commit,origin_run_id,file_count,byte_count) VALUES($1,$2,$3,\'fixture\',0,0)',[versions[i],versions[i-1]??null,'a'.repeat(40)]);
  const id=(n:number)=>'pfv_'+String(n).repeat(64);
  const put=async(version:string,n:number,evidence:string,text='safe',fallback=false)=>{
   const payload={version_id:id(n),evidence_id:evidence,text},raw=JSON.stringify(payload),sha=createHash('sha256').update(raw).digest('hex');
   await db.query('INSERT INTO maas_data.documents(sha256,bytes,payload,entity_id,payload_json) VALUES($1,$2,$3,$4,$5)',[sha,Buffer.byteLength(raw),fallback?null:raw,id(n),raw]);
   await db.query('INSERT INTO maas_data.input_deltas(input_version,logical_path,physical_path,sha256) VALUES($1,$2,$2,$3)',[version,'data/price-facts/versions/'+id(n)+'.json',sha]);
   return payload;
  };
  const inherited=await put(versions[0]!,1,ev),changed=await put(versions[0]!,2,ev),deleted=await put(versions[0]!,3,ev);
  const exceptional=await put(versions[0]!,4,ev,'NUL\u0000 and surrogate\ud800',true);
  await put(versions[0]!,5,other,'unrelated\u0000',true);
  await put(versions[1]!,2,other,'replacement changes evidence');
  await db.query('INSERT INTO maas_data.input_deltas(input_version,logical_path) VALUES($1,$2)',[versions[1],'data/price-facts/versions/'+id(3)+'.json']);
  const added=await put(versions[2]!,6,ev);
  await db.query('INSERT INTO maas_data.documents(sha256,bytes,payload,entity_id,payload_json) VALUES($1,1,NULL,\'obs_unrelated\',\'{}\')',['f'.repeat(64)]);
  store=new SiteDataStore(cfg);
  assert.deepEqual(await store.factsForEvidence(versions[0]!,ev),[inherited,changed,deleted,exceptional]);
  assert.deepEqual(await store.factsForEvidence(versions[1]!,ev),[inherited,exceptional]);
  assert.deepEqual(await store.factsForEvidence(versions[2]!,ev),[inherited,exceptional,added]);
  assert.deepEqual(await store.factsForEvidence(versions[2]!,'ev_'+'c'.repeat(64)),[]);
  assert.deepEqual(await store.factsForEvidence('in_'+'9'.repeat(64),ev),[]);
 }finally{await store?.close();await db.end();}
});
