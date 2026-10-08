import {AccountStore} from '/srv/maasweekly/current/agent-api/dist/account-store.js';
import {AdminStore} from '/srv/maasweekly/current/agent-api/dist/admin-store.js';
import {ProStore} from '/srv/maasweekly/current/agent-api/dist/pro-store.js';
import {spawnSync} from 'node:child_process';
import {writeFileSync,readFileSync,unlinkSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
const dir='/srv/maasweekly/shared/state/admin-release-20261008',fixture='/srv/maasweekly/shared/state/accounts/admin-acceptance-20261008.json',a=new AccountStore(process.env.MAAS_ACCOUNT_DB),s=new AdminStore(a),pro=new ProStore(a),mode=process.argv[2];
try{
 if(mode==='init'){
  const target=a.db.prepare('SELECT id FROM users WHERE email=?').get('zhangchen3508@gmail.com');if(!target)throw Error('authorized user missing');
  const c=spawnSync(process.execPath,['/srv/maasweekly/current/agent-api/dist/admin-cli.js','grant','--user-id',target.id,'--actor','deployment-20261008','--reason','user authorized administrator email in deployment chat'],{env:process.env,encoding:'utf8'});if(c.status!==0)throw Error('admin CLI grant failed');
  const rows=[];for(const role of ['ordinary','admin']){
   const email='acceptance-admin-20261008-'+role+'@example.test';if(a.db.prepare('SELECT 1 FROM users WHERE email=?').get(email))throw Error('synthetic already exists');
   const u=a.verify(email,a.issueCode(email));a.db.prepare('UPDATE sessions SET expires=? WHERE userId=?').run(Date.now()+30*60*1000,u.user.id);rows.push({role,email,userId:u.user.id,organizationId:u.user.organizationId,session:u.session});if(role==='admin')s.setMember(u.user.id,true,'deployment-20261008','temporary synthetic production acceptance');else pro.grant(u.user.id,Date.now()-1000,Date.now()+3600000,'deployment-20261008','synthetic Plus access test');
  }
  writeFileSync(fixture,JSON.stringify(rows),{mode:0o600});console.log(JSON.stringify({authorizedAdmin:true,syntheticAccounts:2,migrations:a.db.prepare('SELECT version FROM admin_schema_migrations ORDER BY version').all()}));
 }else if(mode==='revoke'){
  const rows=JSON.parse(readFileSync(fixture));s.setMember(rows.find(r=>r.role==='admin').userId,false,'deployment-20261008','test immediate administrator revocation');console.log('synthetic admin revoked');
 }else if(mode==='cleanup'){
  const rows=JSON.parse(readFileSync(fixture));const taskIds=JSON.parse(readFileSync(dir+'/synthetic-task-ids.json'));a.transaction(()=>{
   if(taskIds.problemId){const item=a.db.prepare('SELECT title FROM problems WHERE id=?').get(taskIds.problemId);if(!item?.title.startsWith('acceptance-admin-20261008 '))throw Error('problem scope mismatch');for(const t of ['diagnostic_runs','problem_checks','problem_refs','problem_links'])a.db.prepare('DELETE FROM '+t+' WHERE problemId=?').run(taskIds.problemId);a.db.prepare('DELETE FROM problems WHERE id=?').run(taskIds.problemId);}
   if(taskIds.issueId){const item=a.db.prepare('SELECT selection FROM editorial_issues WHERE id=?').get(taskIds.issueId);if(!item?.selection.startsWith('acceptance-admin-20261008 '))throw Error('issue scope mismatch');if(a.db.prepare('SELECT 1 FROM editorial_publications WHERE issueId=?').get(taskIds.issueId))throw Error('unexpected publication');for(const t of ['editorial_runs','editorial_reviews','editorial_revisions','editorial_inputs'])a.db.prepare('DELETE FROM '+t+' WHERE issueId=?').run(taskIds.issueId);a.db.prepare('DELETE FROM editorial_issues WHERE id=?').run(taskIds.issueId);}

   for(const r of rows){
    const actual=a.db.prepare('SELECT email FROM users WHERE id=?').get(r.userId);if(actual?.email!==r.email||!r.email.startsWith('acceptance-admin-20261008-'))throw Error('cleanup scope mismatch');
    for(const t of ['admin_members','admin_user_versions','account_registrations','account_profiles','account_state','watches','pro_settings','pro_beta_access','pro_entitlements','pro_events','pro_tokens','pro_applications','sessions','passwords']){
     if(a.db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(t))a.db.prepare('DELETE FROM '+t+' WHERE userId=?').run(r.userId);
    }
    a.db.prepare('DELETE FROM send_limits WHERE email=?').run(r.email);a.db.prepare('DELETE FROM challenges WHERE email=?').run(r.email);a.db.prepare('DELETE FROM users WHERE id=?').run(r.userId);a.db.prepare('DELETE FROM organizations WHERE id=?').run(r.organizationId);
   }
  });unlinkSync(fixture);console.log(JSON.stringify({syntheticsDeleted:2,authorizedAdminRetained:Boolean(s.member(a.db.prepare('SELECT id FROM users WHERE email=?').get('zhangchen3508@gmail.com').id)),integrity:a.db.prepare('PRAGMA quick_check').get(),foreignKeyViolations:a.db.prepare('PRAGMA foreign_key_check').all().length}));
 }else if(mode==='preservation'){
  const b=new DatabaseSync(dir+'/before.sqlite',{readOnly:true});const checks=[];
  for(const t of ['users','passwords','feedback','pro_content','pro_reports','pro_entitlements']){
   if(!b.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(t))continue;
   const columns=b.prepare('PRAGMA table_info('+t+')').all(),pk=columns.filter(c=>c.pk).sort((l,r)=>l.pk-r.pk).map(c=>c.name);if(!pk.length)continue;let missing=0;
   const query=a.db.prepare('SELECT 1 FROM '+t+' WHERE '+pk.map(c=>c+'=?').join(' AND '));for(const r of b.prepare('SELECT '+pk.join(',')+' FROM '+t).all())if(!query.get(...pk.map(k=>r[k])))missing++;
   checks.push({table:t,missingOriginalKeys:missing});if(missing)throw Error('original rows missing');
  }b.close();console.log(JSON.stringify({preservation:checks}));
 }else throw Error('unknown mode');
}finally{a.close()}
