import hashlib,io,json,tempfile,unittest,sys,types
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import review_crop_recovery as recovery
import label_queue
class RecoveryTests(unittest.TestCase):
 def setup_case(self):
  im=Image.new('RGB',(10,10),'red');out=io.BytesIO();im.crop((2,2,6,6)).save(out,format='PNG');raw=out.getvalue()
  return im,raw,dict(bounds=[2,2,4,4],source_color_space='RGB',native_crop_sha256=hashlib.sha256(raw).hexdigest())
 def test_exact_pixels_only(self):
  im,raw,e=self.setup_case();self.assertEqual(recovery.verified_crop(im,e),raw)
  self.assertIsNone(recovery.verified_crop(Image.new('RGB',(10,10),'blue'),e))
  self.assertIsNone(recovery.verified_crop(im,dict(e,bounds=[9,9,4,4])))
 def test_original_segment_recovers_crop(self):
  im,raw,e=self.setup_case()
  with tempfile.TemporaryDirectory() as t,patch('review_color.sources',return_value=[(Path(t)/'s.mkv',.267)]),patch.object(recovery,'frames',return_value=[im]):
   self.assertEqual(recovery.recover(Path(t),e),raw)
 def test_wrong_frame_refuses_save(self):
  im,raw,e=self.setup_case()
  with tempfile.TemporaryDirectory() as t,patch('review_color.sources',return_value=[(Path(t)/'s.mkv',.267)]),patch.object(recovery,'frames',return_value=[Image.new('RGB',(10,10),'blue')]):
   with self.assertRaisesRegex(ValueError,'not been saved'):recovery.recover(Path(t),e)
 def test_pending_label_survives_cleared_crop(self):
  im,raw,e=self.setup_case();key='a'*32;request='b'*32
  with tempfile.TemporaryDirectory() as t:
   data=Path(t)/'uap-lab';folder=Path(t)/'notifications/outbox'/key;folder.mkdir(parents=True)
   e.update(generation='run-abc',pts_seconds=1,model='model',classification='anomalous');(folder/'event.json').write_text(json.dumps(e));(folder/'label-queue-dismissed.json').write_text('{"dismissed":true}')
   email=types.SimpleNamespace(event_reviews=lambda *a:[]);archive=types.SimpleNamespace(invalidate_event=lambda *a:None)
   with patch.dict(sys.modules,{'email_review':email,'review_archive':archive}),patch.object(recovery,'recover',return_value=raw),patch.object(label_queue,'store_review') as save:
    result=label_queue.label(data,dict(id=key,label='not_anomalous',request_id=request))
   self.assertTrue(result['saved']);self.assertEqual(save.call_args.args[1]['label'],'not_anomalous');self.assertEqual(save.call_args.args[2],raw)
if __name__=='__main__':unittest.main()
