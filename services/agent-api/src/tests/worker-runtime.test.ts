import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {runWorker} from '../worker-runtime.js';
test('TERM drains one in-flight task and never claims the next',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'worker-drain-'));const receipt=join(dir,'ready.json');let calls=0,finished=false;
 try {await runWorker(async()=>{calls++;process.emit('SIGTERM');assert.equal(JSON.parse(readFileSync(receipt,'utf8')).phase,'draining');await new Promise(r=>setTimeout(r,10));finished=true;return true;},{name:'test',receipt});
 assert.equal(calls,1);assert.equal(finished,true);assert.equal(JSON.parse(readFileSync(receipt,'utf8')).phase,'stopped');}finally{rmSync(dir,{recursive:true,force:true});}
});
test('TERM during input reload prevents claiming',async()=>{
 let calls=0;await runWorker(async()=>{calls++;return true;},{name:'test',prepare:async()=>{process.emit('SIGTERM');}});assert.equal(calls,0);
});
