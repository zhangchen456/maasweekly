"""Read-only, bounded host/service and public-link inspection. No credentials or bodies in results."""
import concurrent.futures
import http.client
from html.parser import HTMLParser
import ipaddress
import json
import os
import re
from pathlib import Path
import socket
import sqlite3
import ssl
import subprocess
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

GIB = 1024 ** 3
ORIGIN = 'https://daily.maas.click'
HTML_LIMIT = 8 * 1024 * 1024
# Stable public page that exposed the fact-query timeout; also works when
# landing pages render evidence links only after client-side data loading.
EVIDENCE_REGRESSION_PATH = '/evidence/ev_0000d9f560afd87baeac156c40e3e924206310917d1f27c372104b325259decd/'
PUBLIC_PATHS = ['/', '/en/', '/pricing/', '/en/pricing/', '/changes/', '/en/changes/', '/subscription/', '/en/subscription/', '/account/', '/api/v1/status', '/feed.xml']
RUNNING = ['nginx.service', 'docker.service', 'postgresql.service', 'maas-editorial-worker.service', 'maas-diagnostic-worker.service']
TIMERS = ['maas-daily-scheduler','maas-data-cache-cleanup','maas-pipeline-monitor', 'maas-daily-data-alert', 'maas-release-cleanup', 'maas-account-health', 'maas-account-backup', 'maas-account-digest', 'maas-account-digest-retry', 'maas-daily-inspection']
ONESHOTS = ['maas-daily-scheduler','maas-data-cache-cleanup','maas-release-cleanup', 'maas-account-health', 'maas-account-backup', 'maas-account-digest', 'maas-account-digest-retry', 'maas-daily-inspection']
PAUSED = ['maas-cloud-backup@daily.timer', 'maas-cloud-backup@history.timer', 'openlist.service']
SERVICE_LABELS = {'maas-daily-scheduler':'独立采集调度','maas-data-cache-cleanup':'重复数据缓存清理','nginx':'网站入口','docker':'数据采集容器','postgresql':'业务数据库',
    'maas-editorial-worker':'编辑任务服务','maas-diagnostic-worker':'辅助诊断服务',
    'maas-pipeline-monitor':'数据管线监控','maas-daily-data-alert':'异常监控与通知',
    'maas-release-cleanup':'发布包清理','maas-account-health':'账号运维检查',
    'maas-account-backup':'账号本地备份','maas-account-digest':'业务邮件汇总',
    'maas-account-digest-retry':'业务邮件重试','maas-daily-inspection':'每日综合巡检',
    'maas-cloud-backup@daily':'云盘每日备份','maas-cloud-backup@history':'云盘历史备份','openlist':'云盘连接服务'}


def service_label(unit):
    if unit.startswith('maas-agent@'):return '网站与API（当前槽位）'
    base=unit.removesuffix('.service').removesuffix('.timer')
    return SERVICE_LABELS.get(base,base)+('调度' if unit.endswith('.timer') else '')


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    # systemctl show can return nonzero for one missing unit while still returning the others.
    return result.stdout


def system_snapshot(shared, runtime=None, *, now=None, run=command, proc=Path('/proc')):
    now = time.time() if now is None else now
    result = {'checkedAt': now, 'resources': {}, 'services': [], 'issues': [], 'backup': {}}
    issues = set()
    try:
        stat = os.statvfs(shared)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = (stat.f_blocks - stat.f_bfree) * stat.f_frsize
        percent = round(100 * used / (used + free), 1)
        inode_percent = round(100 * (stat.f_files - stat.f_ffree) / stat.f_files, 1) if stat.f_files else None
        result['resources']['disk'] = dict(totalBytes=total, usedBytes=used, availableBytes=free, usedPercent=percent, inodeUsedPercent=inode_percent)
        if percent >= 80 or free < 8 * GIB or (inode_percent is not None and inode_percent >= 90):
            issues.add('disk_pressure')
        result['resources']['disk']['severity'] = 'critical' if percent >= 90 or free < 3 * GIB or (inode_percent or 0) >= 95 else 'warning' if 'disk_pressure' in issues else 'normal'
        memory = {}
        for line in (proc / 'meminfo').read_text().splitlines():
            key, value = line.split(':', 1)
            memory[key] = int(value.split()[0]) * 1024
        available = memory['MemAvailable']
        result['resources']['memory'] = dict(totalBytes=memory['MemTotal'], availableBytes=available, availablePercent=round(100 * available / memory['MemTotal'], 1), swapTotalBytes=memory.get('SwapTotal', 0), swapUsedBytes=memory.get('SwapTotal', 0)-memory.get('SwapFree', 0))
        if available / memory['MemTotal'] < .1:
            issues.add('memory_pressure')
        cores = os.cpu_count() or 1
        load = os.getloadavg()
        result['resources']['load'] = dict(cpuCount=cores, averages=list(load))
        if load[0] > cores * 2:
            issues.add('load_pressure')
    except (OSError, ValueError, KeyError, ZeroDivisionError):
        issues.add('resource_check_unavailable')
    units = RUNNING + [name+'.timer' for name in TIMERS] + [name+'.service' for name in ONESHOTS] + PAUSED
    slot = (runtime or {}).get('slot')
    if slot in ['blue', 'green']:
        units.append('maas-agent@'+slot+'.service')
    else:
        issues.add('service_unhealthy')
    try:
        raw = run(['systemctl', 'show', *units, '--property=Id,LoadState,ActiveState,SubState,Result,ExecMainStatus,ExecMainStartTimestamp,UnitFileState'])
        values = {}
        for block in raw.strip().split('\n\n'):
            row = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
            if row.get('Id'):
                values[row['Id']] = row
        for unit in units:
            row = values.get(unit, {})
            state = row.get('ActiveState', 'unknown')
            outcome = row.get('Result', 'unknown')
            if unit in PAUSED:
                ok = state == 'inactive'
                status = 'expected_paused' if ok else 'unexpected_or_unknown'
                if not ok:
                    issues.add('paused_jobs_changed')
            elif unit in [name+'.service' for name in ONESHOTS]:
                ok = row.get('LoadState') == 'loaded' and state in ['active', 'activating', 'inactive'] and outcome == 'success'
                status = 'running' if ok and state == 'activating' else 'normal' if ok else 'abnormal'
            else:
                ok = row.get('LoadState') == 'loaded' and state == 'active'
                if unit.endswith('.timer'):ok = ok and row.get('UnitFileState') in ['enabled','enabled-runtime']
                status = 'normal' if ok else 'abnormal'
            if not ok and unit not in PAUSED:
                issues.add('service_unhealthy')
            result['services'].append(dict(unit=unit, state=state, subState=row.get('SubState', 'unknown'), enabled=row.get('UnitFileState','unknown'), result=outcome, lastRun=row.get('ExecMainStartTimestamp') or None, status=status))
        probe = subprocess.run(['pg_isready', '-q', '-h', '/var/run/postgresql', '-d', 'maas_data', '-U', 'maasagent'], timeout=5, capture_output=True)
        result['databaseAcceptingConnections'] = probe.returncode == 0
        if probe.returncode:
            issues.add('service_unhealthy')
        size = run(['psql','-X','-At','-h','/var/run/postgresql','-U','maasagent','-d','maas_data','-c','SELECT pg_database_size(current_database())']).strip()
        result['databaseBytes'] = int(size) if size.isdigit() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        issues.add('service_check_unavailable')
    try:
        backups = list((Path(shared) / 'state/accounts/backups').glob('accounts-*.sqlite'))
        latest = max((p.stat().st_mtime for p in backups), default=None)
        age = now-latest if latest is not None else None
        result['backup'] = dict(retained=len(backups), latestAt=latest, ageSeconds=age, status='normal' if age is not None and 0 <= age <= 26*3600 else 'missing_or_stale')
        if result['backup']['status'] != 'normal':
            issues.add('backup_unhealthy')
    except OSError:
        result['backup'] = {'status': 'unknown'}
        issues.add('backup_unhealthy')
    try:
        account_db = Path(shared)/'state/accounts/accounts.sqlite'
        if not account_db.is_file() or account_db.is_symlink():raise ValueError('account database unavailable')
        db = sqlite3.connect(account_db.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)
        try:
            allowed={'pending','accepted','sent','delivered','failed','review','cancelled','suppressed','sending'}
            counts={}
            for status,count in db.execute('SELECT status,COUNT(*) FROM mail_jobs GROUP BY status'):
                key=status if status in allowed else 'other';counts[key]=counts.get(key,0)+count
            oldest=db.execute("SELECT MIN(created) FROM mail_jobs WHERE status='pending'").fetchone()[0]
            result['mail']={'counts':counts,'oldestPendingAgeSeconds':max(0,now-oldest/1000) if oldest is not None else None}
            if counts.get('review') or (oldest is not None and now-oldest/1000>3600):issues.add('mail_queue_unhealthy')
        finally:db.close()
    except (OSError,ValueError,sqlite3.Error):
        result['mail']={'status':'unknown'};issues.add('mail_queue_unhealthy')
    if (shared/'scheduler/enabled').exists():
        if not (shared/'scheduler/credentials.enc').is_file():issues.add('scheduler_unready')
    if (shared/'cache-retention').exists():
        try:
            cleanup=json.loads((shared/'cache-retention/current.json').read_text())
            if cleanup.get('status')!='completed' or not 0<=now-cleanup['checkedAt']<=26*3600:issues.add('cache_cleanup_stale')
            capacity=json.loads((shared/'cache-retention/capacity.json').read_text())
            result['nextUpdateCapacity']={k:capacity[k] for k in ['checkedAt','requiredFreeBytes','estimatedPeakBytes','reserveBytes']}
            if not 0<=now-capacity['checkedAt']<=26*3600:issues.add('cache_cleanup_stale')
            elif result['resources']['disk']['availableBytes']<capacity['requiredFreeBytes']:issues.add('capacity_headroom')
        except (OSError,ValueError,KeyError,TypeError):issues.add('cache_cleanup_stale')
    result['issues'] = sorted(issues)
    return result


def display_url(url):
    try:
        value = urlsplit(url)
        return urlunsplit((value.scheme, value.hostname or '', value.path or '/', '', ''))
    except ValueError:return '[invalid URL]'


def public_addresses(host):
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('non_public_address')
    # Pin the checked address for the actual TCP connection; no second DNS lookup or proxy.
    return sorted({(row[0], row[4][0]) for row in addresses}, key=lambda row: row[0] != socket.AF_INET)


class PublicProbe:
    def exchange(self, url, deadline, body_limit):
        value = urlsplit(url)
        if len(url)>4096 or value.scheme != 'https' or not value.hostname or value.username or value.password or value.port not in [None, 443] or any(c in url for c in '\r\n\0'):
            raise ValueError('unsupported_url')
        connection = None
        last_error = None
        for _, address in public_addresses(value.hostname)[:4]:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            try:
                sock = socket.create_connection((address, 443), timeout=min(5, remaining))
                try:
                    secure = ssl.create_default_context().wrap_socket(sock, server_hostname=value.hostname)
                except BaseException:
                    sock.close()
                    raise
                connection = http.client.HTTPSConnection(value.hostname, timeout=min(5, remaining))
                connection.sock = secure
                secure.settimeout(min(5, max(.1, deadline-time.monotonic())))
                expiry = secure.getpeercert().get('notAfter')
                connection.request('GET', urlunsplit(('', '', value.path or '/', value.query, '')), headers={'User-Agent': 'MaaSDaily-operations-inspection/1.0', 'Accept-Encoding': 'identity'})
                response = connection.getresponse()
                chunks=[];remaining_bytes=body_limit
                while remaining_bytes:
                    remaining_time=deadline-time.monotonic()
                    if remaining_time<=0:raise TimeoutError()
                    secure.settimeout(min(5,remaining_time))
                    chunk=response.read1(min(16384,remaining_bytes))
                    if not chunk:break
                    chunks.append(chunk);remaining_bytes-=len(chunk)
                return response.status, response.getheader('Location'), b''.join(chunks), ssl.cert_time_to_seconds(expiry) if expiry else None
            except (OSError, http.client.HTTPException) as error:
                last_error = error
            finally:
                if connection:
                    connection.close()
        if last_error:
            raise last_error
        raise OSError('connection_unavailable')

    def check(self, url, *, include_body=False):
        started = time.monotonic()
        result = {'url': display_url(url), 'status': 'unknown', 'httpStatus': None}
        current = url
        try:
            for hop in range(6):
                status, location, body, expiry = self.exchange(current, started+18, HTML_LIMIT if include_body else 4096)
                if status in [301, 302, 303, 307, 308] and location:
                    current = urljoin(current, location)
                    continue
                result.update(httpStatus=status, finalUrl=display_url(current), redirects=hop, certificateExpiresAt=expiry)
                result['status'] = 'ok' if 200 <= status < 300 else 'restricted' if status in [401, 403, 429] else 'http_error'
                if include_body and result['status'] == 'ok':
                    result['body'] = body.decode('utf-8', errors='replace')
                    result['bodyTruncated'] = len(body) == HTML_LIMIT
                break
            else:
                result.update(status='redirect_error', reason='too_many_redirects')
        except socket.gaierror:
            result.update(status='network_error', reason='dns_error')
        except ssl.SSLError:
            result.update(status='network_error', reason='tls_error')
        except (TimeoutError, socket.timeout):
            result.update(status='network_error', reason='timeout')
        except (OSError, http.client.HTTPException):
            result.update(status='network_error', reason='connection_error')
        except ValueError:
            result.update(status='uncheckable', reason='unsafe_or_unsupported_url')
        result['elapsedSeconds'] = round(time.monotonic()-started, 3)
        return result


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = set(); self.details = set()
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href.startswith(('https://', 'http://')):
                self.links.add(href.split('#', 1)[0])
            # Sample only canonical public detail routes discovered on the site.
            # Never forward queries, credentials or arbitrary internal links.
            if re.fullmatch(r'/(?:item/(?:obs|price)_|evidence/ev_)[0-9a-f]{64}/', href):
                self.details.add(href)


def inspect_links(registry_file, *, probe=None, limit=300, registry=None):
    probe = probe or PublicProbe()
    targets = set()
    registry = json.loads(Path(registry_file).read_text()) if registry is None else registry
    for source in registry['sources']:
        targets.add(source['primary_url'])
    site = []; details = set()
    for path in PUBLIC_PATHS:
        row = probe.check(ORIGIN+path, include_body=path != '/feed.xml')
        body = row.pop('body', '')
        if body:
            parser = Anchors(); parser.feed(body)
            details.update(parser.details)
            for url in parser.links:
                try:external_host=urlsplit(url).hostname != urlsplit(ORIGIN).hostname
                except ValueError:external_host=True
                if external_host:targets.add(url)
        site.append(row)
    missing = []
    for prefix in ['/item/', '/evidence/']:
        candidates = sorted(path for path in details if path.startswith(prefix))
        if not candidates and prefix == '/evidence/':
            candidates = [EVIDENCE_REGRESSION_PATH]
        if candidates:
            row = probe.check(ORIGIN+candidates[0])
            row['detailSample'] = True
            site.append(row)
        else:
            missing.append(prefix)
    ordered = sorted(targets)
    # Registry entries are checked first; excess coverage is reported, never silently marked healthy.
    primary = {source['primary_url'] for source in registry['sources']}
    ordered.sort(key=lambda url: (url not in primary, url))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        external = list(executor.map(probe.check, ordered[:limit]))
    return {'checkedAt': time.time(), 'site': site, 'external': external, 'discovered': len(ordered), 'checked': len(external), 'omitted': max(0, len(ordered)-limit), 'detailSamplesMissing': missing, 'pageBodyTruncated': any(row.get('bodyTruncated') for row in site), 'scope': '11 public entrypoints, up to one record and one evidence detail sample, configured primary source URLs and outbound anchors; other historical details are not crawled.'}
