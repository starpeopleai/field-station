import hashlib,json,tempfile,unittest
from pathlib import Path
from review_receipts import confirmed,split

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name)
        self.item=dict(id='a'*32,request_id='b'*32,label='not_anomalous',queued_at=20)
        message='quick-label:'+self.item['request_id'];digest=hashlib.sha256(('station_web_review:'+message).encode()).hexdigest()
        self.path=self.data/'email-reviews/history'/(digest+'.json');self.path.parent.mkdir(parents=True)
        self.receipt=dict(event_id=self.item['id'],message_id=message,label='not_anomalous',human_confirmed=True)
        self.path.write_text(json.dumps(self.receipt))
    def test_exact_committed_request_can_be_acknowledged_without_manifest(self):
        self.assertTrue(confirmed(self.data,self.item)['saved'])
        done,remaining=split(self.data,[self.item]);self.assertEqual(len(done),1);self.assertFalse(remaining)
    def test_wrong_label_request_event_and_uncommitted_records_not_acknowledged(self):
        for item in [dict(self.item,label='anomalous'),dict(self.item,id='c'*32),dict(self.item,request_id='d'*32)]:self.assertIsNone(confirmed(self.data,item))
        self.path.write_text(json.dumps(dict(self.receipt,human_confirmed=False)));self.assertIsNone(confirmed(self.data,self.item))
    def test_reset_cutoff_not_bypassed(self):
        done,remaining=split(self.data,[self.item],30);self.assertFalse(done);self.assertEqual(remaining,[self.item])
    def test_corrupt_receipt_is_not_confirmation(self):
        self.path.write_text('{');self.assertIsNone(confirmed(self.data,self.item))
if __name__=='__main__':unittest.main()
