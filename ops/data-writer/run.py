#!/usr/bin/env python3
"""Unprivileged writer: PG/CAS are authoritative; /work/data is a disposable cache."""
import hashlib,json,os,re,subprocess,sys,time,uuid
from pathlib import Path
CODE=Path('/code');WORK=Path('/work');PUBLIC=Path('/public/v1');STORE=Path('/store')
sys.path.insert(0,str(CODE/'pipeline'))
from blob_store import FilesystemBlobStore
from shadow_store import restore_view,import_view
from input_snapshot import capture,assert_no_pending,load_view,restore_mutable,assert_mutable_matches
from storage_migration import restore,build_manifest,copy_objects,validate_manifest
from data_publication import durable_write
ALLOWED={'LLM_API_KEY','TRANSLATION_API_KEY','OPENROUTER_API_KEY'}
PINNED_STAGES={
 'pipeline/scripts/fetch_sources.py','pipeline/scripts/sync-diff-to-site.py',
 'pipeline/scripts/fetch-prices.py','pipeline/scripts/llm-digest.py',
 'pipeline/scripts/fetch-leaderboards.py','pipeline/scripts/translate-dynamic-en.py',
}

def request(raw):
    if len(raw)>1048576:raise ValueError('request too large')
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value)-{'mode','secrets','drafts','sourceCommit','runContext','inputVersion'}:raise ValueError('invalid request')
    if value.get('mode') not in ['prepare','validate','update','publish','weekly','aggregate','import','rebuild','resume']:raise ValueError('invalid mode')
    if value.get('mode')=='resume':
        if not isinstance(value.get('inputVersion'),str) or not re.fullmatch('in_[a-f0-9]{64}',value['inputVersion']) or value.get('drafts'):raise ValueError('resume requires an explicit input version and no drafts')
    elif 'inputVersion' in value:raise ValueError('inputVersion is only valid for resume')
    keys=value.get('secrets',{})
    if not isinstance(keys,dict) or set(keys)-ALLOWED or any(not isinstance(v,str) or len(v)>16384 or '\0' in v for v in keys.values()):raise ValueError('invalid credentials envelope')
    drafts=value.get('drafts',[])
    if not isinstance(drafts,list) or len(drafts)>52:raise ValueError('invalid drafts')
    for draft in drafts:
        if not isinstance(draft,dict) or set(draft)!={'date','markdown'} or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',draft['date']) or not isinstance(draft['markdown'],str) or len(draft['markdown'].encode())>131072 or '\0' in draft['markdown']:raise ValueError('invalid draft')
    if drafts and not re.fullmatch('[a-f0-9]{40}',value.get('sourceCommit','')):raise ValueError('draft source commit required')
    context=value.get('runContext',{})
    if not isinstance(context,dict) or set(context)-{'GITHUB_RUN_ID','GITHUB_REPOSITORY','GITHUB_EVENT_NAME'} or any(not isinstance(v,str) or len(v)>256 or '\0' in v for v in context.values()):raise ValueError('invalid run context')
    return value

def timed(label, callback, *args, **kwargs):
    started=time.monotonic()
    try:return callback(*args,**kwargs)
    finally:print(json.dumps({'kind':'writer.timing','stage':label,'elapsedSeconds':round(time.monotonic()-started,3)}),flush=True)

def step(script,args=(),credentials=None,optional=False,pinned=False):
    env={**os.environ,'PATH':str(Path(sys.executable).parent)+':'+os.environ.get('PATH',''),'TZ':'Asia/Shanghai','MAAS_BROWSER_SANDBOX':'1'}
    # The browser stages never inherit the LLM/provider credentials.
    for key in ALLOWED:env.pop(key,None)
    env.update(credentials or {})
    # Legacy full-weekly injection keeps a fresh baseline. Formal import opts
    # in only because its immutable request is applied inside the journal.
    env['MAAS_PIPELINE_PINNED_BASELINE']='1' if pinned or script in PINNED_STAGES else '0'
    print('stage',script,flush=True)
    result=timed(script,subprocess.run,[sys.executable,str(CODE/script),*args],cwd=CODE,env=env)
    if result.returncode:
        print('stage exit',script,result.returncode,flush=True)
        if not optional:raise RuntimeError('stage failed: '+script)
    return result.returncode

def import_formal(drafts,secrets,source_commit=None):
    # Drafts enter inside the journal, so its committed baseline can be reused.
    # The immutable request survives interruption and is replayed on recovery.
    raw=(json.dumps(drafts,ensure_ascii=False,sort_keys=True)+'\n').encode()
    path=WORK/'formal-drafts'/(hashlib.sha256(raw).hexdigest()+'.json')
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('draft request collision')
    else:
        path.parent.mkdir(parents=True,exist_ok=True);durable_write(path,raw)
    args=['--drafts-file',str(path),'--defer-site-projection']
    if source_commit:args+=['--source-commit',source_commit]
    step('site/scripts/import-weekly.py',args,pinned=True)
    check=step('pipeline/scripts/translate-dynamic-en.py',['--check'],optional=True)
    if check==1:
        if not secrets.get('TRANSLATION_API_KEY'):raise ValueError('missing translations and no translation credential')
        step('pipeline/scripts/translate-dynamic-en.py',credentials={'TRANSLATION_API_KEY':secrets['TRANSLATION_API_KEY']})
        step('pipeline/scripts/translate-dynamic-en.py',['--check'])
    elif check!=0:raise RuntimeError('translation completeness check failed')

def initialize(connection,published,blobs):
    version=published['site']['inputVersion'];data=WORK/'data';data.mkdir(exist_ok=True)
    pointer=data/'inputs-current.json'
    ready=False
    if pointer.exists():
        try:ready=json.loads(pointer.read_text())['inputVersion']==version;assert_no_pending(CODE)
        except (ValueError,KeyError):ready=False
    if ready:
        restore_mutable(CODE,load_view(CODE));return
    # Preserve interrupted observations rather than silently deleting the cache.
    archive=WORK/'recovery'/str(time.time_ns());archive.mkdir(parents=True)
    for child in list(data.iterdir()):
        if child.name!='model-registry':child.rename(archive/child.name)
    with connection.cursor() as cursor:
        cursor.execute('SELECT manifest FROM maas_data.input_raw_manifests WHERE input_version=%s',[version]);row=cursor.fetchone()
    if not row:raise ValueError('published raw recovery inventory missing')
    raw=validate_manifest(row[0]);destination=WORK/('restore-'+uuid.uuid4().hex)
    print('restoring committed input',version,flush=True)
    restore_view(connection,version,blobs,destination)
    restore_mutable(destination,load_view(destination))
    restore(destination,raw,blobs)
    for child in (destination/'data').iterdir():child.rename(data/child.name)
    (destination/'data').rmdir();destination.rmdir()

def select_ingest_input(expected_version=None, pinned_version=None):
    if pinned_version is not None:
        if expected_version is not None:raise ValueError('conflicting input modes')
        assert_no_pending(CODE)
        view=load_view(CODE)
        if view is None or view.version!=pinned_version:raise ValueError('committed input pointer changed')
        timed('ingest.check_mutable',assert_mutable_matches,CODE,view)
        return view.version
    version=timed('ingest.capture',capture,CODE,'database-writer-'+uuid.uuid4().hex,publish=expected_version is None)
    if expected_version is not None and version!=expected_version:raise ValueError('recovery input changed; refusing import')
    return version


def ingest(parent,code,expected_version=None,pinned_version=None):
    # Exit this process before exporting: Python retains large import heaps even
    # after local variables are freed. Import+export must fit the same 1.5GiB cap.
    if os.getuid()==0:raise ValueError('unprivileged writer required')
    import psycopg2
    from psycopg2.extras import Json
    connection=psycopg2.connect(os.environ['MAAS_DATA_DSN']);blobs=FilesystemBlobStore(STORE/'blobs')
    try:
        version=select_ingest_input(expected_version,pinned_version)
        raw_manifest=timed('ingest.raw_manifest',build_manifest,CODE,code);copied=timed('ingest.raw_copy',copy_objects,CODE,raw_manifest,blobs)
        if copied['failures']:raise ValueError('raw copy failed')
        timed('ingest.database',import_view,connection,CODE,blobs,source_commit=code,parent=parent if version!=parent else None,expected_input=version)
        with connection:
            with connection.cursor() as cursor:
                # Execution logs are audit history, not inputs: replaying an old
                # observation must not change its committed business snapshot.
                for pattern in ['data/pipeline-runs/*/*.json','data/price-runs/*/*.json']:
                    for path in CODE.glob(pattern):
                        raw=path.read_bytes();json.loads(raw)
                        cursor.execute('INSERT INTO maas_data.writer_run_logs(logical_path,sha256,payload_json) VALUES(%s,%s,%s) ON CONFLICT(logical_path) DO UPDATE SET sha256=excluded.sha256,payload_json=excluded.payload_json,updated_at=now()', [str(path.relative_to(CODE)),hashlib.sha256(raw).hexdigest(),raw.decode()])
                cursor.execute('INSERT INTO maas_data.input_raw_manifests(input_version,manifest) VALUES(%s,%s) ON CONFLICT DO NOTHING',[version,Json(raw_manifest)])
                cursor.execute("INSERT INTO maas_data.writer_heads(name,input_version) VALUES('public',%s) ON CONFLICT(name) DO UPDATE SET input_version=excluded.input_version,updated_at=now()",[version])
        durable_write(WORK/'ingestion.json',(json.dumps({'inputVersion':version})+'\n').encode())
    finally:connection.close()

def prepare_candidate(version,code,mode,expected_hash,warnings):
    run_id=uuid.uuid4().hex;candidate=PUBLIC.parent/'candidates'/run_id
    report=WORK/'candidate-report.json'
    args=['--input-version',version,'--code-commit',code,'--config-root',str(CODE),'--blob-root',str(STORE/'blobs'),'--candidate-dir',str(candidate),'--report',str(report)]
    if mode=='validate':args+=['--expected-manifest',str(PUBLIC/'manifest.json')]
    step('pipeline/scripts/export-database-data.py',args)
    if hashlib.sha256((PUBLIC/'publication.json').read_bytes()).hexdigest()!=expected_hash:raise ValueError('publication changed during collection')
    receipt={'candidate':str(candidate),'inputVersion':version,'codeCommit':code,'expectedPublicationSha256':expected_hash,'warnings':warnings}
    durable_write(WORK/'candidate.json',(json.dumps(receipt)+'\n').encode())
    print(json.dumps({'status':'candidate_ready','inputVersion':version,'mode':mode}),flush=True)

def main():
    os.umask(0o027)
    incoming=request(sys.stdin.buffer.read(1048577));mode=incoming['mode'];secrets=incoming.get('secrets',{})
    os.environ.update(incoming.get('runContext',{}))
    if os.getuid()==0:raise ValueError('unprivileged writer required')
    code=os.environ['MAAS_CODE_COMMIT']
    if not re.fullmatch('[0-9a-f]{40}',code):raise ValueError('fixed code commit required')
    import psycopg2
    from psycopg2.extras import Json
    connection=psycopg2.connect(os.environ['MAAS_DATA_DSN']);blobs=FilesystemBlobStore(STORE/'blobs')
    try:
        frozen=(PUBLIC/'publication.json').read_bytes();expected_hash=hashlib.sha256(frozen).hexdigest()
        published=json.loads(frozen)
        if mode=='publish':
            from data_publication import activate
            receipt=json.loads((WORK/'candidate.json').read_text())
            candidate=Path(receipt['candidate'])
            if not candidate.is_relative_to(PUBLIC.parent/'candidates'):raise ValueError('candidate root escape')
            result=activate(connection,candidate,PUBLIC,receipt['expectedPublicationSha256'])
            print(json.dumps(result));return
        with connection.cursor() as cursor:
            cursor.execute("SELECT input_version FROM maas_data.writer_heads WHERE name='public'");head=cursor.fetchone()
        parent=head[0] if head else published['site']['inputVersion']
        connection.commit()
        # Validation reads the already committed database head; it neither
        # rewrites the cache nor repeats a completed import/restore drill.
        if mode in ['validate','rebuild']:
            prepare_candidate(parent,code,mode,expected_hash,[]);return
        if mode=='resume':
            assert_no_pending(CODE)
            view=load_view(CODE)
            if view is None or view.version!=incoming['inputVersion']:raise ValueError('recovery checkpoint changed')
            del view
        else:
            timed('initialize',initialize,connection,{**published,'site':{**published['site'],'inputVersion':parent}},blobs)
        if mode=='prepare':print(json.dumps({'status':'cache_ready'}));return
        warnings=[]
        if mode in ['update','weekly','aggregate']:
            step('pipeline/scripts/fetch_sources.py')
            step('pipeline/scripts/sync-diff-to-site.py')
        if mode=='update':
            pricing=step('pipeline/scripts/fetch-prices.py',['--concurrency','1'],optional=True)
            if pricing:warnings.append('pricing_all_failed')
            step('pipeline/scripts/llm-digest.py',credentials={'LLM_API_KEY':secrets.get('LLM_API_KEY','')},optional=True)
            step('pipeline/scripts/sync-diff-to-site.py')
            step('pipeline/scripts/fetch-leaderboards.py',credentials={'OPENROUTER_API_KEY':secrets.get('OPENROUTER_API_KEY','')},optional=True)
            step('pipeline/scripts/translate-dynamic-en.py',credentials={'TRANSLATION_API_KEY':secrets.get('TRANSLATION_API_KEY','')},optional=True)
        if mode=='weekly':
            for draft in incoming.get('drafts',[]):
                path=CODE/'data/weekly'/(draft['date']+'.md');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(draft['markdown'])
            step('pipeline/scripts/llm-weekly-digest.py',['--all'],credentials={'LLM_API_KEY':secrets.get('LLM_API_KEY','')},optional=True)
            step('site/scripts/import-weekly.py')
            step('pipeline/scripts/translate-dynamic-en.py',credentials={'TRANSLATION_API_KEY':secrets.get('TRANSLATION_API_KEY','')},optional=True)
        pinned_version=None
        if mode=='import':
            import_formal(incoming.get('drafts',[]),secrets,incoming.get('sourceCommit'))
            pinned_version=load_view(CODE).version
        step('pipeline/scripts/project-site-data.py')
        step('pipeline/scripts/validate-archive.py');step('pipeline/scripts/validate-price-archive.py')
        if incoming.get('drafts') and mode!='import':
            source=incoming['sourceCommit'];path=CODE/'data/derived/import-provenance'/(source+'.json');path.parent.mkdir(parents=True,exist_ok=True)
            value={'sourceCommit':source,'drafts':[{'date':d['date'],'sha256':hashlib.sha256(d['markdown'].encode()).hexdigest()} for d in incoming['drafts']]}
            if path.exists() and json.loads(path.read_text())!=value:raise ValueError('draft source identity conflict')
            durable_write(path,(json.dumps(value)+'\n').encode())
        args=['--ingest-pinned',parent,code,pinned_version] if pinned_version else ['--ingest',parent,code]
        if mode=='resume':args.append(incoming['inputVersion'])
        step('ops/data-writer/run.py',args)
        version=json.loads((WORK/'ingestion.json').read_text())['inputVersion']
        prepare_candidate(version,code,mode,expected_hash,warnings)
    finally:connection.close()
if __name__=='__main__':
    try:
        if len(sys.argv)==5 and sys.argv[1]=='--ingest-pinned':ingest(sys.argv[2],sys.argv[3],pinned_version=sys.argv[4])
        elif len(sys.argv) in (4,5) and sys.argv[1]=='--ingest':ingest(sys.argv[2],sys.argv[3],sys.argv[4] if len(sys.argv)==5 else None)
        else:main()
    except Exception as error:
        print('data writer failed: '+type(error).__name__,file=sys.stderr);sys.exit(2)
