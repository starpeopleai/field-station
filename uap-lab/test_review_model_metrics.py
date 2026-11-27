import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from observation_metrics import TZ,response
from review_model_metrics import commit_review,snapshot
class ReviewMetricsTests(unittest.TestCase):
 def record(self,id,label='not_anomalous',version='old',reviewed=10):
  return dict(event_id=id,sample_id=id,reviewed_epoch=reviewed,human_confirmed=True,label=label,pre_review_models=dict(captured_epoch=datetime(2026,11,17,12,tzinfo=TZ).timestamp(),predictions={'human':dict(version=version,settings_revision=0,label='anomalous')}))
 def test_history_survives_model_switch_without_misattribution(self):
  with tempfile.TemporaryDirectory() as t:
   data=Path(t);commit_review(data,self.record('one'));commit_review(data,self.record('two','anomalous','new'))
   with patch('review_model_metrics.state',return_value={'models':[dict(lane='human',version='new',available=True,settings_revision=0)]}):d=snapshot(data,datetime(2026,11,18,12,tzinfo=TZ).timestamp())
   history=next(r for r in d['timelines'] if r['lane']=='human')['periods']['7']['daytime']
   self.assertEqual((history['fp'],history['tp']),(1,1));self.assertEqual({r['version'] for r in history['points'][0]['models']},{'old','new'})
   active=next(r for r in d['series'] if r['active']);self.assertEqual(active['periods']['7']['daytime']['fp'],0)
 def test_correction_updates_counts_and_deletion_removes_it(self):
  with tempfile.TemporaryDirectory() as t:
   data=Path(t);commit_review(data,self.record('one'));commit_review(data,self.record('one','anomalous',reviewed=11))
   with patch('review_model_metrics.state',return_value={'models':[]}):
    d=snapshot(data,datetime(2026,11,18,12,tzinfo=TZ).timestamp());self.assertEqual(d['series'][0]['summaries']['0']['tp'],1);self.assertEqual(d['series'][0]['summaries']['0']['fp'],0)
    record=self.record('one',reviewed=12);record['deleted']=True;commit_review(data,record);self.assertFalse(snapshot(data)['series'])
 def test_endpoint_includes_prediction_history_and_activation(self):
  with tempfile.TemporaryDirectory() as t,patch('observation_metrics.snapshot',return_value={'ready':True}),patch('review_model_metrics.snapshot',return_value={'timelines':['history']}),patch('model_activation.status',return_value={'ready':True}):
   d=response(Path(t));self.assertEqual(d['reviewed_models']['timelines'],['history']);self.assertTrue(d['model_activation']['ready'])
