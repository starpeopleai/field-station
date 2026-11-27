import contextlib,io,json,tempfile,time,unittest
from pathlib import Path
from live_status import EXPORT
class LiveStatusTests(unittest.TestCase):
 def export(self,ledger):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'sessions.json';p.write_text(json.dumps(ledger));out=io.StringIO()
   with contextlib.redirect_stdout(out):exec(EXPORT.replace('/Volumes/UFO-Field/station-runtime/youtube/sessions.json',str(p)),{})
   return json.loads(out.getvalue())
 def ledger(self,state='live',age=0):
  return dict(active_video_id='abcdefghijk',last_api_check=time.time()-age,sessions={'current':dict(video_id='abcdefghijk',state=state,end=0,secret='PRIVATE')},stream_key='PRIVATE')
 def test_confirmed_live_survives_delayed_rotation_without_private_data(self):
  d=self.export(self.ledger());self.assertEqual(d['active_video_id'],'abcdefghijk');self.assertNotIn('PRIVATE',json.dumps(d));self.assertEqual(set(d),{'schema','active_video_id','confirmed_at','state'})
 def test_completed_and_upcoming_not_live(self):
  for state in ('complete',None,'completing'):
   self.assertIsNone(self.export(self.ledger(state))['active_video_id'])
 def test_stale_confirmation_not_republished_as_live(self):
  self.assertIsNone(self.export(self.ledger(age=901))['active_video_id'])
 def test_unconfirmed_and_invalid_id_not_live(self):
  d=self.ledger();d.pop('last_api_check');self.assertIsNone(self.export(d)['active_video_id'])
  d=self.ledger();d['active_video_id']='invalid';self.assertIsNone(self.export(d)['active_video_id'])
if __name__=='__main__':unittest.main()
