"""Bounded metadata-only evidence for seven complete days of unattended operation."""
import argparse,json,sqlite3,time
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ZONE=ZoneInfo('Asia/Shanghai')
def day(t):return datetime.fromtimestamp(t,ZONE).date().isoformat()
def initialize(db):
 db.executescript('''CREATE TABLE IF NOT EXISTS reliability_meta(id INTEGER PRIMARY KEY CHECK(id=1),started REAL NOT NULL);
 CREATE TABLE IF NOT EXISTS reliability_observations(at INTEGER PRIMARY KEY,day TEXT NOT NULL,data_through TEXT,daily_id TEXT,daily_state TEXT,trigger TEXT,issues TEXT NOT NULL,disk_free INTEGER);
 CREATE TABLE IF NOT EXISTS reliability_inspections(day TEXT PRIMARY KEY,at REAL NOT NULL,delivery_ok INTEGER NOT NULL,weekly TEXT,site_ok INTEGER NOT NULL);
 ''')
def observe(db,sample,issues):
 now=sample['checkedAt'];daily=sample.get('daily') or {}
 db.execute('INSERT OR IGNORE INTO reliability_meta VALUES(1,?)',[now])
 db.execute('INSERT OR REPLACE INTO reliability_observations VALUES(?,?,?,?,?,?,?,?)',[int(now)//300*300,day(now),sample.get('dataThrough'),daily.get('id'),daily.get('state'),daily.get('trigger','unknown') if daily.get('startedAt') and day(daily['startedAt']/1000)==day(now) else 'previous_day',json.dumps(sorted(issues)),sample.get('operations',{}).get('resources',{}).get('disk',{}).get('availableBytes')])
 db.execute('DELETE FROM reliability_observations WHERE at<?',[now-31*86400])
def inspection(db,sample):
 now=sample['checkedAt'];delivery=sample.get('delivery') or {};site=sample.get('links',{}).get('site',[])
 db.execute('INSERT OR REPLACE INTO reliability_inspections VALUES(?,?,?,?,?)',[day(now),now,int(delivery.get('status')=='passed'),delivery.get('latestWeekly'),int(bool(site) and all(x.get('status')=='ok' for x in site))])
 db.execute('DELETE FROM reliability_inspections WHERE at<?',[now-31*86400])
def report(db,now=None):
 now=now or time.time();start=db.execute('SELECT started FROM reliability_meta WHERE id=1').fetchone()
 if not start:return {'status':'not_started','completedDays':0,'requiredDays':7}
 today=datetime.fromtimestamp(now,ZONE).date();first=max(datetime.fromtimestamp(start[0],ZONE).date()+timedelta(days=1),today-timedelta(days=7))
 rows=[]
 for i in range(7):
  date=first+timedelta(days=i)
  if date>=today:break
  key=str(date);begin=datetime.combine(date,datetime.min.time(),ZONE).timestamp();end=begin+86400
  samples=db.execute('SELECT at,data_through,daily_state,trigger,issues,disk_free FROM reliability_observations WHERE day=? ORDER BY at',[key]).fetchall()
  checks=db.execute('SELECT delivery_ok,weekly,site_ok FROM reliability_inspections WHERE day=?',[key]).fetchone()
  reasons=[];points=[begin,*[x[0] for x in samples],end]
  if len(samples)<270 or max(b-a for a,b in zip(points,points[1:]))>900:reasons.append('monitoring_gap')
  if any(json.loads(x[4]) for x in samples):reasons.append('confirmed_incident')
  if any(x[3]=='manual' for x in samples):reasons.append('manual_daily_recovery')
  if not any(x[2]=='succeeded' and x[3]=='schedule' and x[1]==key and x[0]<begin+13*3600 for x in samples):reasons.append('automatic_delivery_deadline')
  if not checks or not checks[0] or not checks[2]:reasons.append('delivery_inspection_missing_or_failed')
  rows.append({'day':key,'passed':not reasons,'reasons':reasons,'samples':len(samples),'minFreeGiB':min([x[5]/1024**3 for x in samples if x[5] is not None],default=None),'weekly':checks[1] if checks else None})
 weekly={r['weekly'] for r in rows if r['weekly']}
 complete=len(rows)==7;passed=complete and all(r['passed'] for r in rows) and len(weekly)>=2
 return {'status':'passed' if passed else 'failed' if complete else 'observing','startedAt':start[0],'completedDays':len(rows),'requiredDays':7,'weeklyPublicationObserved':len(weekly)>=2,'days':rows}
def main():
 p=argparse.ArgumentParser();p.add_argument('--database',type=Path,default=Path('/srv/maasweekly/shared/state/data-alerts/alerts.sqlite'));a=p.parse_args()
 db=sqlite3.connect('file:'+str(a.database)+'?mode=ro',uri=True)
 print(json.dumps(report(db),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
