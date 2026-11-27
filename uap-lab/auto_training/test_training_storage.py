import tempfile,unittest,os
from pathlib import Path
from training_storage import deduplicate,store_image
class StorageTests(unittest.TestCase):
 def test_identical_images_share_bytes_and_distinct_crops_survive(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);paths=[r/str(i) for i in range(3)]
   for p,data in zip(paths,[b'first',b'first',b'different']):p.write_bytes(data)
   result=deduplicate(paths,r/'objects');self.assertEqual(result['linked'],1)
   self.assertEqual(paths[0].stat().st_ino,paths[1].stat().st_ino);self.assertNotEqual(paths[0].stat().st_ino,paths[2].stat().st_ino)
   store_image(paths[0],b'edited',r/'objects');self.assertEqual(paths[1].read_bytes(),b'first');self.assertEqual(paths[2].read_bytes(),b'different')
 def test_corrupt_pool_never_replaces_source(self):
  import hashlib
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);p=r/'image';p.write_bytes(b'original');key=hashlib.sha256(b'original').hexdigest();obj=r/'objects'/key[:2]/(key+'.png');obj.parent.mkdir(parents=True);obj.write_bytes(b'wrong')
   with self.assertRaisesRegex(ValueError,'checksum'):deduplicate([p],r/'objects')
   self.assertEqual(p.read_bytes(),b'original')
 def test_symlink_is_not_followed(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);p=r/'source';p.write_bytes(b'unique');link=r/'link';link.symlink_to(p)
   with self.assertRaisesRegex(ValueError,'symlink'):deduplicate([link],r/'objects')
   self.assertEqual(p.read_bytes(),b'unique')
class CanonicalRootTests(unittest.TestCase):
 def test_legacy_alias_keeps_pool_on_resolved_training_volume(self):
  from controller import Controller
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);target=base/'ssd/auto-training';target.mkdir(parents=True);alias=base/'home/auto-training';alias.parent.mkdir();alias.symlink_to(target,target_is_directory=True)
   c=Controller(dict(root=str(alias),remote_app='/remote',remote_python='python'))
   self.assertEqual(c.root,target.resolve());self.assertEqual(c.root.parent/'training-objects',base.resolve()/'ssd/training-objects')
