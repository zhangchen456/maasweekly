#!/usr/bin/env python3
"""Time isolated build phases; never publish or alter official datasets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time

BASE = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='docs/architecture/refactoring-2026-10/build-baseline.json')
    args = parser.parse_args()
    report = {'commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=BASE,text=True).strip(),
              'rounds': 3, 'phases': {}, 'limitations': ['Dependency installation is a clean node_modules with the existing npm cache, not an empty network cache.', 'Assembly samples site and public data copy; full production dependency assembly remains validated by the release builder.']}
    with tempfile.TemporaryDirectory(prefix='maas-build-profile-') as td:
        tmp = Path(td)
        commands = {
            'projection': (BASE, ['python3','pipeline/scripts/export-public-data.py','--dry-run']),
            'publicCheck': (BASE, ['python3','pipeline/scripts/export-public-data.py','--check']),
            'apiCompile': (BASE/'services/agent-api', ['npm','run','build']),
            'astroBuild': (BASE/'site', ['npm','exec','--','astro','build','--outDir',str(tmp/'site')]),
        }
        for phase, (cwd, command) in commands.items():
            times=[]
            for _ in range(3):
                start=time.monotonic()
                result=subprocess.run(command,cwd=cwd,capture_output=True,text=True)
                times.append(time.monotonic()-start)
                if result.returncode: raise RuntimeError(f'{phase}: {result.stdout[-2000:]} {result.stderr[-2000:]}')
            report['phases'][phase]={'command':command,'seconds':times,'medianSeconds':statistics.median(times)}
            print(phase,report['phases'][phase]['medianSeconds'],flush=True)
        times=[]
        for _ in range(3):
            dest=tmp/'assembly'; shutil.rmtree(dest,ignore_errors=True)
            start=time.monotonic()
            shutil.copytree(tmp/'site',dest/'site')
            shutil.copytree(BASE/'data/public/v1',dest/'data/public/v1')
            times.append(time.monotonic()-start)
        report['phases']['staticDataAssembly']={'seconds':times,'medianSeconds':statistics.median(times)}
        for name in ['site','services/agent-api']:
            times=[]
            dest=tmp/('install-'+Path(name).name); dest.mkdir()
            for f in ['package.json','package-lock.json']: shutil.copy2(BASE/name/f,dest/f)
            for _ in range(3):
                shutil.rmtree(dest/'node_modules',ignore_errors=True)
                start=time.monotonic()
                result=subprocess.run(['npm','ci','--offline','--silent'],cwd=dest,capture_output=True,text=True)
                times.append(time.monotonic()-start)
                if result.returncode:
                    report['phases']['cleanInstall:'+name]={'unverified':True,'reason':'offline cache incomplete','exitCode':result.returncode}
                    break
            else: report['phases']['cleanInstall:'+name]={'seconds':times,'medianSeconds':statistics.median(times),'npmCache':'warm','nodeModules':'empty'}
    out=BASE/args.output; out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__': main()
