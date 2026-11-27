import unittest,tempfile,json,hashlib
from pathlib import Path
from approved_recovery import source
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.p=Path(self.temp.name)/'session';self.p.mkdir();(self.p/'recovery-original.mp4').write_bytes(b'evidence');self.note=dict(operator_approved=True,scope='surviving_evidence',session_id='session',full_session_available=False,video_sha256=hashlib.sha256(b'evidence').hexdigest())
 def save(self):(self.p/'recovery-publication.json').write_text(json.dumps(self.note))
 def test_absence_is_not_approval(self):self.assertIsNone(source(self.p))
 def test_explicit_approval_and_checksum(self):self.save();self.assertEqual(source(self.p),self.p/'recovery-original.mp4')
 def test_invalid_authorization(self):
  for key,value in [('operator_approved',False),('scope','full_session'),('session_id','other'),('full_session_available',True)]:
   old=self.note[key];self.note[key]=value;self.save()
   with self.assertRaises(ValueError):source(self.p)
   self.note[key]=old
 def test_changed_bytes_rejected(self):
  self.save();(self.p/'recovery-original.mp4').write_bytes(b'changed')
  with self.assertRaises(ValueError):source(self.p)
 def test_symlinks_rejected(self):
  self.save();(self.p/'recovery-original.mp4').unlink();(self.p/'recovery-original.mp4').symlink_to('/dev/null')
  with self.assertRaises(ValueError):source(self.p)
