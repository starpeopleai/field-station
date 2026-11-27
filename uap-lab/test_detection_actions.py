import json,tempfile,unittest
from pathlib import Path
from detection_actions import set_star,stars,canonical

class StarTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name)
  self.video='a'*32;self.sample='b'*32;self.key='video:'+self.video+':'+self.sample
  folder=self.data/'videos'/self.video;folder.mkdir(parents=True);(folder/'annotations.json').write_text(json.dumps([dict(id=self.sample)]))
 def test_star_survives_reload_and_unstar_preserves_other_stars(self):
  other='review:'+('c'*32)+':'+('c'*32)
  (self.data/'starred-objects.json').write_text(json.dumps({'objects':{other:{'starred_epoch':1}}}))
  self.assertTrue(set_star(self.data,{'id':self.key,'starred':True})['starred'])
  self.assertIn(canonical(self.key),stars(self.data));self.assertIn(other,stars(self.data))
  set_star(self.data,{'id':self.key,'starred':True})
  self.assertEqual(len(stars(self.data)),2)
  self.assertFalse(set_star(self.data,{'id':self.key,'starred':False})['starred'])
  self.assertEqual(stars(self.data),{other:{'starred_epoch':1}})
 def test_invalid_state_or_missing_frame_cannot_modify_saved_stars(self):
  for body in [{'id':self.key,'starred':'true'},{'id':'../escape','starred':True},{'id':'video:'+self.video+':'+('d'*32),'starred':True}]:
   with self.assertRaises(ValueError):set_star(self.data,body)
  self.assertFalse((self.data/'starred-objects.json').exists())
