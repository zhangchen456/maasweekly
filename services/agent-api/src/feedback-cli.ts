import { AdminStore } from './admin-store.js';
import { AdminFeedback } from './admin-feedback.js';
import { cliCommand } from './admin-cli-command.js';
import { AccountStore } from './account-store.js';
import { FeedbackStore } from './feedback-store.js';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
if (!process.env.MAAS_ACCOUNT_DB) throw new Error('MAAS_ACCOUNT_DB required');
const account=new AccountStore(process.env.MAAS_ACCOUNT_DB),store=new FeedbackStore(account);
const [command='list',id,arg,reply='']=process.argv.slice(2);
try {
  const service=new AdminFeedback(new AdminStore(account));const args=process.argv.slice(2);
  if(command==='list')console.log(JSON.stringify(store.list().map(item=>({...item,adminVersion:service.version(String(item.id))})),null,2));
  else if(command==='detail'&&id)console.log(JSON.stringify(service.detail(id),null,2));
  else if(command==='verify'&&id&&arg){const input=JSON.parse(arg);console.log(JSON.stringify(service.write(cliCommand(args,'feedback.verify','feedback',id,input,()=>service.version(id)),'verify')));}
  else if(command==='status'&&id&&arg){const stage=({open:'triage',investigating:'investigating',resolved:'resolved'} as Record<string,string>)[arg];if(!stage)throw new Error('status must be open, investigating or resolved');const i=args.indexOf('--resolution-type');const input={stage,publicReply:reply,...(i>=0?{resolutionType:args[i+1]}:{})};console.log(JSON.stringify(service.write(cliCommand(args,'feedback.update','feedback',id,input,()=>service.version(id)),'update')));}
  else if(command==='export'&&id&&arg){
    const item=store.detail(id);if(!item)throw new Error('feedback not found');
    const directory=path.resolve(arg);mkdirSync(directory,{recursive:true,mode:0o700});
    writeFileSync(path.join(directory,'feedback.json'),JSON.stringify(item,null,2),{mode:0o600});
    for(let index=0;index<3;index++){const image=store.screenshot(id,index);if(image)writeFileSync(path.join(directory,`screenshot-${index+1}.${image.mime==='image/png'?'png':image.mime==='image/jpeg'?'jpg':'webp'}`),image.bytes,{mode:0o600});}
    console.log('Feedback exported.');
  }else throw new Error('Usage: feedback-cli.js list | detail ID | status ID open|investigating|resolved [reply] --actor ACTOR --reason REASON --expected-version N [--key KEY] [--resolution-type KIND] | verify ID JSON --actor ACTOR --reason REASON --expected-version N | export ID DIRECTORY');
}finally{account.close();}
