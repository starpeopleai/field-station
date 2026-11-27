import json,tempfile,unittest
from pathlib import Path
from cascade_training import freeze_inputs,build_snapshot
class CascadeDatasetTests(unittest.TestCase):
 def test_frozen_machine_labels_human_override_and_four_distinct_snapshots(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);source=root/'stable';(source/'images').mkdir(parents=True)
   samples=[]
   for i,label in enumerate(['anomalous','not_anomalous']):
    (source/'images'/str(i)).write_bytes(bytes([i]));samples.append(dict(origin='email:'+str(i),label=label,group='g'+str(i),image='images/'+str(i),human_confirmed=True,pixel_sha256='human'+str(i),native_width=8,native_height=8,split='train'))
   (source/'dataset.json').write_text(json.dumps(dict(fingerprint='base',samples=samples,classes=['anomalous','not_anomalous'])))
   (source/'candidate-policy.json').write_text(json.dumps(dict(version='stable')))
   cfg={'code':str(Path(__file__).resolve().parents[1]),'cycle_root':str(root/'cycles'),'lanes':{lane:{'root':str(root/lane)} for lane in ['experimental','hybrid','machine']}}
   for lane in ['hybrid','machine']:
    corpus=root/lane/'corpus';corpus.mkdir(parents=True);rows={}
    for i,label in enumerate(['anomalous','not_anomalous']):
     (corpus/str(i)).write_bytes(bytes([i+2]));rows[str(i)]=dict(id='m'+str(i),image=str(i),label=label,generation='run',human_confirmed=False,label_source='machine',pixel_sha256='machine'+str(i),native_width=8,native_height=8)
    (corpus/'manifest.json').write_text(json.dumps(rows))
   # Machine labels may not override a reviewed identity or identical pixels.
   manifest=root/'machine/corpus/manifest.json';entries=json.loads(manifest.read_text())
   entries['conflict']=dict(entries['0'],id='different-id',label='not_anomalous',pixel_sha256='human0')
   entries['identity']=dict(entries['1'],id='0',pixel_sha256='different-pixels')
   manifest.write_text(json.dumps(entries))
   cycle=dict(id='one',stable_source=str(source),inputs=freeze_inputs(cfg,'one'))
   # Later collection must not change this cycle's source labels.
   (root/'machine/corpus/manifest.json').write_text('{}')
   paths=[build_snapshot(cfg,cycle,lane) for lane in ['experimental','hybrid','machine']]
   data=[json.loads((p/'dataset.json').read_text()) for p in paths]
   self.assertEqual(len({d['fingerprint'] for d in data}),3)
   self.assertTrue(all(r['human_confirmed'] for r in data[0]['samples']))
   self.assertEqual(len(data[1]['samples']),4)
   self.assertEqual(len(data[2]['samples']),4)
   self.assertEqual(data[2]['human_training_counts'],{'anomalous':1,'not_anomalous':1})
   self.assertTrue(data[2]['human_grounded'])
   self.assertTrue(all(r['pseudo_label'] for r in data[2]['samples'] if not r['human_confirmed']))
   from training_policy import machine_benchmark_training
   self.assertTrue(machine_benchmark_training(data[2]))
   self.assertEqual(data[2]['evaluation_mode'],'shared_human_benchmark')
   self.assertEqual(paths[0],build_snapshot(cfg,cycle,'experimental'))
   next_cycle=dict(cycle,id='two');self.assertNotEqual(paths[0],build_snapshot(cfg,next_cycle,'experimental'))
   # Scheduled collection uses the same human-grounded builder, even before
   # enough independent machine positives have accumulated.
   from corpus import machine_dataset
   scheduled,blockers=machine_dataset(root/'machine',Path(cfg['code']),source)
   scheduled_data=json.loads((scheduled/'dataset.json').read_text())
   self.assertFalse(blockers);self.assertEqual(len(scheduled_data['samples']),2)
   self.assertEqual(scheduled_data['human_training_counts'],{'anomalous':1,'not_anomalous':1})
   # Independently reserved recording groups must never enter fitting.
   reserved=root/'machine/decision-tuning';reserved.mkdir()
   (reserved/'reservations.json').write_text(json.dumps(dict(groups=['run'],pixels=[])))
   reserved_cycle=dict(cycle,id='reserved')
   reserved_data=json.loads((build_snapshot(cfg,reserved_cycle,'machine')/'dataset.json').read_text())
   self.assertEqual(len(reserved_data['samples']),2)
   # Contradictory pixels exclude only those examples, not good neighbors.
   base=json.loads((source/'dataset.json').read_text())
   base['samples'].extend([dict(base['samples'][0],origin='email:conflict',label='not_anomalous'),dict(base['samples'][0],origin='email:neighbor',pixel_sha256='neighbor')])
   (source/'dataset.json').write_text(json.dumps(base))
   corrected=json.loads((build_snapshot(cfg,dict(cycle,id='conflicts'),'machine')/'dataset.json').read_text())
   self.assertIn('email:neighbor',{r['origin'] for r in corrected['samples']})
   self.assertNotIn('human0',{r['pixel_sha256'] for r in corrected['samples']})
   self.assertEqual(len(corrected['quarantine']),2)
   # Old frozen manifests cannot reintroduce discarded machine labels.
   (root/'machine/corpus-reset.json').write_text(json.dumps(dict(epoch=1)))
   reset_data=json.loads((build_snapshot(cfg,cycle,'machine')/'dataset.json').read_text())
   self.assertEqual(reset_data['pseudo_labels'],0)
   self.assertTrue(all(r['human_confirmed'] for r in reset_data['samples']))
