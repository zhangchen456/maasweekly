import { AccountStore } from './account-store.js';
import { FeedbackStore } from './feedback-store.js';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
if (!process.env.MAAS_ACCOUNT_DB) throw new Error('MAAS_ACCOUNT_DB required');
const account=new AccountStore(process.env.MAAS_ACCOUNT_DB),store=new FeedbackStore(account);
const [command='list',id,arg,reply='']=process.argv.slice(2);
try {
  if(command==='list')console.log(JSON.stringify(store.list(),null,2));
  else if(command==='status'&&id&&arg){store.update(id,arg,reply);console.log('Feedback updated.');}
  else if(command==='export'&&id&&arg){
    const item=store.detail(id);if(!item)throw new Error('feedback not found');
    const directory=path.resolve(arg);mkdirSync(directory,{recursive:true,mode:0o700});
    writeFileSync(path.join(directory,'feedback.json'),JSON.stringify(item,null,2),{mode:0o600});
    for(let index=0;index<3;index++){const image=store.screenshot(id,index);if(image)writeFileSync(path.join(directory,`screenshot-${index+1}.${image.mime==='image/png'?'png':image.mime==='image/jpeg'?'jpg':'webp'}`),image.bytes,{mode:0o600});}
    console.log('Feedback exported.');
  }else throw new Error('Usage: feedback-cli.js list | status ID open|investigating|resolved [reply] | export ID DIRECTORY');
}finally{account.close();}
