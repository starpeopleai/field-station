"""Resumable HQ evaluation of every eligible reviewed training example."""
import base64,argparse,fcntl,hashlib,json,random,secrets,subprocess,sys,time,uuid
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image
from worker import read,save,model_folder,verify_storage
PROTOCOL='full-review-box-v1'
BATCH=128

def choose(rows,count=500,seed=None):
 # Retained for reproducing historical random-sample runs only.
 pool=select_all(rows)
 if len(pool)<count:raise ValueError('Fewer than 500 human-reviewed images available')
 seed=secrets.randbits(128) if seed is None else seed
 return random.Random(seed).sample(pool,count),str(seed)

def select_all(rows):
 pool=[r for r in rows if r.get('human_confirmed') and r['label'] in ('anomalous','not_anomalous')]
 if not pool:raise ValueError('No reviewed binary training examples available')
 if len({r['origin'] for r in pool})!=len(pool):raise ValueError('Duplicate training origins')
 return pool

def totals(parts):
 values={k:sum(part[k] for part in parts) for k in ('tp','fp','tn','fn')};tp,fp,tn,fn=(values[k] for k in ('tp','fp','tn','fn'));n=tp+fp+tn+fn
 return dict(values,accuracy=(tp+tn)/n if n else None,false_positive_rate=fp/(fp+tn) if fp+tn else None,recall=tp/(tp+fn) if tp+fn else None)

def experimental_models(config):
 models={}
 for lane,key in [('experimental','experimental_root'),('hybrid','hybrid_root'),('machine','machine_root'),('rotation','rotation_root')]:
  if not config.get(key):continue
  state=read(Path(config[key])/'status.json',{})
  if state.get('shadow_folder') and not state.get('shadow_seed_only',True):models[lane]=Path(state['shadow_folder'])
 return models

def inference_key(policy):
 color=policy.get('color_decision',{})
 return json.dumps(dict(version=policy['version'],scope='review-box-v1',color=color if color.get('color_evidence') else None),sort_keys=True)

def previous_scores(root,previous,policy):
 """Reuse verified probabilities only for the same pixels and inference policy."""
 if previous.get('state')!='complete':return {}
 run=Path(previous.get('run','/nonexistent'))
 if not run.resolve().is_relative_to((Path(root)/'runs').resolve()):return {}
 contracts=read(run/'inference-contracts.json',{})
 lane=next((lane for lane,key in contracts.items() if key==inference_key(policy)),None)
 if lane is None:return {}
 samples=read(run/'live-sample.json',{}).get('samples',[]);pixels={r['origin']:r['pixel_sha256'] for r in samples};scores={}
 for path in sorted((run/lane).glob('*.json')):
  for prediction in read(path)['predictions']:
   origin=prediction['origin'];score=prediction['score']
   if origin not in pixels or not isinstance(score,(int,float)) or not 0<=score<=1:raise ValueError('Invalid cached benchmark probability')
   scores[(origin,pixels[origin])]=score
 return scores

def cycle(config,force=False):
 root=Path(config['root']);human_root=Path(config['human_root']);code=Path(config['code'])
 verify_storage(root,config)
 root.mkdir(parents=True,exist_ok=True)
 cascade=read(human_root/'cascade-status.json',{})
 if not force and cascade.get('phase') in ('preparing','training','activation_pending','evaluating','evaluation_retry_pending','publishing','publication_retry_pending'):return
 with (root/'worker.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  from experimental_profile import sync as sync_experimental
  sync_experimental(config)
  human_state=read(human_root/'status.json',{});human=model_folder(human_root,human_state['active_version']);models={'human':human};models.update(experimental_models(config))
  sys.path[:0]=[str(code/'uap-lab/auto_training'),str(code/'uap-lab/recognition'),str(code/'uap-lab')]
  from model_settings import effective
  from model_inspector_sync import pull_settings,rpc
  from crop_client import CropClassifier
  from model_test_worker import score
  from live_decisions import prepare,classify
  settings=pull_settings(config);policies={lane:effective(read(folder/'candidate-policy.json'),lane,settings) for lane,folder in models.items()}
  versions={lane:p['version'] for lane,p in policies.items()};revisions={lane:p.get('settings_revision',0) for lane,p in policies.items()}
  dataset=read(human/'dataset.json');rows=select_all(dataset['samples']);identity=dict(context_revision=2,evaluation_protocol=PROTOCOL,versions=versions,settings_revisions=revisions,source_dataset=dataset['fingerprint'])
  previous=read(root/'status.json',{});same=all(previous.get(k)==v for k,v in identity.items())
  if not force and same and previous.get('state')=='complete':sync(config);return
  resume=same and previous.get('state') in ('evaluating','retry_pending') and Path(previous.get('run','/nonexistent')).is_dir()
  run=Path(previous['run']) if resume else root/'runs'/uuid.uuid4().hex;run.mkdir(parents=True,exist_ok=True)
  save(run/'inference-contracts.json',{lane:inference_key(policy) for lane,policy in policies.items()})
  started=previous.get('started_epoch',time.time()) if resume else time.time();last_publish=0
  def progress(stage,completed,total,lane=None,**extra):
   nonlocal last_publish
   save(root/'status.json',dict(identity,state='evaluating',run=str(run),started_epoch=started,updated_epoch=time.time(),stage=stage,completed=completed,total=total,lane=lane,**extra))
   if time.monotonic()-last_publish>=20:
    try:sync(config)
    except Exception:pass # Metrics delivery never invalidates a resumable evaluation.
    last_publish=time.monotonic()
  progress('context',0,len(rows))
  try:
   sample_id=hashlib.sha256(json.dumps([(r['origin'],r['pixel_sha256'],r['label']) for r in rows]).encode()).hexdigest()
   save(run/'sample.json',dict(id=sample_id,count=len(rows),source_dataset=dataset['fingerprint'],source_folder=str(human),samples=rows,kind='full_reviewed_training_set'))
   eligible=[];excluded={}
   for start in range(0,len(rows),BATCH):
    chunk=rows[start:start+BATCH];path=run/'context'/f'{start:07d}.json';metadata=read(path)
    if metadata is None:
     payload=base64.b64encode(json.dumps([{k:r[k] for k in ('origin','label','pixel_sha256')} for r in chunk]).encode()).decode()
     remote="import sys,json,base64;from pathlib import Path;sys.path[:0]=['/Users/ufo-field/ufo-field/uap-lab','/Users/ufo-field/ufo-field/uap-lab/recognition'];from benchmark_context import collect;print(json.dumps(collect(Path('/Volumes/UFO-Field/uap-lab'),json.loads(base64.b64decode("+repr(payload)+")))))"
     metadata=json.loads(rpc(config,remote));save(path,metadata)
    if len(metadata)!=len(chunk):raise ValueError('Incomplete benchmark context response')
    for row,meta in zip(chunk,metadata):
     if meta['origin']!=row['origin']:raise ValueError('Benchmark context mapping mismatch')
     if meta.get('excluded'):excluded[meta['excluded']]=excluded.get(meta['excluded'],0)+1
     else:eligible.append(dict(row,geometry=meta['geometry']))
    progress('context',min(start+BATCH,len(rows)),len(rows),eligible=len(eligible),excluded_count=sum(excluded.values()))
   if not eligible:raise ValueError('No unchanged reviewed images are available')
   save(run/'context-coverage.json',dict(requested=len(rows),eligible=len(eligible),excluded=excluded));save(run/'live-sample.json',dict(samples=eligible,requested=len(rows),excluded=len(rows)-len(eligible)))
   tools=human_root/'tools';lanes={};inference_cache={}
   for lane,folder in models.items():
    policy=policies[lane];version=policy['version'];compiled=root/'compiled'/(version+'.mlmodelc');compiled.parent.mkdir(exist_ok=True)
    if not compiled.exists():subprocess.run([str(tools/'compile_model'),str(folder/'candidate.mlpackage'),str(compiled)],check=True,capture_output=True,timeout=300)
    parts=[];prior_scores=previous_scores(root,previous,policy)
    with CropClassifier(tools/'crop_worker',compiled,version,timeout=120) as classifier:
     for start in range(0,len(eligible),BATCH):
      chunk=eligible[start:start+BATCH];path=run/lane/f'{start:07d}.json';result=read(path)
      key=(inference_key(policy),start)
      if result is None and all((row['origin'],row['pixel_sha256']) in prior_scores for row in chunk):
       predictions=[dict(scores={'anomalous':prior_scores[(row['origin'],row['pixel_sha256'])],'not_anomalous':1-prior_scores[(row['origin'],row['pixel_sha256'])]}) for row in chunk]
       result=score(chunk,predictions,policy);save(path,result)
      if result is None and key in inference_cache:
       predictions=[dict(scores={'anomalous':r['score'],'not_anomalous':1-r['score']}) for r in inference_cache[key]['predictions']]
       result=score(chunk,predictions,policy);save(path,result)
      if result is None:
       samples=[];inputs=[];contexts=[];geometries=[]
       for row in chunk:
        source=human/row['image']
        if source.is_symlink() or not source.resolve().is_relative_to(human.resolve()):raise ValueError('Unsafe benchmark source')
        raw=source.read_bytes()
        import io
        with Image.open(io.BytesIO(raw)) as im:
         im=im.convert('RGB');digest=hashlib.sha256(f'{im.width}x{im.height}:RGB:'.encode()+im.tobytes()).hexdigest()
        if digest!=row['pixel_sha256']:raise ValueError('Benchmark source checksum mismatch')
        image,context,size=prepare(raw,row['geometry']);inputs.append(image);contexts.append(context);geometries.append(row['geometry']);samples.append(dict(row,native_width=size[0],native_height=size[1]))
       predictions=classify(classifier,inputs,contexts,geometries,policy,'full-'+lane+'-'+str(start));result=score(samples,predictions,policy);save(path,result)
      inference_cache[key]=result
      c=result['per_class']['anomalous'];part={k:c[k] for k in ('tp','fp','fn')};part['tn']=len(chunk)-sum(part.values());parts.append(part)
      progress('scoring',min(start+BATCH,len(eligible)),len(eligible),lane,completed_lanes=list(lanes),requested_count=len(rows),excluded_count=sum(excluded.values()))
    lanes[lane]=totals(parts);save(run/(lane+'-result.json'),dict(lanes[lane],count=len(eligible),batch_predictions=lane+'/'))
   epoch=time.time();point=dict(settings_revisions=revisions,epoch=epoch,day=datetime.fromtimestamp(epoch,ZoneInfo('America/Los_Angeles')).date().isoformat(),count=len(eligible),requested_count=len(rows),excluded_count=len(rows)-len(eligible),exclusions=excluded,evaluation_protocol=PROTOCOL,sample_id=sample_id,cascade_id=config.get('cascade_id'),lanes=lanes,**{lane+'_version':v for lane,v in versions.items()})
   save(run/'result.json',point);history=read(root/'history.json',dict(points=[]))
   if not any(p.get('run_id')==run.name for p in history['points']):history['points'].append(dict(point,run_id=run.name))
   history.update(updated_epoch=epoch,mode='full_reviewed_training_set',scope='All eligible reviewed training examples, the exact full-color review box; not unseen-footage accuracy.',seed_only=len(models)==1,phase='complete',available_lanes=list(models));save(root/'history.json',history)
   save(root/'status.json',dict(identity,state='complete',run=str(run),sample_id=sample_id,started_epoch=started,finished_epoch=epoch,count=len(eligible),requested_count=len(rows),excluded_count=len(rows)-len(eligible),cascade_id=config.get('cascade_id')));sync(config)
  except Exception as exc:
   save(root/'status.json',dict(read(root/'status.json',{}),state='retry_pending',error=str(exc),updated_epoch=time.time()));raise

def sync(config):
 from comparison import publish
 publish(Path(config['hybrid_root']),config['ssh_helper'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--force',action='store_true');a=p.parse_args();cycle(read(a.config),a.force)
