import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import air_traffic as a
import air_traffic_archive as p

class PublicTrafficTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);a.base(self.root).mkdir();self.folder=self.root/'sessions'/'test';self.folder.mkdir(parents=True);self.now=time.time();self.manifest={'started_epoch':self.now,'ended_epoch':self.now+60}
 def tearDown(self):self.tmp.cleanup()
 def snapshot(self,provider='adsb.lol'):
  return dict(provider=provider,license='ODbL-1.0',sampled_epoch=self.now-10,received_epoch=self.now-10,center_id='test',center={'address':'PRIVATE ADDRESS','latitude':1,'longitude':2},api_key='SECRET',aircraft=[{'hex':'abc123','latitude':37,'longitude':-122,'position_epoch':self.now-11,'track_deg':90}])
 def test_private_feed_never_exported(self):
  a.store(self.root,self.snapshot('adsb.fi'));v=json.loads(p.bundle(self.root,self.folder,self.manifest).read_text());self.assertEqual(v['status'],'unavailable');self.assertEqual(v['samples'],[])
 def test_open_data_export_strips_center_and_secrets(self):
  a.store(self.root,self.snapshot(),namespace='public-');s=p.bundle(self.root,self.folder,self.manifest).read_text();self.assertNotIn('PRIVATE ADDRESS',s);self.assertNotIn('SECRET',s);self.assertNotIn('center',json.loads(s)['samples'][0]);self.assertEqual(json.loads(s)['samples'][0]['aircraft'][0]['track_deg'],90)
 def test_bundle_keeps_samples_after_history_expiry(self):
  a.store(self.root,self.snapshot(),namespace='public-');path=p.bundle(self.root,self.folder,self.manifest);before=path.read_bytes();(a.base(self.root)/'public-history.sqlite').unlink();p.bundle(self.root,self.folder,self.manifest);self.assertEqual(path.read_bytes(),before)
 def test_retained_event_public_context(self):
  a.store(self.root,self.snapshot(),namespace='public-');key='a'*32;folder=self.root/'notifications/outbox'/key;folder.mkdir(parents=True)
  p.attach_public(self.root,folder,{'id':key,'detected_epoch':self.now});(a.base(self.root)/'public-history.sqlite').unlink()
  a.atomic(self.folder/'review-annotations.json',{'annotations':[{'event_id':key}]});v=json.loads(p.bundle(self.root,self.folder,self.manifest).read_text());self.assertEqual(len(v['samples']),1);self.assertEqual(v['detections'][0]['status'],'available')
 def test_gaps_explicit(self):
  v=json.loads(p.bundle(self.root,self.folder,self.manifest).read_text());self.assertEqual(v['coverage_gaps'],[{'start_epoch':self.now,'end_epoch':self.now+60}])
 def test_restart_obeys_public_request_budget(self):
  a.atomic(a.base(self.root)/'public-collector-status.json',{'next_attempt':self.now+180})
  with patch.object(a,'fetch_json',side_effect=AssertionError('unexpected request')):p.collect_due(self.root)
 def test_license_metadata_present(self):
  v=json.loads(p.bundle(self.root,self.folder,self.manifest).read_text());self.assertEqual(v['license'],'ODbL-1.0');self.assertIn('ADSB.lol',v['attribution'])

if __name__=='__main__':unittest.main()
