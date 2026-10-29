"""Securely copy a declared runtime package into root-owned storage, without tar extraction."""
import hashlib,json,os,posixpath,re,shutil,stat,tempfile
from pathlib import Path,PurePosixPath
MAX_BYTES=512*1024*1024

def source_file(root,name):
    parts=PurePosixPath(name).parts
    if not parts or name.startswith('/') or any(p in ('.','..') for p in parts):raise ValueError('unsafe package path')
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            nextfd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nextfd
        file=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        if not stat.S_ISREG(os.fstat(file).st_mode):os.close(file);raise ValueError('non-regular package file')
        return os.fdopen(file,'rb')
    finally:os.close(fd)

def install(incoming,destination):
    with source_file(incoming,'metadata/runtime-manifest.json') as stream:raw=stream.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('manifest too large')
    manifest=json.loads(raw);code=manifest['codeCommit']
    if not re.fullmatch('[a-f0-9]{40}',code) or manifest.get('dataIncluded') is not False or manifest.get('pageFormatVersion')!=1:raise ValueError('invalid runtime metadata')
    files=manifest['files']
    if not isinstance(files,list) or len(files)>30000 or sum(f.get('bytes',0) for f in files)>MAX_BYTES:raise ValueError('package budget exceeded')
    target=destination/code
    if target.exists():
        if (target/'metadata/runtime-manifest.json').read_bytes()!=raw:raise ValueError('code identity conflict')
        return target,manifest
    staging=Path(tempfile.mkdtemp(prefix='.install-',dir=destination));seen=set()
    try:
        for item in files:
            name=item['path'];parts=PurePosixPath(name).parts
            if not parts or name.startswith('/') or any(p in ('.','..') for p in parts) or name in seen or name=='metadata/runtime-manifest.json':raise ValueError('unsafe/duplicate package path')
            seen.add(name);output=staging/name
            output.parent.mkdir(parents=True,exist_ok=True)
            if not output.resolve().is_relative_to(staging):raise ValueError('package output escape')
            if 'symlink' in item:
                link=item['symlink'];resolved=posixpath.normpath(str(PurePosixPath(name).parent/link))
                if link.startswith('/') or resolved=='..' or resolved.startswith('../'):raise ValueError('package symlink escape')
                output.symlink_to(link);continue
            expected=item['bytes']
            if not isinstance(expected,int) or expected<0 or expected>256*1024*1024 or not re.fullmatch('[a-f0-9]{64}',item['sha256']):raise ValueError('invalid file metadata')
            digest=hashlib.sha256();count=0
            with source_file(incoming,name) as source,output.open('xb') as dest:
                while chunk:=source.read(1024*1024):
                    count+=len(chunk)
                    if count>expected:raise ValueError('package size changed')
                    digest.update(chunk);dest.write(chunk)
            if count!=expected or digest.hexdigest()!=item['sha256']:raise ValueError('package hash mismatch')
        # Verify after all writes too, in case declared internal links alias a path.
        for item in files:
            file=staging/item['path']
            if 'symlink' in item:
                if not file.is_symlink() or str(file.readlink())!=item['symlink']:raise ValueError('link conflict')
            elif file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('file alias conflict')
        (staging/'metadata').mkdir(exist_ok=True)
        (staging/'metadata/runtime-manifest.json').write_bytes(raw)
        os.rename(staging,target);return target,manifest
    finally:
        if staging.exists():shutil.rmtree(staging)
