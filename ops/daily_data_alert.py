#!/usr/bin/env python3
"""Independent daily-update watchdog: fixed metadata inputs, durable incidents and mail."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from operations_checks import system_snapshot
from reliability_observation import initialize as observation_initialize, observe as record_observation

ZONE = ZoneInfo('Asia/Shanghai')
ROOT = Path('/srv/maasweekly/shared')
GITHUB = 'https://api.github.com/repos/zhangchen456/maasweekly/actions/workflows/daily-update.yml/runs?branch=main&per_page=5'
ORIGIN = 'https://daily.maas.click'
FAILURES = {'failure', 'timed_out', 'cancelled', 'action_required', 'startup_failure', 'stale'}
DEADLINE_HOUR = 13
LABELS = {
 'weekly_overdue': '本期正式周报超过周四交付时间或期号无效',
 'delivery_unverified': '实际页面或周报中英文交付未通过验收',
 'scheduler_unready': '独立采集调度未就绪',
 'cache_cleanup_stale': '重复缓存清理长期未完成',
 'capacity_headroom': '下一轮更新容量余量不足',
 'workflow_failed': '每日更新工作流失败或被取消',
 'task_failed': '服务器上的每日采集任务失败',
 'task_interrupted': '采集进程已退出但没有完成回执',
 'task_timeout': '每日更新任务运行超时',
 'publication_late': '已超过13:00，尚未确认当天数据发布',
 'runtime_unavailable': '未能读取线上服务或公网数据状态',
 'runtime_mismatch': '服务加载的数据与正式发布版本不一致',
 'sources_degraded': '部分内容或报价来源更新状态需要核对',
 'monitor_input_unavailable': '未能读取每日任务监控记录',
 'github_check_unavailable': '连续未能核对GitHub任务状态',
 'disk_pressure': '磁盘空间或inode余量偏低',
 'memory_pressure': '可用内存持续低于10%',
 'load_pressure': '系统负载持续高于CPU数量的2倍',
 'resource_check_unavailable': '未能完整读取服务器资源状态',
 'service_unhealthy': '核心服务或定时任务异常',
 'service_check_unavailable': '未能完整核对核心服务状态',
 'paused_jobs_changed': '预期暂停的云盘任务状态发生变化或无法确认',
 'backup_unhealthy': '账号本地备份缺失、超过26小时或无法读取',
 'inspection_stale': '每日巡检超过26小时未完成或缺少有效记录',
 'mail_queue_unhealthy': '邮件队列需人工核对、积压超过1小时或无法读取',
}
IMMEDIATE = {'workflow_failed', 'task_failed', 'task_interrupted', 'task_timeout', 'publication_late'}


def local_time(epoch):
    return datetime.fromtimestamp(epoch, ZONE).strftime('%Y-%m-%d %H:%M:%S') + ' (Asia/Shanghai)'


def day(epoch):
    return datetime.fromtimestamp(epoch, ZONE).date().isoformat()


def valid_day(value):
    try:
        return isinstance(value, str) and datetime.strptime(value, '%Y-%m-%d').strftime('%Y-%m-%d') == value
    except ValueError:
        return False


def read_json(path, limit=1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        import stat
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_size > limit:
            raise ValueError('invalid metadata file')
        with os.fdopen(os.dup(fd), 'rb') as f:
            body = f.read(limit+1)
        if len(body) > limit:
            raise ValueError('metadata too large')
        return json.loads(body)
    finally:
        os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Transport:
    def __init__(self):
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, url, *, headers=None, body=None, timeout=8, limit=1024*1024):
        req = urllib.request.Request(url, data=body, headers={'User-Agent': 'MaaSDaily-daily-watchdog/1.0', **(headers or {})})
        with self.opener.open(req, timeout=timeout) as response:
            raw = response.read(limit+1)
            if len(raw) > limit:
                raise ValueError('response too large')
            return json.loads(raw)


def alive(job):
    try:
        pid = job['pid']
        if type(pid) is not int or pid <= 1 or not re.fullmatch(r'\d+', job['processStart']):
            return False
        actual = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
        return actual == job['processStart']
    except (OSError, KeyError, TypeError):
        return False


def validate_job(job):
    if (not isinstance(job, dict) or job.get('schemaVersion') != 1 or not isinstance(job.get('id'), str)
            or not re.fullmatch(r'pipeline_[a-f0-9]{32}', job['id'])
            or job.get('state') not in ['running', 'succeeded', 'failed']
            or any(type(job.get(k)) is not int for k in ['startedAt', 'updatedAt'])
            or not re.fullmatch(r'[-a-z]{1,64}', job.get('stage', ''))
            or (job.get('failureStage') is not None and not re.fullmatch(r'[-a-z]{1,64}',job['failureStage']))):
        raise ValueError('invalid job metadata')
    return job


def collect(now, transport=None, shared=ROOT):
    transport = transport or Transport()
    sample = {'checkedAt': now, 'today': day(now), 'dataThrough': None, 'consistent': False,
              'sourcesHealthy': False, 'githubKnown': False, 'github': None,
              'daily': None, 'current': None, 'jobAlive': False, 'inputError': False,
              'runtimeError': False, 'githubError': False}
    runtime_for_ops = {}
    try:
        current = validate_job(read_json(shared/'pipeline-monitor/current.json', 65536))
        sample['current'] = {k: current.get(k) for k in ['id','state','mode','stage','startedAt','updatedAt','failureStage','runLink','trigger']}
        daily_path = shared/'pipeline-monitor/daily.json'
        daily = validate_job(read_json(daily_path, 65536)) if daily_path.exists() else current
        if daily.get('mode') != 'update':
            raise ValueError('daily receipt unavailable')
        sample['daily'] = {k: daily.get(k) for k in ['id','state','mode','stage','startedAt','updatedAt','failureStage','runLink','trigger']}
        sample['jobAlive'] = alive(daily) if daily['state'] == 'running' else False
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        sample['inputError'] = True
    try:
        runtime = read_json(shared/'runtime.json', 65536)
        runtime_for_ops = runtime
        publication = read_json(shared/'public-data/v1/publication.json')
        if type(runtime.get('port')) is not int or not 1024 <= runtime['port'] <= 65535:
            raise ValueError('invalid port')
        expected = {k: publication['site'][k] for k in ['inputVersion','codeCommit','formatVersion']}
        expected['datasetVersion'] = publication['datasetVersion']
        health = transport.request(f"http://127.0.0.1:{runtime['port']}/_runtime/health", timeout=5)
        public = transport.request(ORIGIN+'/api/v1/status', timeout=8)
        date = public.get('dataThrough')
        if not valid_day(date):
            raise ValueError('invalid published date')
        sample['dataThrough'] = date
        sample['formalWeekly']=publication.get('coverage',{}).get('weekly',{}).get('latestId')
        status = public.get('status', {})
        sample['sources'] = {}
        for name in ['sourceStreams', 'priceStreams']:
            rows = status.get(name, [])
            sample['sources'][name] = {'total': len(rows), 'ok': sum(row.get('state') == 'ok' for row in rows),
                'problems': [{k: row.get(k) for k in ['sourceId', 'sourceKey', 'state', 'lastSuccessDate', 'lastSuccessAt']} for row in rows if row.get('state') != 'ok']}
        sample['consistent'] = bool(health.get('ready') and not health.get('lastReloadError')
            and health.get('processCode') == runtime['code'] and health.get('publication') == expected
            and health.get('dataThrough') == date and public.get('datasetVersion') == expected['datasetVersion'])
        sample['sourcesHealthy'] = health.get('freshness', {}).get('freshness') == 'fresh'
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        sample['runtimeError'] = True
    sample['operations'] = system_snapshot(shared, runtime_for_ops, now=now)
    inspection = shared/'state/data-alerts/inspection.json'
    try:
        inspected=read_json(inspection);checked = inspected['checkedAt']
        if inspected.get('delivery',{}).get('status')!='passed':sample['operations']['issues'].append('delivery_unverified')
        if any(x.get('status')!='ok' for x in inspected.get('links',{}).get('site',[])):sample['operations']['issues'].append('delivery_unverified')
        if not isinstance(checked, (int, float)) or checked > now+60 or now-checked > 26*3600:
            raise ValueError('inspection stale')
    except (OSError, ValueError, KeyError, TypeError):
        local = datetime.fromtimestamp(now, ZONE)
        if (local.hour, local.minute) >= (13, 45):
            sample['operations']['issues'].append('inspection_stale')
    try:
        runs = transport.request(GITHUB, headers={'Accept':'application/vnd.github+json'}, timeout=8)['workflow_runs']
        if not isinstance(runs, list) or not runs:
            raise ValueError('workflow records unavailable')
        run = runs[0]
        if type(run.get('id')) is not int or run['id'] <= 0 or run.get('status') not in ['queued','in_progress','completed','waiting','requested','pending']:
            raise ValueError('invalid workflow metadata')
        created = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00')).timestamp()
        updated = datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00')).timestamp()
        sample['github'] = {'id': run['id'], 'status':run['status'], 'conclusion':run.get('conclusion'), 'createdAt':created, 'updatedAt':updated,
                            'event': run.get('event') if run.get('event') in ['schedule', 'workflow_dispatch'] else 'other'}
        sample['githubKnown'] = True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        sample['githubError'] = True
    return sample


def conditions(sample, deadline_hour=DEADLINE_HOUR):
    now = sample['checkedAt'];today = day(now);local = datetime.fromtimestamp(now, ZONE)
    baseline = today if local.hour >= deadline_hour else (local.date()-timedelta(days=1)).isoformat()
    issues = {};daily=sample.get('daily');current=sample.get('current');gh=sample.get('github')
    if 'formalWeekly' in sample:
        since_tuesday=(local.weekday()-1)%7
        due=local.date()-timedelta(days=since_tuesday or 7)
        after_deadline=since_tuesday>2 or (since_tuesday==2 and local.hour>=12)
        latest=sample['formalWeekly']
        if not valid_day(latest) or latest>today or (after_deadline and latest<str(due)):
            issues['weekly_overdue']=today
    for reason in sample.get('operations', {}).get('issues', []):
        if reason in LABELS: issues[reason] = baseline
    if sample.get('inputError'):
        issues['monitor_input_unavailable'] = baseline
    if sample.get('runtimeError'):
        issues['runtime_unavailable'] = baseline
    elif not sample.get('consistent') or (sample.get('dataThrough') or '') > today:
        issues['runtime_mismatch'] = baseline
    elif not sample.get('sourcesHealthy'):
        issues['sources_degraded'] = baseline
    date = sample.get('dataThrough')
    if local.hour >= deadline_hour and (not valid_day(date) or date < today):
        issues['publication_late'] = today
    local_delivery=bool(daily and daily.get('trigger')=='schedule' and daily.get('state')=='succeeded' and sample.get('consistent') and sample.get('sourcesHealthy') and date==today and day(daily['updatedAt']/1000)==today)
    if sample.get('githubError') and not local_delivery:
        issues['github_check_unavailable'] = baseline
    recovered_publish = bool(current and current['state']=='succeeded' and sample.get('consistent')
        and date == today and daily and current['updatedAt'] > daily['updatedAt'])
    if daily:
        target = day(daily['startedAt']/1000)
        if daily['state']=='failed' and not recovered_publish:
            issues['task_failed'] = target
        if daily['state']=='running':
            if not sample.get('jobAlive'):
                issues['task_interrupted'] = target
            elif now-daily['startedAt']/1000 > 100*60:
                issues['task_timeout'] = target
    if gh:
        # A later verified server publication supersedes an old workflow failure.
        newer_success = bool(current and current['state']=='succeeded' and current['updatedAt']/1000 > gh['updatedAt']
                             and sample.get('consistent') and date == today)
        if gh['status']=='completed' and gh['conclusion'] in FAILURES and not newer_success:
            issues['workflow_failed'] = day(gh['createdAt'])
        elif not newer_success and gh['status']!='completed' and now-gh['createdAt'] > 110*60:
            issues['task_timeout'] = day(gh['createdAt'])
    return issues


class MailFailure(Exception):
    def __init__(self, code, uncertain):
        self.code, self.uncertain = code, uncertain
        super().__init__(code)


class ResendMailer:
    def __init__(self, env=None, transport=None):
        env = os.environ if env is None else env
        self.key=env.get('RESEND_API_KEY','');self.sender=env.get('MAAS_MAIL_FROM','');self.recipient=env.get('MAAS_DATA_ALERT_TO','')
        if not self.key or not self.sender or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.recipient) or any(c in self.sender+self.recipient for c in '\r\n\0'):
            raise ValueError('operator mail configuration required')
        self.transport=transport or Transport()

    def send(self, key, mail):
        try:
            result=self.transport.request('https://api.resend.com/emails',headers={'Authorization':'Bearer '+self.key,
                'Content-Type':'application/json','Idempotency-Key':key},body=json.dumps(mail,ensure_ascii=False).encode(),timeout=15)
            if not isinstance(result.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',result['id']):
                raise MailFailure('invalid_acceptance',True)
            return result['id']
        except urllib.error.HTTPError as error:
            raise MailFailure('provider_rejected',error.code not in [400,401,403,409,422,429]) from None
        except MailFailure:
            raise
        except Exception:
            raise MailFailure('timeout_or_unknown',True) from None


class AlertStore:
    def __init__(self, directory):
        directory=Path(directory)
        if directory.is_symlink() or directory.resolve()!=directory:
            raise ValueError('unsafe alert state directory')
        directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        file=directory/'alerts.sqlite'
        if file.is_symlink():raise ValueError('unsafe alert state file')
        self.db=sqlite3.connect(file);self.db.row_factory=sqlite3.Row
        self.db.executescript('''CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,episode TEXT NOT NULL,kind TEXT NOT NULL,created REAL NOT NULL,
        payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
        firstAttempt REAL,messageId TEXT,error TEXT,uncertain INTEGER NOT NULL DEFAULT 0);
        ''');self.db.commit();os.chmod(file,0o600)
        observation_initialize(self.db)
        self.db.execute('CREATE TABLE IF NOT EXISTS reports(day TEXT NOT NULL,destination TEXT NOT NULL,job TEXT NOT NULL,PRIMARY KEY(day,destination))');self.db.commit()

    def close(self):self.db.close()

    def load(self):
        row=self.db.execute('SELECT payload FROM state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {'counts':{},'episode':None,'checkedAt':None}

    def queue(self, episode, kind, reasons, sample, sender, recipient, *, rehearsal=False):
        identifier='ops_'+uuid.uuid4().hex;now=sample['checkedAt'];recovery=kind=='recovery'
        operational=bool((set(episode.get('seen',[]))|set(reasons)) - {'workflow_failed','task_failed','task_interrupted','task_timeout','publication_late','runtime_unavailable','runtime_mismatch','sources_degraded','monitor_input_unavailable','github_check_unavailable'})
        title=('运行状态已恢复' if recovery else '运行巡检异常' if kind=='alert' else '运行巡检异常状态更新') if operational else ('每日数据更新已恢复' if recovery else '每日数据更新异常' if kind=='alert' else '每日数据更新异常状态更新')
        subject='[MaaSDaily] '+('[演练] ' if rehearsal else '')+title
        rows=[('本邮件为告警链路验收演练，未修改真实任务或发布数据。' if rehearsal else '运行与数据更新自动监控通知。'),
              '发现时间：'+local_time(episode['openedAt']), '本次检查：'+local_time(now),
              '需要确认的数据日期：'+episode['targetDate'], '当前公网数据截至：'+(sample.get('dataThrough') or '暂无法读取，尚未验证')]
        if recovery:rows+=['已确认：服务和正式数据版本一致，异常条件已连续两次检查消失。','需要处理：目前无需操作。']
        else:
            rows+=['问题：'+'；'.join(LABELS[r] for r in sorted(reasons)),'影响：服务、资源或数据交付状态需要核对；尚未验证的状态不会作为恢复成功。']
            job=sample.get('daily')
            if job:rows+=['最近每日任务开始时间：'+local_time(job['startedAt']/1000),
                          '最近每日任务状态：'+job['state']+'；阶段：'+str(job.get('failureStage') or job['stage'])]
            ops=sample.get('operations', {})
            disk=ops.get('resources', {}).get('disk')
            if disk:rows+=['磁盘：已用 '+str(disk['usedPercent'])+'%，可用 '+str(round(disk['availableBytes']/1024**3,2))+' GiB']
            memory=ops.get('resources',{}).get('memory')
            if memory:rows+=['可用内存：'+str(memory['availablePercent'])+'%']
            load=ops.get('resources',{}).get('load')
            if load:rows+=['负载（1/5/15分钟）：'+', '.join(str(round(x,2)) for x in load['averages'])+'；CPU数量：'+str(load['cpuCount'])]
            bad=[r['unit'] for r in ops.get('services',[]) if r['status'] not in ['normal','running','expected_paused']]
            if bad:rows+=['异常服务：'+', '.join(bad)]
            rows+=['已采取措施：已记录异常，并继续每5分钟复查。','需要处理：请核对上述异常项；任务异常时查看任务记录与失败阶段。恢复确认后会发送恢复通知。']
        if sample.get('github'):rows+=['任务记录：https://github.com/zhangchen456/maasweekly/actions/runs/'+str(sample['github']['id'])]
        rows+=['网站：'+ORIGIN+'/']
        mail={'from':sender,'to':[recipient],'subject':subject,'text':'\n\n'.join(rows)}
        self.db.execute('INSERT INTO jobs(id,episode,kind,created,payload) VALUES(?,?,?,?,?)',
                        [identifier,episode['id'],kind,now,json.dumps(mail,ensure_ascii=False,sort_keys=True)])
        return identifier

    def queue_report(self, sample, sender, recipient, text):
        report_day=day(sample['checkedAt']);destination=hashlib.sha256((sender+'\0'+recipient).encode()).hexdigest()
        identifier='ops_'+uuid.uuid4().hex
        with self.db:
            cursor=self.db.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?)',[report_day,destination,identifier])
            if not cursor.rowcount:return 0
            mail={'from':sender,'to':[recipient],'subject':'[MaaSDaily] 每日巡检 '+report_day,'text':text}
            self.db.execute('INSERT INTO jobs(id,episode,kind,created,payload) VALUES(?,?,?,?,?)',
                [identifier,'report_'+report_day+'_'+destination[:16],'inspection',sample['checkedAt'],json.dumps(mail,ensure_ascii=False,sort_keys=True)])
        return 1

    def observe(self, sample, sender, recipient, *, rehearsal=False, deadline_hour=DEADLINE_HOUR):
        raw=conditions(sample,deadline_hour);state=self.load();destination=hashlib.sha256((sender+'\0'+recipient).encode()).hexdigest();counts={r:state['counts'].get(r,0)+1 for r in raw}
        confirmed={r:target for r,target in raw.items() if counts[r]>=(1 if r in IMMEDIATE else 3 if r=='github_check_unavailable' else 2)}
        episode=state['episode'];queued=0
        with self.db:
            if not rehearsal:record_observation(self.db,sample,confirmed)
            if state.get('destination') and state['destination']!=destination:
                self.db.execute("UPDATE jobs SET status='cancelled' WHERE status='pending'")
                if episode:episode['seen']=[]
            if confirmed:
                self.db.execute("UPDATE jobs SET status='cancelled' WHERE kind='recovery' AND status='pending'")
                if not episode:
                    episode={'id':uuid.uuid4().hex,'openedAt':sample['checkedAt'],'targetDate':max(confirmed.values()),'seen':[],'healthy':0}
                    kind='alert'
                else:kind='escalation'
                episode['healthy']=0;episode['targetDate']=max(episode['targetDate'],max(confirmed.values()))
                new=set(confirmed)-set(episode['seen'])
                if new:
                    self.queue(episode,kind,confirmed,sample,sender,recipient,rehearsal=rehearsal);queued+=1
                    episode['seen']=sorted(set(episode['seen'])|set(confirmed))
            elif episode:
                recovered=bool(not raw and sample.get('consistent') and sample.get('sourcesHealthy') and (sample.get('githubKnown') or (sample.get('daily') or {}).get('trigger')=='schedule')
                               and (sample.get('dataThrough') or '')>=episode['targetDate'])
                episode['healthy']=episode.get('healthy',0)+1 if recovered else 0
                if recovered and set(episode['seen']) & {'workflow_failed','task_failed','task_interrupted','task_timeout'}:
                    current=sample.get('current');gh=sample.get('github')
                    terminal=bool(current and current['state']=='succeeded' and current['updatedAt']/1000>=episode['openedAt']) or bool(gh and gh['status']=='completed' and gh['conclusion']=='success' and gh['updatedAt']>=episode['openedAt'])
                    if not terminal:episode['healthy']=0
                if episode['healthy']>=2:
                    informed=self.db.execute("SELECT 1 FROM jobs WHERE episode=? AND (status='accepted' OR uncertain=1)",[episode['id']]).fetchone()
                    self.db.execute("UPDATE jobs SET status='cancelled' WHERE episode=? AND status='pending'",[episode['id']])
                    if informed:self.queue(episode,'recovery',[],sample,sender,recipient,rehearsal=rehearsal);queued+=1
                    episode=None
            state={'counts':counts,'episode':episode,'checkedAt':sample['checkedAt'],'sample':sample,'destination':destination}
            self.db.execute('INSERT INTO state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',[json.dumps(state,ensure_ascii=False)])
        return {'alerts':sorted(confirmed),'episodeOpen':bool(episode),'queued':queued}

    def deliver(self, mailer, now):
        sent=failed=review=0
        for job in self.db.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY created,id LIMIT 2").fetchall():
            if job['uncertain'] and job['firstAttempt'] is not None and now-job['firstAttempt']>=23*3600:
                with self.db:self.db.execute("UPDATE jobs SET status='review',error='idempotency_window_expiring' WHERE id=?",[job['id']])
                continue
            with self.db:self.db.execute('UPDATE jobs SET attempts=attempts+1,firstAttempt=COALESCE(firstAttempt,?),uncertain=1 WHERE id=?',[now,job['id']])
            try:
                message=mailer.send(job['id'],json.loads(job['payload']))
                with self.db:self.db.execute("UPDATE jobs SET status='accepted',messageId=?,error=NULL,uncertain=0 WHERE id=?",[message,job['id']])
                sent+=1
            except MailFailure as error:
                with self.db:self.db.execute('UPDATE jobs SET error=?,uncertain=? WHERE id=?',[error.code,int(bool(job['uncertain']) or error.uncertain),job['id']])
                failed+=1
        review+=self.db.execute("SELECT count(*) FROM jobs WHERE status='review'").fetchone()[0]
        return {'accepted':sent,'failed':failed,'review':review}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    now=time.time();sample=collect(now)
    if args.check:
        print(json.dumps({'checkedAt':local_time(now),'dataThrough':sample['dataThrough'],'alerts':sorted(conditions(sample))}));return
    directory=ROOT/'state/data-alerts';directory.mkdir(mode=0o700,exist_ok=True)
    with (directory/'watch.lock').open('a+b') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print(json.dumps({'status':'deferred'}));return
        mailer=ResendMailer();store=AlertStore(directory)
        try:
            result=store.observe(sample,mailer.sender,mailer.recipient);result.update(store.deliver(mailer,now))
            print(json.dumps({'kind':'daily-data-alert','checkedAt':local_time(now),'dataThrough':sample['dataThrough'],**result}))
            if result['alerts'] or result['failed'] or result['review']:raise SystemExit(1)
        finally:store.close()


if __name__=='__main__':main()
