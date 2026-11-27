import hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import benchmark_context

class ReviewTaxonomyTests(unittest.TestCase):
 def test_legacy_labels_match_training_taxonomy_without_admitting_retired_labels(self):
  out=io.BytesIO();im=Image.new('RGB',(8,8),(12,20,40));im.save(out,format='PNG');raw=out.getvalue();digest=hashlib.sha256(b'8x8:RGB:'+im.tobytes()).hexdigest();aid='a'*32
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);folder=data/'email-reviews/examples'/aid;folder.mkdir(parents=True)
   sample=dict(origin='email:'+aid,label='not_anomalous',pixel_sha256=digest)
   for label,eligible in [('cloud',True),('star',True),('not_anomalous',True),('anomalous',False),('landscape',False),('unknown',False)]:
    with self.subTest(label=label):
     (folder/'review.json').write_text(json.dumps(dict(event_id=aid,label=label,human_confirmed=True)))
     with patch.object(benchmark_context,'crop',return_value=raw):result=benchmark_context.collect(data,[sample])[0]
     self.assertEqual('geometry' in result,eligible)
 def test_changed_pixels_still_rejected(self):
  aid='b'*32;out=io.BytesIO();Image.new('RGB',(8,8)).save(out,format='PNG')
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);folder=data/'email-reviews/examples'/aid;folder.mkdir(parents=True);(folder/'review.json').write_text(json.dumps(dict(event_id=aid,label='cloud',human_confirmed=True)))
   with patch.object(benchmark_context,'crop',return_value=out.getvalue()):result=benchmark_context.collect(data,[dict(origin='email:'+aid,label='not_anomalous',pixel_sha256='changed')])[0]
   self.assertIn('pixels changed',result['excluded'])
