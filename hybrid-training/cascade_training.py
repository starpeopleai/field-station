"""Isolated training snapshots and publication for manual multi-model cycles."""
import ctypes,fcntl,hashlib,json,os,shutil,sys,time
from collections import Counter
from pathlib import Path
from worker import read,save,finish_training
from policy import eligible_pseudo

def copy_image(source,destination):
 destination.parent.mkdir(parents=True,exist_ok=True)
 if source.is_symlink():raise ValueError('Symlink training image')
 if sys.platform=='darwin' and ctypes.CDLL(None).clonefile(os.fsencode(source),os.fsencode(destination),0)==0:return
 shutil.copyfile(source,destination)

def freeze_inputs(cfg,request_id):
 result={};root=Path(cfg['cycle_root'])/request_id;root.mkdir(parents=True,exist_ok=True)
 for lane in ('hybrid','machine'):
  source=Path(cfg['lanes'][lane]['root'])/'corpus/manifest.json';target=root/(lane+'-manifest.json')
  if not target.exists():save(target,read(source,{}))
  result[lane]=str(target)
 return result

def build_snapshot(cfg,cycle,lane):
 settings=cfg['lanes'][lane];root=Path(settings['root']);source=Path(cycle['stable_source']);base=read(source/'dataset.json');recipe=read(root/'recipe.json',{})
 reset=read(root/'corpus-reset.json',{}).get('epoch',0) if lane=='machine' else 0
 key=hashlib.sha256(json.dumps([cycle['id'],lane,base['fingerprint'],recipe,'human-grounded-v2',reset],sort_keys=True).encode()).hexdigest();folder=root/'runs'/key
 if (folder/'dataset.json').exists():return folder
 if folder.exists():folder.rename(folder.with_name(key+'.incomplete.'+str(time.time_ns())))
 (folder/'images').mkdir(parents=True)
 rows=[];sources=[]
 for row in base['samples']:
  if lane in ('experimental','machine') and not row.get('human_confirmed'):continue
  rows.append(dict(row,label_source='human' if row.get('human_confirmed') else row.get('label_source','base')));sources.append(source/row['image'])
 if lane in ('hybrid','machine'):
  corpus=Path(settings['root'])/'corpus';machine_rows=list(read(cycle['inputs'][lane],{}).values())
  if reset:machine_rows=[r for r in machine_rows if r.get('admitted_epoch',r.get('preserved_epoch',0))>reset]
  machine_rows=eligible_pseudo(rows,machine_rows)
  held_out={alias for row in rows if row['split']!='train' for alias in row.get('group_aliases',[])}
  for row in machine_rows:
   if row.get('human_confirmed') or row.get('label_source')!='machine':raise ValueError('Human label in machine corpus')
   if ('generation:'+row['generation'] in held_out or row['generation'] in held_out):continue
   rows.append(dict(origin='machine:'+row['id'],label=row['label'],group='machine:'+row['generation'],pixel_sha256=row['pixel_sha256'],native_width=row['native_width'],native_height=row['native_height'],human_confirmed=False,label_source='machine',input_color_space='RGB',split='train',pseudo_label=True))
   sources.append(corpus/row['image'])
 quarantine=[]
 if lane=='machine':
  sys.path.insert(0,str(Path(cfg['code'])/'uap-lab/recognition'))
  from candidate_dataset import group_rows
  combined=[dict(row,source=str(src)) for row,src in zip(rows,sources)]
  human_rows=[r for r in combined if r.get('human_confirmed')]
  labels={}
  for row in human_rows:labels.setdefault(row['pixel_sha256'],set()).add(row['label'])
  conflicts={pixel for pixel,values in labels.items() if len(values)>1}
  quarantine=[dict(origin=r['origin'],reason='conflicting_labels_for_identical_pixels') for r in human_rows if r['pixel_sha256'] in conflicts]
  machine_rows,machine_quarantine=group_rows([r for r in combined if not r.get('human_confirmed')])
  quarantine.extend(machine_quarantine)
  # Keep reviewed recording aliases and every nonconflicting reviewed example.
  # Regrouping the foundation would drop whole recordings on a single conflict.
  rows=[r for r in human_rows if r['pixel_sha256'] not in conflicts]+machine_rows
  sys.path.insert(0,str(Path(cfg['code'])/'uap-lab/auto_training'))
  from decision_tuning import training_filter
  from prospective import partition
  allowed=training_filter(root)
  rows=[r for r in rows if allowed(r)]
  rows,research_admission=partition(root,rows)
  sources=[Path(row.pop('source')) for row in rows]
 if {r['label'] for r in rows}!={'anomalous','not_anomalous'}:raise ValueError('Both labeled classes are required')
 for index,(row,src) in enumerate(zip(rows,sources)):
  image='images/'+str(index)+'.png';copy_image(src,folder/image);row['image']=image
 data=dict(base,samples=rows,fingerprint=key,blockers=[],counts=dict(Counter(r['label'] for r in rows)),training_lane={'experimental':'human_experimental','hybrid':'hybrid','machine':'machine_only'}[lane],shadow_only=True,training_strategy=recipe.get('training_strategy','recording_balanced'),cascade_id=cycle['id'],source_dataset=base['fingerprint'],quarantine=quarantine,human_baseline_version=read(source/'candidate-policy.json')['version'],pseudo_labels=sum(not r.get('human_confirmed') and r.get('label_source')=='machine' for r in rows),human_training_counts=dict(Counter(r['label'] for r in rows if r.get('human_confirmed'))))
 if lane=='machine':data.update(evaluation_mode='shared_human_benchmark',fixed_anomaly_threshold=.8,human_grounded=True,human_source_dataset=base['fingerprint'],research_admission=research_admission)
 save(folder/'dataset.json',data);save(folder/'experiment.json',dict(cascade_id=cycle['id'],lane=lane,recipe=recipe,source_model=str(source),created_epoch=time.time()))
 return folder

def train_lane(cfg,cycle,lane):
 if lane=='experimental':
  from experimental_profile import bind
  return bind(cfg['human_root'],cfg['lanes'][lane]['root'],cycle['stable_source'])
 root=Path(cfg['lanes'][lane]['root']);root.mkdir(parents=True,exist_ok=True)
 code=Path(cfg['code']);sys.path[:0]=[str(code/'uap-lab/auto_training'),str(code/'uap-lab/recognition'),str(code/'uap-lab')]
 # Serialize against collection and any worker already running before the cascade.
 with (root/'worker.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  state=read(root/'status.json',{})
  if lane=='experimental' and state.get('experiment_mode')=='trained':
   from experimental_profile import selection
   return selection(state)
  folder=build_snapshot(cfg,cycle,lane)
  state.update(phase='training',training_lane={'experimental':'human_experimental','hybrid':'hybrid','machine':'machine_only'}[lane],run_directory=str(folder),cascade_id=cycle['id'],error=None,baseline_copy=False,reason=None)
  save(root/'status.json',state)
  try:finish_training(root,folder,code,Path(cfg['human_root']),state)
  except Exception as exc:
   state.update(phase='error',error=str(exc),updated_epoch=time.time());save(root/'status.json',state);raise
  result=read(root/'status.json');return dict(version=result['shadow_version'],folder=str(folder),publication=result.get('publication'),publication_error=result.get('publication_error'))

def compare(cfg,cycle):
 from benchmark_worker import cycle as evaluate
 config=read(cfg['comparison_config']);status=read(Path(config['root'])/'status.json',{})
 if status.get('cascade_id')==cycle['id'] and status.get('state')=='complete':return status
 config['cascade_id']=cycle['id'];evaluate(config,force=True)
 status=read(Path(config['root'])/'status.json',{})
 if status.get('state')!='complete' or status.get('cascade_id')!=cycle['id']:raise RuntimeError('Shared evaluation has not completed')
 return status


def retry_publications(cfg,cycle):
 code=Path(cfg['code']);sys.path[:0]=[str(code/'uap-lab/auto_training'),str(code/'uap-lab/recognition'),str(code/'uap-lab')]
 from publish import publish
 errors={}
 for lane,result in cycle['steps'].items():
  if lane=='human' or result.get('state')!='complete' or result.get('publication'):continue
  try:
   root=Path(cfg['lanes'][lane]['root']);result['publication']=publish(root,Path(result['folder']));result.pop('publication_error',None)
   state=read(root/'status.json',{});state['publication']=result['publication'];state.pop('publication_error',None);save(root/'status.json',state)
  except Exception as exc:errors[lane]=str(exc)
 return errors
