#!/usr/bin/env python3
"""Unprivileged writer: PG/CAS are authoritative; /work/data is a disposable cache."""
import hashlib,json,os,re,subprocess,sys,time,uuid
from pathlib import Path
CODE=Path('/code');WORK=Path('/work');PUBLIC=Path('/public/v1');STORE=Path('/store')
sys.path.insert(0,str(CODE/'pipeline'))
from blob_store import FilesystemBlobStore
from shadow_store import restore_view,import_view
from input_snapshot import capture,assert_no_pending
from storage_migration import restore,build_manifest,copy_objects,validate_manifest
from data_publication import durable_write
ALLOWED={'LLM_API_KEY','TRANSLATION_API_KEY','OPENROUTER_API_KEY'}

def request(raw):
    if len(raw)>65536:raise ValueError('request too large')
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value)-{'mode','secrets'}:raise ValueError('invalid request')
    if value.get('mode') not in ['prepare','validate','update','publish']:raise ValueError('invalid mode')
    keys=value.get('secrets',{})
    if not isinstance(keys,dict) or set(keys)-ALLOWED or any(not isinstance(v,str) or len(v)>16384 or '\0' in v for v in keys.values()):raise ValueError('invalid credentials envelope')
    return value

def step(script,args=(),credentials=None,optional=False):
    env={**os.environ,'PATH':str(Path(sys.executable).parent)+':'+os.environ.get('PATH',''),'TZ':'Asia/Shanghai','MAAS_BROWSER_SANDBOX':'1'}
    # The browser stages never inherit the LLM/provider credentials.
    for key in ALLOWED:env.pop(key,None)
    env.update(credentials or {})
    print('stage',script,flush=True)
    result=subprocess.run([sys.executable,str(CODE/script),*args],cwd=CODE,env=env)
    if result.returncode and not optional:raise RuntimeError('stage failed: '+script)
    return result.returncode

def initialize(connection,published,blobs):
    version=published['site']['inputVersion'];data=WORK/'data';data.mkdir(exist_ok=True)
    pointer=data/'inputs-current.json'
    ready=False
    if pointer.exists():
        try:ready=json.loads(pointer.read_text())['inputVersion']==version;assert_no_pending(CODE)
        except (ValueError,KeyError):ready=False
    if ready:return
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
    restore(destination,raw,blobs)
    for child in (destination/'data').iterdir():child.rename(data/child.name)
    (destination/'data').rmdir();destination.rmdir()

def main():
    os.umask(0o027)
    incoming=request(sys.stdin.buffer.read(65537));mode=incoming['mode'];secrets=incoming.get('secrets',{})
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
        initialize(connection,published,blobs)
        if mode=='prepare':print(json.dumps({'status':'cache_ready'}));return
        if mode=='update':
            step('pipeline/scripts/fetch_sources.py')
            step('pipeline/scripts/sync-diff-to-site.py')
            pricing=step('pipeline/scripts/fetch-prices.py',['--concurrency','1'],optional=True)
            if pricing:print('health warning: all pricing sources failed; retained previous price facts',flush=True)
            step('pipeline/scripts/llm-digest.py',credentials={'LLM_API_KEY':secrets.get('LLM_API_KEY','')},optional=True)
            step('pipeline/scripts/sync-diff-to-site.py')
            step('pipeline/scripts/fetch-leaderboards.py',credentials={'OPENROUTER_API_KEY':secrets.get('OPENROUTER_API_KEY','')},optional=True)
            step('pipeline/scripts/translate-dynamic-en.py',credentials={'TRANSLATION_API_KEY':secrets.get('TRANSLATION_API_KEY','')},optional=True)
        step('pipeline/scripts/project-site-data.py')
        step('pipeline/scripts/validate-archive.py');step('pipeline/scripts/validate-price-archive.py')
        version=capture(CODE,'database-writer-'+uuid.uuid4().hex)
        raw=build_manifest(CODE,code);copied=copy_objects(CODE,raw,blobs)
        if copied['failures']:raise ValueError('raw copy failed')
        parent=published['site']['inputVersion']
        import_view(connection,CODE,blobs,source_commit=code,parent=parent if version!=parent else None)
        with connection:
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO maas_data.input_raw_manifests(input_version,manifest) VALUES(%s,%s) ON CONFLICT DO NOTHING',[version,Json(raw)])
        run_id=uuid.uuid4().hex;candidate=PUBLIC.parent/'candidates'/run_id
        report=WORK/'candidate-report.json'
        args=['--input-version',version,'--code-commit',code,'--config-root',str(CODE),'--blob-root',str(STORE/'blobs'),'--candidate-dir',str(candidate),'--report',str(report)]
        if mode=='validate':args+=['--expected-manifest',str(PUBLIC/'manifest.json')]
        step('pipeline/scripts/export-database-data.py',args)
        if hashlib.sha256((PUBLIC/'publication.json').read_bytes()).hexdigest()!=expected_hash:raise ValueError('publication changed during collection')
        receipt={'candidate':str(candidate),'inputVersion':version,'codeCommit':code,'expectedPublicationSha256':expected_hash}
        durable_write(WORK/'candidate.json',(json.dumps(receipt)+'\n').encode())
        print(json.dumps({'status':'candidate_ready','inputVersion':version,'mode':mode}),flush=True)
    finally:connection.close()
if __name__=='__main__':
    try:main()
    except Exception as error:
        print('data writer failed: '+type(error).__name__,file=sys.stderr);sys.exit(2)
