import hashlib,json,tempfile,unittest
from pathlib import Path
from review_receipts import confirmed,split

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name)/'uap-lab'
        self.item=dict(id='a'*32,request_id='b'*32,label='not_anomalous',queued_at=20)
        message='quick-label:'+self.item['request_id'];digest=hashlib.sha256(('station_web_review:'+message).encode()).hexdigest()
        self.path=self.data/'email-reviews/history'/(digest+'.json');self.path.parent.mkdir(parents=True)
        self.receipt=dict(event_id=self.item['id'],message_id=message,label='not_anomalous',human_confirmed=True)
        self.path.write_text(json.dumps(self.receipt))
    def mark_cleared(self,reason='User cleared labeling backlog'):
        path=self.data.parent/'notifications/outbox'/self.item['id']/'label-queue-dismissed.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(dismissed=True,reason=reason,queue_clear_id='c'*32)))
    def test_cleared_request_is_removed_not_reported_saved(self):
        self.path.unlink();self.mark_cleared();done,remaining=split(self.data,[self.item])
        self.assertFalse(remaining);self.assertFalse(done[0]['saved']);self.assertTrue(done[0]['discarded']);self.assertEqual(done[0]['reason'],'backlog_cleared')
    def test_automatic_retention_does_not_discard_human_choice(self):
        self.path.unlink();self.mark_cleared('bounded_machine_negative_sample');done,remaining=split(self.data,[self.item])
        self.assertFalse(done);self.assertEqual(remaining,[self.item])
    def test_committed_review_wins_over_old_clear_marker(self):
        self.mark_cleared();done,remaining=split(self.data,[self.item]);self.assertTrue(done[0]['saved']);self.assertFalse(remaining)
    def test_current_review_can_still_be_relabelled(self):
        self.path.unlink();self.mark_cleared();p=self.data/'email-reviews/examples'/self.item['id']/'review.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'human_confirmed':True}))
        done,remaining=split(self.data,[self.item]);self.assertFalse(done);self.assertEqual(remaining,[self.item])
    def test_exact_committed_request_can_be_acknowledged_without_manifest(self):
        self.assertTrue(confirmed(self.data,self.item)['saved'])
        done,remaining=split(self.data,[self.item]);self.assertEqual(len(done),1);self.assertFalse(remaining)
    def test_wrong_label_request_event_and_uncommitted_records_not_acknowledged(self):
        for item in [dict(self.item,label='anomalous'),dict(self.item,id='c'*32),dict(self.item,request_id='d'*32)]:self.assertIsNone(confirmed(self.data,item))
        self.path.write_text(json.dumps(dict(self.receipt,human_confirmed=False)));self.assertIsNone(confirmed(self.data,self.item))
    def test_reset_cutoff_not_bypassed(self):
        done,remaining=split(self.data,[self.item],30);self.assertFalse(done);self.assertEqual(remaining,[self.item])
    def test_busy_batch_acknowledges_receipt_and_retries_remaining_label(self):
        import sqlite3
        from unittest.mock import patch
        from detection_library import label_batch
        other=dict(self.item,id='e'*32,request_id='f'*32)
        error=sqlite3.OperationalError('database is locked')
        error.sqlite_errorcode=sqlite3.SQLITE_BUSY
        with patch('detection_library._label_batch',side_effect=error):
            results=label_batch(self.data,dict(items=[self.item,other]))['results']
        self.assertTrue(results[0]['saved'])
        self.assertEqual(results[1]['request_id'],other['request_id'])
        self.assertFalse(results[1]['saved'])
        self.assertTrue(results[1]['retryable'])
    def test_corrupt_receipt_is_not_confirmation(self):
        self.path.write_text('{');self.assertIsNone(confirmed(self.data,self.item))
if __name__=='__main__':unittest.main()
