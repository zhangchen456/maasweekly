#!/usr/bin/env python3
"""Thin CI client: fixed SSH action, credential envelope over stdin, no data checkout."""
import argparse,json,os,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--mode',choices=['update','rebuild','validate','weekly','aggregate','import'],required=True);p.add_argument('--drafts',type=Path);a=p.parse_args()
request={'mode':a.mode,'secrets':{k:os.environ.get(k,'') for k in ['LLM_API_KEY','TRANSLATION_API_KEY','OPENROUTER_API_KEY']}}
if a.drafts:
 request['drafts']=[{'date':f.stem,'markdown':f.read_text()} for f in sorted(a.drafts.glob('*.md')) if re.fullmatch(r'\d{4}-\d{2}-\d{2}',f.stem)]
 request['sourceCommit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
request['runContext']={k:os.environ.get(k,'') for k in ['GITHUB_RUN_ID','GITHUB_REPOSITORY','GITHUB_EVENT_NAME']}
body=json.dumps(request).encode()
if len(body)>1048576:raise ValueError('data request exceeds 1MiB')
subprocess.run(['ssh','-i',os.environ.get('MAAS_SSH_KEY',str(Path.home()/'.ssh/id_ed25519')),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=ops/known_hosts.production','-o','ConnectTimeout=30','-o','ServerAliveInterval=15','maasdeploy@47.237.135.97','data-update'],input=body,check=True)
