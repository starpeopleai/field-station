import ast,json,re,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
source=ast.parse(Path(__file__).with_name('controller.py').read_text());ns=dict(json=json,re=re,subprocess=subprocess,time=time,Path=Path)
exec(compile(ast.Module(body=[n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Controller'],type_ignores=[]),'controller.py','exec'),ns)
Controller=ns['Controller']
class Retry(unittest.TestCase):
 def controller(self):
  c=Controller.__new__(Controller);c.python='python';c.app='/app';return c
 def test_status_retries_timeout(self):
  c=self.controller();c.remote=Mock(side_effect=[subprocess.TimeoutExpired('status',30),Mock(stdout='{"version":"new"}')])
  with patch('time.sleep'):self.assertEqual(c.rpc('deploy.py','status')['version'],'new')
  self.assertEqual(c.remote.call_count,2);self.assertEqual(c.remote.call_args.kwargs['timeout'],30)
 def test_mutation_not_repeated(self):
  c=self.controller();c.remote=Mock(side_effect=subprocess.TimeoutExpired('activate',360))
  with self.assertRaises(subprocess.TimeoutExpired):c.rpc('deploy.py','activate')
  self.assertEqual(c.remote.call_count,1)
 def test_resume_only_same_manual_request_and_recipe(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=self.controller();c.root=Path(tmp);c.recipe='recipe';c.manual_request_id='request';c.c={};fp='a'*64;folder=c.root/'run';folder.mkdir();(folder/'candidate-policy.json').write_text('{}');(folder/'dataset.json').write_text('{}');reviews=c.root/'reviews'/fp;reviews.mkdir(parents=True);(reviews/'reviews.json').write_text('{}')
   c.resume_state=dict(training_request_id='request',training_recipe='recipe',run_directory=str(folder),fingerprint=fp,examples=100)
   c.rpc=Mock(return_value={'fresh':True});self.assertEqual(c.snapshot(),dict(fingerprint=fp,examples=100));c.rpc.assert_not_called()
   c.manual_request_id='another';c.c={'remote_lab':'/lab'};self.assertEqual(c.snapshot(),{'fresh':True})
if __name__=='__main__':unittest.main()
