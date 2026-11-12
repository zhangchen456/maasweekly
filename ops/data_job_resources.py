"""Fixed collection budgets and fail-closed host headroom checks. No request overrides."""
import argparse,json,os,re,signal,stat,subprocess,time
from pathlib import Path
from pipeline_monitor import write_json

MIB=1024**2
RESERVE=512*MIB
MIN_WRITER=1024*MIB
MAX_WRITER=1536*MIB
IO_BPS=16*MIB
POLL_SECONDS=2
LOW_SAMPLES=2
JOB_SECONDS=90*60

class ResourcePressure(RuntimeError):pass
class JobInterrupted(RuntimeError):pass

def host_memory(path=Path('/proc/meminfo')):
    values={k:int(v.strip().split()[0])*1024 for k,v in (line.split(':',1) for line in path.read_text().splitlines())}
    available,total=values['MemAvailable'],values['MemTotal']
    if not 0<=available<=total:raise ValueError('invalid host memory sample')
    return {'availableBytes':available,'totalBytes':total}

def disk_device(shared,sysfs=Path('/sys'),devfs=Path('/dev')):
    """Resolve a local filesystem partition to its whole block device for io.max."""
    device=os.stat(shared).st_dev
    node=(sysfs/'dev/block'/f'{os.major(device)}:{os.minor(device)}').resolve(strict=True)
    if (node/'partition').exists():node=node.parent
    if list((node/'slaves').iterdir()):raise ValueError('layered data devices require an explicit reviewed I/O policy')
    major,minor=map(int,(node/'dev').read_text().strip().split(':'))
    target=devfs/node.name;info=target.stat()
    if not stat.S_ISBLK(info.st_mode) or info.st_rdev!=os.makedev(major,minor):raise ValueError('data block device mismatch')
    return str(target),f'{major}:{minor}'

def terminate_group(process):
    if process.poll() is not None:return
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait(timeout=5)

class DataJobResources:
    def __init__(self,root,job_id,gid=None,*,sample=host_memory,clock=time.monotonic,wall=time.time):
        if not re.fullmatch(r'pipeline_[a-f0-9]{32}',job_id):raise ValueError('invalid resource job id')
        self.root=Path(root);self.job_id=job_id;self.gid=gid;self.sample=sample;self.clock=clock;self.wall=wall
        self.deadline=clock()+JOB_SECONDS;self.low=0;self.last_saved=0;self.container=None;self.cgroup=None
        self.state={'schemaVersion':1,'jobId':job_id,'startedAt':wall(),'status':'running','minimumHostAvailableBytes':None,
                    'policy':{'hostReserveBytes':RESERVE,'writerMemoryMaximumBytes':MAX_WRITER,'writerMemoryMinimumBytes':MIN_WRITER,
                              'containerSwapBytes':0,'readBytesPerSecond':IO_BPS,'writeBytesPerSecond':IO_BPS,
                              'sampleSeconds':POLL_SECONDS,'consecutiveLowSamples':LOW_SAMPLES,'deadlineSeconds':JOB_SECONDS},'containers':[]}
        self.directory=self.root/'shared/pipeline-resources'
        self.device,self.device_id=disk_device(self.root/'shared')
        controllers=Path('/sys/fs/cgroup/cgroup.controllers').read_text().split()
        if not {'io','memory'}.issubset(controllers):raise ValueError('required cgroup v2 controllers unavailable')

    def record(self,force=False):
        if force or self.clock()-self.last_saved>=15:
            self.state['checkedAt']=self.wall()
            write_json(self.directory/(self.job_id+'.json'),self.state,self.gid)
            write_json(self.directory/'current.json',self.state,self.gid);self.last_saved=self.clock()

    def check(self):
        if self.clock()>=self.deadline:
            self.state['reason']='job_deadline';self.record(True);raise ResourcePressure('job_deadline')
        try:value=self.sample()
        except Exception:
            self.state['reason']='host_resource_measurement_failed';self.record(True)
            raise ResourcePressure('host_resource_measurement_failed') from None
        available=value['availableBytes'];self.state['hostAvailableBytes']=available
        minimum=self.state['minimumHostAvailableBytes'];self.state['minimumHostAvailableBytes']=available if minimum is None else min(minimum,available)
        self.low=self.low+1 if available<RESERVE else 0
        if self.low>=LOW_SAMPLES:
            self.state['reason']='host_memory_headroom';self.record(True);raise ResourcePressure('host_memory_headroom')
        if self.container:self.inspect_container()
        self.record();return value

    def admit(self):
        value=self.check()
        if value['availableBytes']<MIN_WRITER+RESERVE:
            self.state['reason']='insufficient_starting_memory';self.record(True);raise ResourcePressure('insufficient_starting_memory')
        self.record(True);return {'kind':'resource.admission','availableBytes':value['availableBytes'],'requiredBytes':MIN_WRITER+RESERVE}

    def container_arguments(self,mode):
        value=self.check();minimum=256*MIB if mode=='publish' else MIN_WRITER
        maximum=512*MIB if mode=='publish' else MAX_WRITER
        budget=min(maximum,(value['availableBytes']-RESERVE)//(64*MIB)*(64*MIB))
        if budget<minimum:
            self.state['reason']='insufficient_container_memory';self.record(True);raise ResourcePressure('insufficient_container_memory')
        token=f'{mode}-{time.time_ns()}'
        cidfile=self.directory/(self.job_id+'-'+token+'.cid')
        self.record(True)
        self.container={'mode':mode,'cidfile':str(cidfile),'memoryLimitBytes':budget,'verified':False,'startedAt':self.wall()}
        self.cgroup=None;self.state['containers'].append(self.container)
        return ['--cidfile',str(cidfile),'--label','maas.pipeline.job='+self.job_id,
                '--memory',str(budget),'--memory-swap',str(budget),
                '--device-read-bps',self.device+':'+str(IO_BPS),'--device-write-bps',self.device+':'+str(IO_BPS)]

    def inspect_container(self):
        current=self.container;path=Path(current['cidfile'])
        if not path.exists():return
        if path.is_symlink():raise ResourcePressure('unsafe_container_identity')
        cid=path.read_text().strip()
        if not re.fullmatch('[a-f0-9]{64}',cid):raise ResourcePressure('invalid_container_identity')
        current['id']=cid
        if self.cgroup is None:
            result=subprocess.run(['docker','inspect','--format','{{.State.Pid}}',cid],capture_output=True,text=True,timeout=3)
            if result.returncode:return  # --rm may have completed between polls.
            pid=int(result.stdout.strip())
            if pid<=1:return
            try:relative=Path(f'/proc/{pid}/cgroup').read_text().strip().split('::')[-1].lstrip('/')
            except FileNotFoundError:return
            cgroup=Path('/sys/fs/cgroup')/relative
            if cgroup.resolve()!=cgroup or 'docker-'+cid not in str(cgroup):raise ResourcePressure('unexpected_writer_cgroup')
            self.cgroup=cgroup
        if not self.cgroup.exists():return
        try:
            memory=int((self.cgroup/'memory.max').read_text());swap=int((self.cgroup/'memory.swap.max').read_text())
            lines=[line.split() for line in (self.cgroup/'io.max').read_text().splitlines()]
            io=next((dict(part.split('=',1) for part in row[1:]) for row in lines if row[0]==self.device_id),{})
            if memory!=current['memoryLimitBytes'] or swap!=0 or any(io.get(key)=='max' or int(io.get(key,0)) not in range(1,IO_BPS+1) for key in ['rbps','wbps']):
                raise ResourcePressure('container_limits_not_enforced')
            current.update(verified=True,cgroup=str(self.cgroup),memoryCurrentBytes=int((self.cgroup/'memory.current').read_text()),swapCurrentBytes=int((self.cgroup/'memory.swap.current').read_text()))
            current['maximumObservedMemoryBytes']=max(current.get('maximumObservedMemoryBytes',0),current['memoryCurrentBytes'])
        except FileNotFoundError:return  # A naturally exiting container can remove its cgroup.

    def stop_container(self):
        if not self.container:return
        path=Path(self.container['cidfile'])
        if not path.exists() or path.is_symlink():return
        cid=path.read_text().strip()
        if not re.fullmatch('[a-f0-9]{64}',cid):return
        for args,timeout in [(['docker','stop','--time','10',cid],20),(['docker','kill',cid],5)]:
            try:
                result=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout)
                if result.returncode==0:return
            except subprocess.TimeoutExpired:pass
        self.state['cleanupNeedsReview']=True;self.record(True)

    def end_container(self):
        if self.container:self.container['finishedAt']=self.wall()
        self.container=None;self.cgroup=None;self.record(True)

    def run(self,args,*,input=None,stdout=None,stderr=None,env=None,timeout=None,check=True,on_abort=None):
        self.check();started=self.clock();limit=min(timeout or JOB_SECONDS,max(0,self.deadline-started))
        process=subprocess.Popen(args,stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                                 stdout=stdout,stderr=stderr,env=env,start_new_session=True)
        first=True
        try:
            while True:
                remaining=limit-(self.clock()-started)
                if remaining<=0:raise subprocess.TimeoutExpired(args,limit)
                try:
                    process.communicate(input=input if first else None,timeout=min(POLL_SECONDS,remaining));break
                except subprocess.TimeoutExpired:first=False;self.check()
            self.check()
            if check and process.returncode:raise subprocess.CalledProcessError(process.returncode,args)
            return subprocess.CompletedProcess(args,process.returncode)
        except BaseException:
            try:
                if on_abort:on_abort()
            except Exception:
                self.state['cleanupNeedsReview']=True
            finally:terminate_group(process)
            raise
        finally:
            if process.stdin:process.stdin.close()

    def finish(self,error=None):
        self.state.update(status='failed' if error else 'succeeded',finishedAt=self.wall())
        if error:self.state['errorType']=type(error).__name__
        self.record(True)

def install_signal_handlers():
    seen=False;previous={}
    def interrupted(number,frame):
        nonlocal seen
        if not seen:
            seen=True;raise JobInterrupted('received_'+signal.Signals(number).name)
    for number in [signal.SIGTERM,signal.SIGINT]:previous[number]=signal.signal(number,interrupted)
    return previous

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--device',action='store_true');args=parser.parse_args()
    if args.device:print(disk_device(Path('/srv/maasweekly/shared'))[0])


def stop_orphan_writer(shared,job):
    """A dead controller must not leave a daemon-owned writer running behind it."""
    rows=subprocess.run(['docker','ps','-aq','--filter','name=^/maas-data-writer$'],capture_output=True,text=True,timeout=5)
    if rows.returncode:raise ResourcePressure('cannot_check_orphan_writer')
    ids=rows.stdout.split()
    if not ids:return {'writerPresent':False}
    if len(ids)!=1:raise ResourcePressure('ambiguous_orphan_writer')
    inspected=subprocess.run(['docker','inspect',ids[0]],capture_output=True,text=True,timeout=5)
    if inspected.returncode:raise ResourcePressure('cannot_identify_orphan_writer')
    value=json.loads(inspected.stdout)[0]
    if not value['State']['Running']:return {'writerPresent':True,'alreadyStopped':True}
    label=(value['Config'].get('Labels') or {}).get('maas.pipeline.job')
    legacy=(label is None and value['Image']==(Path(shared)/'data-writer-image').read_text().strip()
            and 'MAAS_CODE_COMMIT='+job['codeCommit'] in value['Config'].get('Env',[]))
    if value['Name']!='/maas-data-writer' or (label!=job['id'] and not legacy):
        raise ResourcePressure('unowned_writer_requires_review')
    cid=value['Id']
    if not re.fullmatch('[a-f0-9]{64}',cid):raise ResourcePressure('invalid_orphan_identity')
    result=subprocess.run(['docker','stop','--time','10',cid],capture_output=True,text=True,timeout=20)
    if result.returncode:raise ResourcePressure('orphan_writer_cleanup_failed')
    check=subprocess.run(['docker','ps','-q','--no-trunc','--filter','id='+cid],capture_output=True,text=True,timeout=5)
    if check.returncode or check.stdout.strip():raise ResourcePressure('orphan_writer_still_running')
    return {'writerPresent':True,'stopped':True,'containerId':cid}

if __name__=='__main__':main()
