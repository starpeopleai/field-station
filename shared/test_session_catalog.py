import json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import session_catalog as catalog
class CatalogRepairTests(unittest.TestCase):
 def test_missing_root_rebuilds_then_uses_index(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);folder=root/'sessions'/'20261121T000000Z-abcdef';folder.mkdir(parents=True)
   (folder/'manifest.json').write_text(json.dumps({'spool_generation':'run-abcdef','state':'completed'}))
   (folder/'buffer-state.json').write_text(json.dumps({'segments':[{'start':10,'end':20}]}))
   with patch.dict(os.environ,{'CAPTURE_SESSION_INDEX':str(root/'index.sqlite')}):
    self.assertIsNone(catalog.lookup(root,'run-abcdef',15))
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
     result=catalog.lookup(root,'run-abcdef',15)
     if result is not None:break
     time.sleep(.02)
    self.assertEqual(result,[folder]);self.assertEqual(catalog.lookup(root,'run-abcdef',25),[])
 def test_invalid_index_returns_fallback_and_requests_repair(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'session-catalog-invalid').write_text('invalid')
   with patch.dict(os.environ,{'CAPTURE_SESSION_INDEX':str(root/'index.sqlite')}),patch.object(catalog,'request_rebuild') as repair:
    self.assertIsNone(catalog.lookup(root,'run-abcdef',15));repair.assert_called_once_with(root)
 def test_duplicate_repairs_not_started(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   with patch.dict(os.environ,{'CAPTURE_SESSION_INDEX':str(root/'index.sqlite')}),patch.object(catalog.threading,'Thread') as thread:
    catalog.request_rebuild(root);catalog.request_rebuild(root);self.assertEqual(thread.call_count,1)
   catalog._REPAIR_PENDING.clear()
if __name__=='__main__':unittest.main()
