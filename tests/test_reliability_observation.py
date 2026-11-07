import json,sqlite3,sys,unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import reliability_observation as r
class ObservationTests(unittest.TestCase):
 def setUp(self):self.db=sqlite3.connect(':memory:');r.initialize(self.db);self.start=datetime(2026,11,7,18,tzinfo=r.ZONE).timestamp();self.db.execute('INSERT INTO reliability_meta VALUES(1,?)',[self.start])
 def tearDown(self):self.db.close()
 def fill(self):
  first=datetime(2026,11,8,tzinfo=r.ZONE)
  for d in range(7):
   date=first+timedelta(days=d)
   for minute in range(0,1440,5):
    now=(date+timedelta(minutes=minute)).timestamp();sample={'checkedAt':now,'dataThrough':str(date.date()),'daily':{'id':'daily'+str(d),'startedAt':int(date.timestamp()*1000),'state':'succeeded','trigger':'schedule'}};r.observe(self.db,sample,[])
   r.inspection(self.db,{'checkedAt':now,'delivery':{'status':'passed','latestWeekly':'2026-11-03' if d<4 else '2026-11-10'},'links':{'site':[{'status':'ok'}]}})
  return (first+timedelta(days=7)).timestamp()
 def test_never_claims_a_week_at_deployment_time(self):self.assertEqual(r.report(self.db,self.start+3600)['status'],'observing');self.assertEqual(r.report(self.db,self.start+3600)['completedDays'],0)
 def test_requires_complete_coverage_automatic_delivery_and_new_formal_weekly(self):
  now=self.fill();self.assertEqual(r.report(self.db,now)['status'],'passed')
  self.db.execute("UPDATE reliability_observations SET trigger='manual' WHERE day='2026-11-09'");self.assertEqual(r.report(self.db,now)['status'],'failed')
  self.db.execute("UPDATE reliability_observations SET trigger='schedule'");self.db.execute("DELETE FROM reliability_observations WHERE day='2026-11-09'");self.assertEqual(r.report(self.db,now)['status'],'failed')
 def test_old_weekly_and_failed_delivery_are_not_success(self):
  now=self.fill();self.db.execute("UPDATE reliability_inspections SET weekly='2026-11-03'");self.assertFalse(r.report(self.db,now)['weeklyPublicationObserved']);self.assertEqual(r.report(self.db,now)['status'],'failed')
