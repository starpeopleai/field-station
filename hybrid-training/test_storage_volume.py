import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from worker import verify_storage
class StorageTests(unittest.TestCase):
 def test_configured_volume_identity_and_containment(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);volume=root/'training';volume.mkdir();(volume/'.training-volume').write_text('expected');cfg={'storage_volume':str(volume),'storage_volume_id':'expected'}
   with patch.object(Path,'is_mount',return_value=True):
    verify_storage(volume/'models',cfg)
    with self.assertRaises(ValueError):verify_storage(root/'other',cfg)
    (volume/'escape').symlink_to(root/'other')
    with self.assertRaises(ValueError):verify_storage(volume/'escape',cfg)
    with self.assertRaises(ValueError):verify_storage(volume/'models',dict(cfg,storage_volume_id='wrong'))
   with patch.object(Path,'is_mount',return_value=False):
    with self.assertRaises(ValueError):verify_storage(volume/'models',cfg)
