import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from manual_training import Control
from review_trigger import maybe_queue,THRESHOLDS
class TriggerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.station=Path(self.tmp.name);self.root=self.station/'auto-training';self.root.mkdir();self.data=self.station/'uap-lab/email-reviews';self.data.mkdir(parents=True);self.now=time.time();self.config(enabled=True)
 def config(self,enabled=True,threshold=100):
  (self.station/'station-settings.json').write_text(json.dumps(dict(auto_training_enabled=enabled,auto_training_reviews=threshold,auto_training_enabled_epoch=self.now-100)))
 def reviews(self,n,stamp=None):
  self.rows=[dict(sample_id=str(i),human_confirmed=True,label='not_anomalous',reviewed_epoch=stamp or self.now-10) for i in range(n)];self.write()
 def write(self): (self.data/'training-manifest.json').write_text(json.dumps(dict(examples=self.rows)))
 def test_threshold_and_no_duplicate_running_cascade(self):
  self.reviews(99);c=Control(self.root);self.assertEqual(c.claim(),{})
  self.reviews(100);a=c.claim();self.assertEqual(a['source'],'review_threshold');self.assertEqual(a['new_review_count'],100);self.assertEqual(c.claim()['id'],a['id'])
  c.finish(a['id'],dict(phase='cascade_complete'));self.assertEqual(c.claim(),{})
 def test_reviews_during_training_are_not_lost(self):
  self.reviews(100);c=Control(self.root);a=c.claim();self.reviews(100,time.time()+1)
  c.finish(a['id'],dict(phase='cascade_complete'))
  state=c.transaction()
  maybe_queue(self.root,state,False,now=time.time()+2)
  self.assertEqual(state['request']['source'],'review_threshold');self.assertNotEqual(state['request']['id'],a['id'])
 def test_historical_deleted_machine_and_duplicates_do_not_count(self):
  self.reviews(99);self.rows.extend([dict(self.rows[0]),dict(self.rows[0],sample_id='old',reviewed_epoch=self.now-200),dict(self.rows[0],sample_id='deleted',deleted=True),dict(self.rows[0],sample_id='machine',human_confirmed=False)]);self.write();self.assertEqual(Control(self.root).claim(),{})
 def test_disabled_and_manual_request(self):
  self.reviews(100);self.config(False);c=Control(self.root);self.assertEqual(c.claim(),{});c.request();a=c.claim();self.assertEqual(a['source'],'web');self.config();self.assertEqual(c.claim()['id'],a['id'])
 def test_all_thresholds(self):
  for threshold in THRESHOLDS:
   self.config(threshold=threshold);self.reviews(threshold);state={};maybe_queue(self.root,state,False,now=self.now);self.assertEqual(state['request']['review_threshold'],threshold)
 def test_corrupt_manifest_never_queues(self):
  (self.data/'training-manifest.json').write_text('{');self.assertEqual(Control(self.root).claim(),{})
if __name__=='__main__':unittest.main()
