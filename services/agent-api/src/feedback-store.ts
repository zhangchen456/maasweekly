import { randomUUID } from 'node:crypto';
import { AccountError, type AccountStore } from './account-store.js';
export const IMAGE_LIMIT = 2 * 1024 * 1024;
export class FeedbackStore {
  constructor(readonly account: AccountStore) {
    account.db.exec(`CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),title TEXT NOT NULL,description TEXT NOT NULL,page TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',reply TEXT NOT NULL DEFAULT '',created INTEGER NOT NULL,updated INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS feedback_images(feedbackId TEXT NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,position INTEGER NOT NULL,mime TEXT NOT NULL,bytes BLOB NOT NULL,PRIMARY KEY(feedbackId,position));
      CREATE INDEX IF NOT EXISTS feedback_owner ON feedback(userId,created);`);
  }
  submit(userId: string, input: Record<string, unknown>) {
    const title=this.text(input.title,5,120,'请用5至120个字符概括问题');
    const description=this.text(input.description,10,5000,'请用10至5000个字符描述问题与复现步骤');
    const page=this.text(input.page??'',0,500,'页面路径过长');
    if(page && (!page.startsWith('/') || page.startsWith('//') || /[?#]/.test(page)))throw new AccountError(400,'invalid_page','请填写本站页面路径，不包含查询参数');
    const images=input.images??[];
    if(!Array.isArray(images)||images.length>3)throw new AccountError(400,'invalid_images','最多上传3张截图');
    const checked=images.map(image=>this.image(image));
    return this.account.transaction(()=>{
      const recent=this.account.db.prepare('SELECT count(*) AS n FROM feedback WHERE userId=? AND created>?').get(userId,this.account.now()-86400000) as {n:number};
      if(recent.n>=10)throw new AccountError(429,'feedback_limit','每天最多提交10个问题，请明天再试');
      const id=randomUUID(),now=this.account.now();
      this.account.db.prepare('INSERT INTO feedback(id,userId,title,description,page,created,updated) VALUES(?,?,?,?,?,?,?)').run(id,userId,title,description,page,now,now);
      checked.forEach((image,index)=>this.account.db.prepare('INSERT INTO feedback_images VALUES(?,?,?,?)').run(id,index,image.mime,image.bytes));
      return {id,status:'open'};
    });
  }
  text(value:unknown,min:number,max:number,message:string){if(typeof value!=='string'||value.trim().length<min||value.trim().length>max||/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value))throw new AccountError(400,'invalid_feedback',message);return value.trim();}
  image(value:unknown){
    if(!value||typeof value!=='object')throw new AccountError(400,'invalid_image','截图格式无效');
    const {mime,data}=value as {mime:unknown;data:unknown};
    if(typeof data!=='string'||data.length>Math.ceil(IMAGE_LIMIT/3)*4||!data.length||!/^[A-Za-z0-9+/]+={0,2}$/.test(data))throw new AccountError(400,'invalid_image','截图格式无效或超过2MB');
    const bytes=Buffer.from(data,'base64');
    if(bytes.toString('base64')!==data||bytes.length>IMAGE_LIMIT)throw new AccountError(400,'invalid_image','截图格式无效或超过2MB');
    const png=mime==='image/png'&&bytes.length>=45&&bytes.subarray(0,8).equals(Buffer.from('89504e470d0a1a0a','hex'))&&bytes.toString('ascii',12,16)==='IHDR'&&bytes.toString('ascii',bytes.length-8,bytes.length-4)==='IEND';
    const jpeg=mime==='image/jpeg'&&bytes.length>=12&&bytes[0]===255&&bytes[1]===216&&bytes[2]===255&&bytes[bytes.length-2]===255&&bytes[bytes.length-1]===217;
    const webp=mime==='image/webp'&&bytes.length>=20&&bytes.toString('ascii',0,4)==='RIFF'&&bytes.toString('ascii',8,12)==='WEBP'&&bytes.readUInt32LE(4)===bytes.length-8;
    if(!png&&!jpeg&&!webp)throw new AccountError(400,'invalid_image','仅支持PNG、JPEG和WebP截图');
    return {mime:mime as string,bytes};
  }
  list(userId?:string){return this.account.db.prepare(`SELECT ${userId?'':'u.email,'}f.id,f.title,f.description,f.page,f.status,f.reply,f.created,f.updated,(SELECT count(*) FROM feedback_images i WHERE i.feedbackId=f.id) AS imageCount FROM feedback f JOIN users u ON u.id=f.userId ${userId?'WHERE f.userId=?':''} ORDER BY f.created DESC LIMIT 100`).all(...(userId?[userId]:[]));}
  detail(id:string){return this.account.db.prepare('SELECT f.*,u.email,(SELECT count(*) FROM feedback_images i WHERE i.feedbackId=f.id) AS imageCount FROM feedback f JOIN users u ON u.id=f.userId WHERE f.id=?').get(id);}
  screenshot(id:string,index:number,userId?:string){return this.account.db.prepare(`SELECT i.mime,i.bytes FROM feedback_images i JOIN feedback f ON f.id=i.feedbackId WHERE i.feedbackId=? AND i.position=? ${userId?'AND f.userId=?':''}`).get(id,index,...(userId?[userId]:[])) as {mime:string;bytes:Uint8Array}|undefined;}
  update(id:string,status:string,reply:string){if(!['open','investigating','resolved'].includes(status))throw new Error('status must be open, investigating or resolved');const message=this.text(reply,0,2000,'处理说明最多2000个字符');const result=this.account.db.prepare('UPDATE feedback SET status=?,reply=?,updated=? WHERE id=?').run(status,message,this.account.now(),id);if(!result.changes)throw new Error('feedback not found');}
}
