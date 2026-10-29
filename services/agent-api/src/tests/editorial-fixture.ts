/** Small fixed editorial evidence: ordinary tests never depend on live archives. */
import {mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {Dataset} from '../dataset.js';
import {ReleaseFixture} from './fixture.js';
export function editorialDataset():Dataset {
  const fixture=new ReleaseFixture(mkdtempSync(path.join(tmpdir(),'editorial-evidence-')));
  try {
    fixture.writeRelease('ds_'+'e'.repeat(64),{
      dataThrough:'2026-09-28',
      providers:[{providerId:'google',displayName:'Google',region:'global'}],
      changes:[{id:'obs_'+'e'.repeat(64),providerId:'google',sourceId:'google-vertex-changelog',observationDate:'2026-09-27',title:'Fixed Vertex capability observation'}],
    });
    return Dataset.load(fixture.root);
  } finally {fixture.cleanup();}
}
