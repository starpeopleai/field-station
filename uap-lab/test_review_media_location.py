import hashlib,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from review_playback import media_dir,native_path
class MediaLocationTests(unittest.TestCase):
 def test_existing_media_retained_and_verified_move_preferred(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'XDG_RUNTIME_DIR':tmp+'/runtime'}):
   data=Path(tmp)/'field/uap-lab';key='a'*32
   identity=hashlib.sha256(str(data).encode()).hexdigest()[:16]
   old=Path(tmp)/'runtime/review-videos'/identity/key
   new=data.parent/'review-playback'/identity/key
   self.assertEqual(media_dir(data,key),new)
   old.mkdir(parents=True);(old/'review.mp4').write_bytes(b'native')
   self.assertEqual(native_path(data,key),old/'review.mp4')
   new.mkdir(parents=True);(new/'review.mp4').write_bytes(b'native')
   self.assertEqual(native_path(data,key),new/'review.mp4')
   self.assertEqual((old/'review.mp4').read_bytes(),b'native')
if __name__=='__main__':unittest.main()
