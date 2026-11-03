#!/usr/bin/env python3
"""Daily operator report, with durable once-per-day mail and bounded public-link checks."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time
from daily_data_alert import AlertStore, ResendMailer, ROOT, collect, conditions, local_time, day
from operations_checks import inspect_links, service_label


def inspect(now=None, shared=ROOT, registry_file=Path('/usr/local/lib/maasweekly/inspection-sources.json'), *, sample=None, links=None):
    now = time.time() if now is None else now
    sample = collect(now, shared=shared) if sample is None else sample
    sample['links'] = inspect_links(registry_file) if links is None else links
    operations=sample.get('operations',{})
    operations['issues']=[reason for reason in operations.get('issues',[]) if reason != 'inspection_stale']
    return sample


def report_text(sample):
    rows = ['MaaSDaily 每日巡检', '检查时间：'+local_time(sample['checkedAt']),
            '数据截至：'+(sample.get('dataThrough') or '未能确认'),
            '发布与实际加载：'+('一致' if sample.get('consistent') else '异常或未能确认'),
            '当天数据迟到告警时间：13:00（Asia/Shanghai）；明确失败、进程退出和服务异常仍及时检查。']
    reasons=conditions(sample)
    from daily_data_alert import LABELS
    rows+=['当前告警条件：'+('；'.join(LABELS[x] for x in sorted(reasons)) if reasons else '无')]
    daily=sample.get('daily')
    if daily:
        rows+=['最近完整每日任务：'+daily['state']+'；阶段：'+str(daily.get('failureStage') or daily['stage']),
               '任务开始：'+local_time(daily['startedAt']/1000)]
    github=sample.get('github')
    if github:
        rows+=['最近GitHub任务：'+github['status']+' / '+str(github.get('conclusion') or '尚未结束')+'；创建：'+local_time(github['createdAt']),
               '任务记录：https://github.com/zhangchen456/maasweekly/actions/runs/'+str(github['id'])]
    else:rows+=['GitHub任务：未能核对']
    for key,label in [('sourceStreams','内容来源'),('priceStreams','报价来源')]:
        value=sample.get('sources',{}).get(key)
        rows+= [label+'：'+(f"{value['ok']}/{value['total']} 正常" if value and value['total'] else '未能确认')]
        for problem in (value or {}).get('problems',[]):
            rows+=['  '+str(problem.get('sourceKey') or problem.get('sourceId'))+'：'+str(problem['state'])]
    ops=sample.get('operations',{});resources=ops.get('resources',{})
    rows+=['', '服务器资源']
    disk=resources.get('disk')
    if disk:
        gib=lambda v: str(round(v/1024**3,2))+' GiB'
        rows += ['磁盘：总量 '+gib(disk['totalBytes'])+'；已用 '+gib(disk['usedBytes'])+f"（{disk['usedPercent']}%）；可用 "+gib(disk['availableBytes']),
                 'inode使用率：'+str(disk.get('inodeUsedPercent'))+'%；磁盘状态：'+disk['severity'],
                 '空间提醒阈值：使用率≥80%或可用<8GiB；危急阈值：使用率≥90%或可用<3GiB。']
    else:rows+=['磁盘：未能读取']
    memory=resources.get('memory')
    if memory:
        rows += [f"内存：总量 {round(memory['totalBytes']/1024**3,2)} GiB；可用 {round(memory['availableBytes']/1024**3,2)} GiB（{memory['availablePercent']}%）",
                 f"交换空间：已用 {round(memory['swapUsedBytes']/1024**3,2)} / {round(memory['swapTotalBytes']/1024**3,2)} GiB"]
    else:rows+=['内存：未能读取']
    load=resources.get('load')
    if load:rows += [f"负载（1/5/15分钟）：{', '.join(str(round(x,2)) for x in load['averages'])}；CPU数量：{load['cpuCount']}"]
    rows+=['', '服务与定时任务']
    for service in ops.get('services',[]):
        label={'normal':'正常','running':'执行中','expected_paused':'按预期暂停','abnormal':'异常','unexpected_or_unknown':'与预期暂停状态不符或未知'}[service['status']]
        rows += [service_label(service['unit'])+'：'+label]
        if service['status'] not in ['normal','running','expected_paused']:
            rows += ['  '+service['unit']+'；状态 '+service['state']+'/'+service['subState']+'；最近结果 '+service['result']]
    rows+=['数据库接受连接：'+('是' if ops.get('databaseAcceptingConnections') else '否或未能核对')]
    if ops.get('databaseBytes') is not None:rows+=['业务数据库体积：'+str(round(ops['databaseBytes']/1024**3,2))+' GiB']
    mail=ops.get('mail',{})
    mail_labels={'pending':'待发送','accepted':'服务商已接收','sent':'已发出','delivered':'已投递','failed':'失败','review':'需人工核对','cancelled':'已取消','suppressed':'已抑制','sending':'发送中','other':'其他'}
    rows+=['邮件队列（仅计数）：'+('；'.join(mail_labels[k]+' '+str(v) for k,v in mail['counts'].items()) if 'counts' in mail and mail['counts'] else '无任务' if 'counts' in mail else '未能核对')]
    if mail.get('oldestPendingAgeSeconds') is not None:rows+=['最早待发邮件已等待：'+str(round(mail['oldestPendingAgeSeconds']/60,1))+'分钟']
    backup=ops.get('backup',{})
    rows+=['本地账号备份：'+str(backup.get('status','unknown'))+'；保留 '+str(backup.get('retained','未知'))+' 份；最近备份 '+(local_time(backup['latestAt']) if backup.get('latestAt') else '未能确认'),
           '备份存在与时间不等于本次已执行恢复演练；云盘备份按当前设置暂停。']
    links=sample['links'];site=links['site'];external=links['external']
    rows+=['', '网站入口与外部链接', f"网站入口：{sum(r['status']=='ok' for r in site)}/{len(site)} 正常",
           f"外部链接：发现 {links['discovered']}；已检查 {links['checked']}；正常 {sum(r['status']=='ok' for r in external)}；访问受限 {sum(r['status']=='restricted' for r in external)}；异常/未能确认 {sum(r['status'] not in ['ok','restricted'] for r in external)}；未覆盖 {links['omitted']}"]
    for label,values in [('网站入口异常',site),('外部链接异常或需复核',external)]:
        failures=[r for r in values if r['status']!='ok']
        if failures:
            rows += [label+'：']
            for link in failures:
                description='访问受限，需复核（不据此认定失效）' if link['status']=='restricted' else str(link.get('reason') or link['status'])
                rows += ['  '+link['url']+'；'+description+'；HTTP '+str(link.get('httpStatus') or '无响应')]
    expiries=[r.get('certificateExpiresAt') for r in site if r.get('certificateExpiresAt')]
    if expiries:
        days=round((min(expiries)-sample['checkedAt'])/86400,1)
        rows+=['网站TLS证书剩余有效期：'+str(days)+'天'+('（少于14天，需核对续期）' if days<14 else '')]
    if links['omitted'] or links.get('pageBodyTruncated'):rows+=['覆盖不完整：有链接超出检查上限或页面读取上限，不能据此认定所有链接正常。']
    rows+=['检查范围：网站11个公开入口、配置中的主要官方信源及这些入口的外部链接；不遍历全部历史详情页。',
           'DNS、TLS、超时、重定向和HTTP错误按实际响应报告；访问受限与失效分开。',
           '网站：https://daily.maas.click/']
    return '\n'.join(rows)


def save_snapshot(directory, sample):
    fd,name=tempfile.mkstemp(prefix='.inspection-',dir=directory)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(sample,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,0o600);os.replace(name,directory/'inspection.json')
    finally:
        Path(name).unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser();modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check',action='store_true');modes.add_argument('--preview',action='store_true');modes.add_argument('--send',action='store_true')
    args=parser.parse_args();sample=inspect();text=report_text(sample)
    if args.preview:print(text);return
    if args.check:print(json.dumps(sample,ensure_ascii=False));return
    directory=ROOT/'state/data-alerts'
    with (directory/'watch.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        mailer=ResendMailer();store=AlertStore(directory)
        try:
            save_snapshot(directory,sample)
            queued=store.queue_report(sample,mailer.sender,mailer.recipient,text)
            result=store.deliver(mailer,time.time())
            print(json.dumps({'kind':'daily-inspection','reportDate':day(sample['checkedAt']),'checkedAt':local_time(sample['checkedAt']),'queued':queued,**result}))
            if result['failed'] or result['review']:raise SystemExit(1)
        finally:store.close()


if __name__=='__main__':main()
