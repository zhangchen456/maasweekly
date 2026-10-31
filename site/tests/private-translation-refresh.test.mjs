import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'private-translations-'));
const file=path.join(dir,'catalog.json');const previous=process.env.MAAS_PRIVATE_EN_TRANSLATIONS;
process.env.MAAS_PRIVATE_EN_TRANSLATIONS=file;
try {
 const b=await build({entryPoints:['src/lib/translation-server.ts'],bundle:true,write:false,format:'cjs',platform:'node'});
 const m={exports:{}};new Function('module','exports','require',b.outputFiles[0].text)(m,m.exports,createRequire(import.meta.url));
 const save=text=>{fs.writeFileSync(file+'.tmp',JSON.stringify({schemaVersion:1,texts:{'本期专属译文':text}}));fs.renameSync(file+'.tmp',file);};
 assert.equal(m.exports.privateTranslations()['本期专属译文'],undefined);
 save('First private edition');assert.equal(m.exports.englishServerHtml('<p>本期专属译文</p>'),'<p>First private edition</p>');
 save('Second private edition');assert.equal(m.exports.englishServerUi('本期专属译文'),'Second private edition');
 fs.writeFileSync(file,JSON.stringify({schemaVersion:1,texts:{'本期专属译文':42}}));assert.throws(()=>m.exports.englishServerUi('本期专属译文'),/Invalid private/);
 save('Recovered edition');assert.equal(m.exports.englishServerUi('本期专属译文'),'Recovered edition');
 fs.unlinkSync(file);assert.equal(m.exports.privateTranslations()['本期专属译文'],undefined);
 console.log('Private catalog creation, replacement, rejection, recovery and removal passed');
} finally {if(previous===undefined)delete process.env.MAAS_PRIVATE_EN_TRANSLATIONS;else process.env.MAAS_PRIVATE_EN_TRANSLATIONS=previous;fs.rmSync(dir,{recursive:true,force:true});}
