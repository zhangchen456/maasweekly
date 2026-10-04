import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { randomUUID } from 'node:crypto';
const { AccountStore } = await import(pathToFileURL('/srv/maasweekly/current/agent-api/dist/account-store.js'));
const store = new AccountStore(process.env.MAAS_ACCOUNT_DB);
const users = [];
const pause = () => new Promise(r => setTimeout(r, 2300));
const origin = 'https://daily.maas.click';
const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf0QAAAAASUVORK5CYII=';
let checks = 0;
const check = (actual, expected) => { assert.equal(actual, expected); checks++; };
try {
  for (let i=0;i<2;i++) {
    const email = `release-feedback-${randomUUID()}@example.test`;
    users.push(store.verify(email, store.issueCode(email)));
  }
  const cookie = u => `__Host-maas_session=${u.session}`;
  const payload = {title:'部署验收合成反馈',description:'验证截图上传、用户隔离和私有读取，验收结束后自动删除。',page:'/feedback/',images:[{mime:'image/png',data:png}],padding:'x'.repeat(9000)};
  await pause();
  const submitted = await fetch(origin+'/api/account/feedback',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json',Cookie:cookie(users[0])},body:JSON.stringify(payload)});
  check(submitted.status,201);
  const {id}=await submitted.json();
  await pause();
  const image=await fetch(`${origin}/api/account/feedback/${id}/image/0`,{headers:{Cookie:cookie(users[0])}});
  check(image.status,200);check(image.headers.get('content-type'),'image/png');check(image.headers.get('cache-control').split(',').map(x=>x.trim()).includes('no-store'),true);check(image.headers.get('x-content-type-options').split(',').map(x=>x.trim()).includes('nosniff'),true);
  check(Buffer.from(await image.arrayBuffer()).toString('base64'),png);
  await pause();check((await fetch(`${origin}/api/account/feedback/${id}/image/0`,{headers:{Cookie:cookie(users[1])}})).status,404);
  await pause();check((await fetch(`${origin}/api/account/feedback/${id}/image/0`)).status,401);
  await pause();
  const other=await fetch(origin+'/api/account/feedback',{headers:{Cookie:cookie(users[1])}});
  check(other.status,200);check((await other.json()).items.length,0);
  console.log(JSON.stringify({checks,passed:true,mailSent:0}));
} finally {
  store.transaction(()=>{
    for(const {user} of users){
      store.db.prepare('DELETE FROM feedback WHERE userId=?').run(user.id);
      for(const table of ['sessions','account_profiles','account_state','passwords','watches']) store.db.prepare(`DELETE FROM ${table} WHERE userId=?`).run(user.id);
      store.db.prepare('DELETE FROM users WHERE id=?').run(user.id);
      store.db.prepare('DELETE FROM organizations WHERE id=?').run(user.organizationId);
      for(const table of ['send_limits','challenges','password_attempts']) store.db.prepare(`DELETE FROM ${table} WHERE email=?`).run(user.email);
    }
  });
  store.close();
  console.log('Temporary acceptance accounts, feedback and screenshots removed.');
}
