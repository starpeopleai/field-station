import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
from backlog_media import cleanup
from backlog_safety import protected,reviewed_events

class SafetyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.data=Path(self.tmp.name)/'lab';self.data.mkdir();self.key='a'*32
  self.folder=self.data.parent/'notifications/outbox'/self.key;self.folder.mkdir(parents=True)
  self.put(self.folder/'event.json',{'id':self.key})
  self.image=self.folder/'native-object.png';self.image.write_bytes(b'keep')
  self.audit=self.data/'audit';self.audit.mkdir()
  self.row={'kind':'detection','id':self.key}
  (self.audit/'actions.jsonl').write_text(json.dumps(self.row)+'\n')
 def put(self,p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))
 def run_cleanup(self):return cleanup(self.data,self.audit)
 def test_unreviewed_deleted(self):
  self.assertEqual(self.run_cleanup()['media_files_deleted'],1);self.assertFalse(self.image.exists())
 def test_manual_recording_preserved(self):
  self.put(self.folder/'event.json',{'kind':'manual_recording','manual_session_id':'session'})
  self.assertEqual(self.run_cleanup()['media_protected'],1);self.assertTrue(self.image.exists())
 def test_star_preserved(self):
  self.put(self.data/'starred-objects.json',{'objects':{'review:'+self.key+':'+self.key:{}}})
  self.assertEqual(self.run_cleanup()['media_protected'],1);self.assertTrue(self.image.exists())
 def test_archive_evidence_preserved(self):
  self.put(self.folder/'archive-decision.json',{'confirmed_anomalous':True})
  self.assertEqual(self.run_cleanup()['media_protected'],1);self.assertTrue(self.image.exists())
 def test_human_review_preserved(self):
  self.put(self.data/'email-reviews/examples'/self.key/'review.json',{'event_id':self.key,'human_confirmed':True})
  self.assertEqual(self.run_cleanup()['media_protected'],1);self.assertTrue(self.image.exists())
 def test_corrupt_bookmarks_abort(self):
  (self.data/'starred-objects.json').write_text('{broken')
  with self.assertRaises(ValueError):self.run_cleanup()
  self.assertTrue(self.image.exists())
 def test_corrupt_review_aborts(self):
  p=self.data/'email-reviews/examples'/self.key/'review.json';p.parent.mkdir(parents=True);p.write_text('{broken')
  with self.assertRaises(ValueError):self.run_cleanup()
  self.assertTrue(self.image.exists())
 def test_review_io_error_aborts(self):
  with patch('backlog_safety.reviewed_events',side_effect=OSError('disk unavailable')):
   with patch('backlog_media.reviewed_events',side_effect=OSError('disk unavailable')):
    with self.assertRaises(OSError):self.run_cleanup()
  self.assertTrue(self.image.exists())
 def test_annotated_video_preserved(self):
  row={'kind':'video','id':self.key};folder=self.data/'videos'/self.key
  self.put(folder/'video.json',{'id':self.key});self.put(folder/'annotations.json',[{'label':'anomalous'}])
  self.assertTrue(protected(self.data,row))
 def test_session_video_preserved(self):
  self.put(self.data/'videos'/self.key/'video.json',{'provenance':{'session_id':'manual-session'}})
  self.assertTrue(protected(self.data,{'kind':'video','id':self.key}))
 def test_active_producer_preserved(self):
  self.put(self.folder.parent/'producer-state.json',{'groups':[{'id':self.key}]})
  self.assertEqual(self.run_cleanup()['media_deferred'],1);self.assertTrue(self.image.exists())
 def test_symlink_preserved(self):
  (self.folder/'clip.mp4').symlink_to(self.image)
  self.assertEqual(self.run_cleanup()['media_deferred'],1);self.assertTrue(self.image.exists())
if __name__=='__main__':unittest.main()
