import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from cascade_training import train_lane
from worker import finish_training
class CascadeRecoveryTests(unittest.TestCase):
 def test_experimental_binds_stable_without_training(self):
  cfg={'human_root':'human','lanes':{'experimental':{'root':'experiment'}}}
  with patch('experimental_profile.bind',return_value={'version':'stable','mode':'decision_profile'}) as bind:
   result=train_lane(cfg,{'stable_source':'trained-stable'},'experimental')
  bind.assert_called_once_with('human','experiment','trained-stable')
  self.assertEqual(result['mode'],'decision_profile')
 def test_null_publication_does_not_prevent_training(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'run';folder.mkdir();(folder/'dataset.json').write_text(json.dumps({'fingerprint':'new'}))
   with patch('worker.subprocess.run',side_effect=RuntimeError('trainer reached')) as run:
    with self.assertRaisesRegex(RuntimeError,'trainer reached'):
     finish_training(root,folder,root,root,{'publication':None})
   run.assert_called_once()
