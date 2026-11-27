import ast,json,re,time,tempfile,unittest
from pathlib import Path
source=ast.parse(Path(__file__).with_name('label_queue.py').read_text())
ns=dict(json=json,re=re,time=time,Path=Path)
exec(compile(ast.Module(body=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('read','lease_videos','renew_review_leases')],type_ignores=[]),'label_queue.py','exec'),ns)
class Leases(unittest.TestCase):
 def test_retention_and_omission(self):
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);keep='a'*32;deleted='b'*32
   (data/'omitted-objects.json').write_text(json.dumps({'objects':{deleted:{'complete':True}}}))
   result=ns['renew_review_leases'](data,{'ids':[keep,deleted,keep]})
   self.assertEqual(result['protected'],1);self.assertEqual(result['omitted'],[deleted])
   leases=json.loads((data/'review-leases.json').read_text());self.assertGreater(leases[keep],time.time()+890);self.assertNotIn(deleted,leases)
 def test_invalid_request_never_writes(self):
  with tempfile.TemporaryDirectory() as tmp:
   for value in ({'ids':['../escape']},{'ids':'a'*32},{'ids':['a'*32]*10001}):
    with self.assertRaises(ValueError):ns['renew_review_leases'](Path(tmp),value)
   self.assertEqual(list(Path(tmp).iterdir()),[])
 def test_expired_leases_pruned(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'review-leases.json').write_text(json.dumps({'c'*32:time.time()-1}))
   ns['renew_review_leases'](p,{'ids':['a'*32]})
   self.assertNotIn('c'*32,json.loads((p/'review-leases.json').read_text()))
if __name__=='__main__':unittest.main()
