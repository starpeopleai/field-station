import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import drive_storage as d
class StorageTests(unittest.TestCase):
 def test_external_only_and_names_with_spaces(self):
  output='Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/disk1 1000 300 700 30% /\n/dev/disk2 2000 500 1500 25% /Volumes/UFO Files Archive 1\n'
  with patch.object(d.subprocess,'run',return_value=Mock(stdout=output)):result=d.collect('HQ')
  self.assertEqual(len(result['drives']),1);row=result['drives'][0];self.assertEqual(row['name'],'UFO Files Archive 1');self.assertEqual(row['free_bytes'],1500*1024);self.assertEqual(row['used_percent'],25)
 def test_shared_apfs_capacity_counted_once(self):
  import plistlib
  output='Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/disk7s1 1000 100 700 10% /Volumes/One\n/dev/disk7s2 1000 200 700 20% /Volumes/Two\n'
  apfs={'Containers':[{'ContainerReference':'disk7','CapacityCeiling':1024000,'CapacityFree':716800,'Volumes':[{'DeviceIdentifier':'disk7s1'},{'DeviceIdentifier':'disk7s2'}]}]}
  with patch.object(d.subprocess,'run',side_effect=[Mock(stdout=output),Mock(stdout=plistlib.dumps(apfs))]):result=d.collect('HQ')
  self.assertEqual(len(result['drives']),2);self.assertEqual(result['total_capacity_bytes'],1024000);self.assertEqual(result['total_used_bytes'],307200)
 def test_hq_report_stale_when_disconnected(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'storage-status';path.mkdir();(path/'hq.json').write_text(json.dumps(dict(machine='HQ',status='available',updated_epoch=time.time()-300,drives=[])))
   with patch.dict(d._CACHE,dict(machine='Field',status='available',updated_epoch=time.time(),drives=[]),clear=True):result=d.status(tmp)
   self.assertEqual(result['machines'][1]['status'],'stale')
if __name__=='__main__':unittest.main()
