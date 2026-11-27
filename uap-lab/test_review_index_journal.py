import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from email_training import review_batch,current_review_index
class JournalTests(unittest.TestCase):
 def test_interrupted_save_replays_only_pending_records(self):
  with tempfile.TemporaryDirectory() as t:
   data=Path(t);root=data/'email-reviews';pending=root/'pending-index';pending.mkdir(parents=True);(pending/'enabled').write_text('1')
   key='a'*32;other='b'*32
   rows=[dict(event_id=key,label='anomalous'),dict(event_id=other,label='anomalous')]
   (root/'training-manifest.json').write_text(json.dumps(dict(examples=rows)))
   path=root/'examples'/key;path.mkdir(parents=True);(path/'review.json').write_text(json.dumps(dict(event_id=key,label='not_anomalous')));(pending/(key+'.json')).write_text('{}')
   with patch('email_training.replay_review_receipts',side_effect=AssertionError('Historical scan')),patch('concurrent.futures.ThreadPoolExecutor',side_effect=AssertionError('Full rebuild')):
    with review_batch(data):
     updated={r['event_id']:r for r in current_review_index(data)};self.assertEqual(updated[key]['label'],'not_anomalous');self.assertEqual(updated[other]['label'],'anomalous')
   self.assertFalse(list(pending.glob('*.json')));self.assertTrue((pending/'enabled').exists());self.assertEqual(len(json.loads((root/'training-manifest.json').read_text())['examples']),2)
 def test_missing_uncommitted_record_does_not_remove_existing_label(self):
  with tempfile.TemporaryDirectory() as t:
   data=Path(t);root=data/'email-reviews';pending=root/'pending-index';pending.mkdir(parents=True);(pending/'enabled').write_text('1');key='a'*32
   (root/'training-manifest.json').write_text(json.dumps(dict(examples=[dict(event_id=key,label='anomalous')])));(pending/(key+'.json')).write_text('{}')
   with review_batch(data):self.assertEqual(current_review_index(data)[0]['label'],'anomalous')
