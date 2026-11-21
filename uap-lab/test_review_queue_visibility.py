import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from review_queue_visibility import mark

class VisibilityTests(unittest.TestCase):
 def test_cutoff_published_without_deleting_media(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);media=root/'example.png';media.write_bytes(b'preserved')
   mark(root,100,'request');self.assertEqual(json.loads((root/'review-queue-cleared.json').read_text())['cutoff_epoch'],100);self.assertEqual(media.read_bytes(),b'preserved')
 def test_old_retry_cannot_expose_cleared_items(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);mark(root,200,'new');mark(root,100,'old');self.assertEqual(json.loads((root/'review-queue-cleared.json').read_text())['cutoff_epoch'],200)
 def test_cutoff_exists_before_slow_scan(self):
  import label_queue
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   def scan(*args,**kwargs):
    self.assertEqual(json.loads((root/'review-queue-cleared.json').read_text())['cutoff_epoch'],123)
    raise RuntimeError('stop before filesystem scan')
   with patch('review_retention.load_records',side_effect=scan):
    with self.assertRaisesRegex(RuntimeError,'stop before'):label_queue.clear_backlog(root,cutoff=123)
if __name__=='__main__':unittest.main()
