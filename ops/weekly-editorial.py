#!/usr/bin/env python3
"""Prepare evidence packets and verify reviewed formal drafts; never auto-publish prose."""
import argparse, hashlib, json, re, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CHECKS=('evidence','observationDates','claims','englishPrivate','previewBoundary')
SECTIONS=('重要更新摘要','各平台详细追踪','各平台状态汇总表','趋势洞察','关注时间点','已报道事件索引')

def period(today):
    # Latest fully completed Tuesday; Tuesday itself is still in progress.
    end=today-timedelta(days=((today.weekday()-1)%7 or 7))
    return end-timedelta(days=6),end

def load(url):
    with urllib.request.urlopen(url,timeout=30) as response:return json.load(response)

def collect(root,start,end,fetch=load):
    params={'from':start.isoformat(),'to':(end+timedelta(days=1)).isoformat(),'limit':100}
    rows=[];version=None;seen=set();cursors=set();coverage=None
    for _ in range(200):
        page=fetch(root.rstrip('/')+'/changes?'+urllib.parse.urlencode(params))
        if version is not None and page['datasetVersion']!=version:raise ValueError('dataset changed; restart packet preparation')
        version=page['datasetVersion'];coverage=page['coverage']
        for row in page['items']:
            if not start.isoformat()<=row['observationDate']<=end.isoformat():raise ValueError('observation outside period')
            if row['id'] in seen:raise ValueError('duplicate observation across pages')
            seen.add(row['id']);rows.append(row)
        cursor=page['page']['nextCursor']
        if not cursor:break
        if cursor in cursors:raise ValueError('repeated cursor')
        cursors.add(cursor);params={'cursor':cursor}
    else:raise ValueError('packet pagination limit reached; refusing partial evidence')
    return {'schemaVersion':1,'periodStart':str(start),'periodEnd':str(end),'datasetVersion':version,'coverage':coverage,'observations':rows}

def prepare(root,out,today,requested=None):
    start,end=period(today)
    if requested:
        end=date.fromisoformat(requested);start=end-timedelta(days=6)
        if end.weekday()!=1 or end>=today:raise ValueError('period must end on a completed Tuesday')
    packet=collect(root,start,end);folder=out/end.isoformat();folder.mkdir(parents=True,exist_ok=False)
    (folder/'evidence.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n')
    summary=[f'# 周报素材 {end}',f'追踪周期：{start} ~ {end}',f"数据版本：{packet['datasetVersion']}",
        '这是选题素材，不是已核实的发布稿。逐条复核原始增删行和官方来源；LLM摘要仅供检索，观察日期不等于发布日期。',
        '优先选模型/API变化、价格和计费条件、迁移/下线、接入与合规设置。导航噪声、首次抓取、缺失值不写成事件。',
        '全量观察见 evidence.json；下面仅列来源更新供人工筛选，不代表全部都值得报道。']
    for row in packet['observations']:
        if row['recordType']=='source_observation':
            summary.append(f"- {row['observationDate']} · {row['providerId']} · {row['id']} · {row['title']} · {row.get('links',{}).get('sourceUrl','')}")
    (folder/'brief.md').write_text('\n\n'.join(summary)+'\n')
    draft=f'# MaaS 周报 {end}\n\n追踪周期：{start} ~ {end}\n\n'
    for i,section in enumerate(SECTIONS,1):draft+=f'## {"一二三四五六"[i-1]}、{section}\n\nTODO：编辑完成本节；无明确时间节点时注明本期无已确认节点。\n\n'
    (folder/f'{end}.md').write_text(draft)
    receipt={'schemaVersion':1,'periodStart':str(start),'periodEnd':str(end),'draftSha256':'TODO','datasetVersion':packet['datasetVersion'],'reviewedBy':'TODO','reviewedAt':'TODO','checks':dict.fromkeys(CHECKS,False),'evidenceIds':[]}
    (folder/'release.template.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'packet':str(folder),'observations':len(packet['observations']),'periodEnd':str(end)}))

def check(draft,receipt,today):
    raw=draft.read_bytes();text=raw.decode();meta=json.loads(receipt.read_text())
    end=date.fromisoformat(draft.stem);start=end-timedelta(days=6)
    if end>=today:raise ValueError('cannot publish an unfinished observation period')
    if meta.get('schemaVersion')!=1 or meta.get('periodStart')!=str(start) or meta.get('periodEnd')!=str(end):raise ValueError('review period mismatch')
    if meta.get('draftSha256')!=hashlib.sha256(raw).hexdigest():raise ValueError('draft changed since editorial review')
    reviewed=datetime.fromisoformat(meta['reviewedAt'])
    if reviewed.tzinfo is None or reviewed.date()>today or reviewed.date()<end:raise ValueError('invalid review date')
    if not meta.get('reviewedBy') or meta['reviewedBy']=='TODO' or any(meta.get('checks',{}).get(k) is not True for k in CHECKS):raise ValueError('editorial checklist incomplete')
    if not re.fullmatch(r'ds_[0-9a-f]{64}',meta.get('datasetVersion','')):raise ValueError('missing evidence dataset')
    if re.search(r'TODO|TBD|待填写|待核实',text):raise ValueError('unfinished draft placeholder')
    if not re.search(r'追踪周期.*?'+str(start)+r'\s*~\s*'+str(end),text):raise ValueError('draft period mismatch')
    for section in SECTIONS:
        if not re.search(r'^## .*(?:'+section+r')\s*$',text,re.M):raise ValueError('missing section: '+section)
    sections=re.split(r'^## .+$',text,flags=re.M)[1:]
    if any(not section.strip() for section in sections):raise ValueError('empty report section')
    headlines=text.split('重要更新摘要',1)[1].split('\n## ',1)[0]
    if not re.search(r'^\d+\.\s+\*\*[^*]+\*\*',headlines,re.M):raise ValueError('missing structured headline')
    table=text.split('各平台状态汇总表',1)[1].split('\n## ',1)[0]
    rows=[line for line in table.splitlines() if line.strip().startswith('|')]
    if len(rows)<3 or any(len(line.strip().strip('|').split('|'))!=4 for line in rows):raise ValueError('platform table requires four columns and content')
    ids=set(re.findall(r'/item/(obs_[0-9a-f]{64})/',text))
    if not ids or ids!=set(meta.get('evidenceIds',[])):raise ValueError('reviewed evidence differs from draft references')
    if not re.search(r'\]\(https://',text):raise ValueError('official source links required')
    return {'periodEnd':str(end),'draftSha256':meta['draftSha256'],'evidenceCount':len(ids),'status':'reviewed'}

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--root',default='https://daily.maas.click/api/v1');prep.add_argument('--out',type=Path,required=True);prep.add_argument('--period')
    verify=sub.add_parser('check');verify.add_argument('--draft',type=Path,required=True);verify.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args();today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    if args.command=='prepare':prepare(args.root,args.out,today,args.period)
    else:print(json.dumps(check(args.draft,args.receipt,today)))
if __name__=='__main__':main()
