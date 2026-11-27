import hashlib,json,tempfile,unittest
from pathlib import Path
from PIL import Image
from corpus import preserve,machine_dataset
CODE=Path(__file__).resolve().parents[1]
class CorpusTests(unittest.TestCase):
 def make(self,root,i,label='anomalous',group='one'):
  frames=root/'frames';frames.mkdir(exist_ok=True);im=Image.new('RGB',(8,8),(i,0,0));im.save(frames/(str(i)+'.png'))
  return dict(id=str(i),pixel_sha256=hashlib.sha256(b'8x8:RGB:'+im.tobytes()).hexdigest(),label=label,generation=group,native_width=8,native_height=8,teacher_version='seed')
 def test_preserved_pixels_survive_collection_cache_changes(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);row=self.make(root,1);data=preserve(root,[row],root/'frames');p=root/'corpus'/next(iter(data.values()))['image'];original=p.read_bytes();(root/'frames/1.png').write_bytes(b'changed');self.assertEqual(p.read_bytes(),original)
 def test_human_labels_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);row=self.make(root,1);row['human_confirmed']=True
   with self.assertRaises(ValueError):preserve(root,[row],root/'frames')
 def test_machine_training_requires_reviewed_foundation(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)
   with self.assertRaises(FileNotFoundError):machine_dataset(root,CODE,root/'missing-reviewed-source')
