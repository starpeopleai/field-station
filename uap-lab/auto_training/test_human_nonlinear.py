import unittest,importlib.util
import numpy as np
from human_nonlinear import select_rows,sample_weights,fit_head

class HumanRecipeTests(unittest.TestCase):
 def row(self,label,pixel,group='g',human=True):return dict(label=label,pixel_sha256=pixel,group=group,human_confirmed=human,split='train')
 def test_conflicts_and_machine_labels_do_not_train(self):
  rows=[self.row('anomalous','conflict'),self.row('not_anomalous','conflict'),self.row('anomalous','a'),self.row('not_anomalous','b'),self.row('anomalous','machine',human=False)]
  selected,conflicts=select_rows(rows)
  self.assertEqual(conflicts,['conflict']);self.assertEqual([r['pixel_sha256'] for r in selected],['a','b']);self.assertEqual(len(rows),5)
 def test_class_budgets_and_tempered_recording_influence(self):
  rows=[self.row('anomalous','a')]+[self.row('not_anomalous',str(i),'long') for i in range(100)]+[self.row('not_anomalous','short','short')]
  w=sample_weights(rows);self.assertAlmostEqual(w[0],sum(w[1:]));self.assertAlmostEqual(sum(w[1:101])/w[-1],10)
 @unittest.skipUnless(importlib.util.find_spec('torch'), 'Neural fitting runs in the dedicated ML CI job')
 def test_binary_head_learns_and_rejects_machine_rows(self):
  import torch
  torch.set_num_threads(2)
  rows=[self.row('anomalous','a'+str(i)) for i in range(8)]+[self.row('not_anomalous','n'+str(i)) for i in range(8)]
  x=np.array([[1,1]]*8+[[-1,-1]]*8,dtype=np.float32)
  head=fit_head(x,rows,['anomalous','not_anomalous']);p=torch.softmax(head(torch.tensor(x)),dim=1).detach().numpy()
  self.assertTrue(np.isfinite(p).all());np.testing.assert_allclose(p.sum(1),1,atol=1e-6);self.assertGreater(p[:8,0].mean(),p[8:,0].mean())
  rows[0]['human_confirmed']=False
  with self.assertRaises(ValueError):fit_head(x,rows,['anomalous','not_anomalous'])
if __name__=='__main__':unittest.main()

class RevisedRecipeTests(unittest.TestCase):
 def test_v2_weights_keep_every_example_and_reduce_positive_class_mass(self):
  from human_nonlinear import sample_weights,recipe_config
  import numpy as np
  rows=[dict(label='anomalous' if i<2 else 'not_anomalous',group=str(i//2),pixel_sha256=str(i)) for i in range(10)]
  cfg=recipe_config('human_nonlinear_v2');w=sample_weights(rows,cfg['positive_mass'])
  self.assertEqual(cfg['width'],128);self.assertEqual(cfg['epochs'],60)
  self.assertTrue(np.all(w>0));self.assertAlmostEqual(float(w[:2].sum()/w.sum()),.25)
  self.assertEqual(recipe_config('human_nonlinear_v1')['threshold'],.78)
