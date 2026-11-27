import tempfile,json,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from youtube_sessions import Studio,RequestNotStarted,cycle,slot,save
class RecoveryTests(unittest.TestCase):
 def test_closed_dashboard_reopens_without_sending(self):
  a=Studio();a.evaluate=Mock(side_effect=RuntimeError('Keep a signed-in YouTube Studio live dashboard tab open'))
  with patch('youtube_sessions.subprocess.run') as run:
   with self.assertRaises(RequestNotStarted):a.post('/live/create_broadcast',{})
   run.assert_called_once()
 def test_creation_retry_only_for_unsent_request(self):
  for error,pending in [(RequestNotStarted('not sent'),False),(TimeoutError('uncertain'),True)]:
   with self.subTest(pending=pending),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);api=Mock();api.create.side_effect=error;now=1795078000
    save(root/'sessions.json',dict(sessions={}))
    with self.assertRaises(type(error)):cycle({},root,api,now)
    state=json.loads((root/'sessions.json').read_text())
    self.assertEqual(state['sessions'][slot(now)['key']]['creation_pending'],pending)
