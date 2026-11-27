import unittest,tempfile,json
from pathlib import Path
from benchmark_worker import choose,experimental_models
class BenchmarkTests(unittest.TestCase):
 def test_random_sample_shared_manifest_reproducible_but_changes_between_runs(self):
  rows=[dict(origin=str(i),human_confirmed=True,label='anomalous' if i%2 else 'not_anomalous') for i in range(1000)]
  a,seed=choose(rows);b,_=choose(rows);repeat,_=choose(rows,seed=int(seed))
  self.assertEqual(a,repeat);self.assertNotEqual(a,b);self.assertEqual(len(a),500);self.assertEqual(len({r['origin'] for r in a}),500)
 def test_machine_labels_never_become_reference_truth(self):
  with self.assertRaises(ValueError):choose([dict(human_confirmed=False,label='anomalous')]*500)

 def test_human_experiment_is_independent_and_older_configs_still_work(self):
  self.assertEqual(experimental_models({}),{})
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);(root/'status.json').write_text(json.dumps(dict(shadow_folder=str(root/'baseline'),shadow_seed_only=False)))
   self.assertEqual(experimental_models(dict(experimental_root=str(root))),{'experimental':root/'baseline'})
 def test_rotation_requires_its_own_trained_artifact(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);config=dict(rotation_root=str(root))
   self.assertEqual(experimental_models(config),{})
   (root/'status.json').write_text(json.dumps(dict(shadow_folder=str(root/'rotated'),shadow_seed_only=False)))
   self.assertEqual(experimental_models(config),{'rotation':root/'rotated'})
 def test_inference_reuse_requires_identical_weights_and_enabled_color_policy(self):
  from benchmark_worker import inference_key
  a=dict(version='v1',thresholds={'anomalous':.6},color_decision={'color_evidence':False,'minimum_color_fraction':.2})
  b=dict(a,thresholds={'anomalous':.7},color_decision={'color_evidence':False,'minimum_color_fraction':.5})
  self.assertEqual(inference_key(a),inference_key(b))
  self.assertNotEqual(inference_key(a),inference_key(dict(b,version='v2')))
  self.assertNotEqual(inference_key(a),inference_key(dict(b,color_decision={'color_evidence':True})))
 def test_previous_probabilities_are_pixel_and_policy_bound(self):
  from benchmark_worker import previous_scores,inference_key
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);run=root/'runs/one';(run/'human').mkdir(parents=True);policy={'version':'v1'}
   (run/'inference-contracts.json').write_text(json.dumps({'human':inference_key(policy)}))
   (run/'live-sample.json').write_text(json.dumps({'samples':[{'origin':'a','pixel_sha256':'pixels'}]}))
   (run/'human/0000000.json').write_text(json.dumps({'predictions':[{'origin':'a','score':.8}]}))
   state={'state':'complete','run':str(run)};scores=previous_scores(root,state,policy)
   self.assertEqual(scores[('a','pixels')],.8);self.assertNotIn(('a','changed'),scores)
   self.assertEqual(previous_scores(root,state,{'version':'v2'}),{})
