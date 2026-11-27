"""Persistent HQ-only decision tuning; never trains or activates learned weights."""
import argparse,base64,fcntl,hashlib,io,json,sys,time,zlib
from pathlib import Path
from model_inspector_sync import read,save,rpc,folder_for,pull_settings
from decision_tuning import fresh,groups,reservations,tune,benchmark_rows

def remote(cfg,script):
 prefix="import sys,json;from pathlib import Path;sys.path.insert(0,'/Users/ufo-field/ufo-field/uap-lab');data=Path('/Volumes/UFO-Field/uap-lab');"
 return json.loads(rpc(cfg,prefix+script))

def apply(cfg,lane,version,revision,values,proof):
 body=repr(json.dumps(dict(lane=lane,version=version,revision=revision,values=values,proof=proof)))
 return remote(cfg,"from model_settings import automatic_update;v=json.loads("+body+");print(json.dumps(automatic_update(data,**v)))")

def reserve(root,rows,maximum_recordings=8):
 # Keep the existing holdout immutable, but do not reserve every future
 # recording and progressively starve the training corpus.
 path=root/'decision-tuning/reservations.json';value=reservations(root);existing=set(value['groups'])
 candidates=set().union(*(groups(r) for r in rows)) if rows else set()
 additions=sorted(candidates-existing,key=lambda g:hashlib.sha256(g.encode()).hexdigest())[:max(0,maximum_recordings-len(existing))]
 selected=existing|set(additions);rows=[r for r in rows if groups(r) and groups(r)<=selected]
 value['groups']=sorted(selected);value['pixels']=sorted(set(value['pixels'])|{r['pixel_sha256'] for r in rows if r.get('pixel_sha256')});save(path,value)
 return rows

def machine_scores(cfg,model,folder,rows,policy):
 from PIL import Image
 from crop_client import CropClassifier
 from night_context import predict
 root=Path(cfg['root']);lane_root=Path(cfg['machine_root']);cache_path=lane_root/'decision-tuning/scores.json';cache=read(cache_path,{});pending=[];images=[]
 for row in rows:
  key=model['version']+':'+row['pixel_sha256']
  if key not in cache:
   path=lane_root/'corpus'/row['image']
   if path.is_symlink() or not path.resolve().is_relative_to((lane_root/'corpus').resolve()):raise ValueError('Unsafe machine tuning image')
   raw=path.read_bytes()
   with Image.open(io.BytesIO(raw)) as im:
    im=im.convert('RGB');digest=hashlib.sha256(f'{im.width}x{im.height}:RGB:'.encode()+im.tobytes()).hexdigest()
   if digest!=row['pixel_sha256']:raise ValueError('Machine tuning crop checksum mismatch')
   pending.append(key);images.append(raw)
 compiled=root/'compiled'/(model['version']+'.mlmodelc');tools=Path(cfg['human_root'])/'tools'
 if images:
  if not compiled.exists():
   import subprocess
   subprocess.run([str(tools/'compile_model'),str(folder/'candidate.mlpackage'),str(compiled)],check=True,capture_output=True,timeout=300)
  with CropClassifier(tools/'crop_worker',compiled,model['version'],timeout=120) as worker:
   for start in range(0,len(images),32):
    results=predict(worker,images[start:start+32],[],policy,'automatic-tuning')
    for key,result in zip(pending[start:start+32],results):
     if result.get('error'):raise ValueError(result['error'])
     cache[key]=result['scores']['anomalous']
  save(cache_path,cache)
 return [dict(r,score=cache[model['version']+':'+r['pixel_sha256']],native_size=max(r['native_width'],r['native_height'])) for r in rows]

def cycle(cfg):
 root=Path(cfg['root'])
 from worker import verify_storage
 verify_storage(root,cfg)
 root.mkdir(parents=True,exist_ok=True)
 sys.path[:0]=[str(Path(cfg['code'])/'uap-lab'),str(Path(cfg['code'])/'uap-lab/recognition')]
 from model_settings import effective,defaults
 with (root/'decision-tuning.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  if read(Path(cfg['human_root'])/'cascade-status.json',{}).get('phase') in ('preparing','training','activation_pending','publishing'):return
  catalog=read(root/'model-inspector/models.json',{});settings=pull_settings(cfg);status={}
  for lane in ('hybrid','machine'):
   try:
    model=next(m for m in catalog.get('models',[]) if m['lane']==lane and m.get('available'));version=model['version'];lane_root=Path(cfg[lane+'_root']);folder=folder_for(lane_root,version,read(lane_root/'status.json'));dataset=read(folder/'dataset.json');pending=Path(read(lane_root/'status.json',{}).get('run_directory','/nonexistent'));pending_data=read(pending/'dataset.json',{}) if pending!=folder else {};dataset=dict(dataset,samples=dataset['samples']+pending_data.get('samples',[]));record=settings.get('models',{}).get(lane+':'+version,{})
    if record.get('owner')!='automatic':
     apply(cfg,lane,version,record.get('revision',0),{},dict(action='automatic_baseline',label_source='human' if lane=='hybrid' else 'machine'));settings=pull_settings(cfg)
    policy=effective(model['policy'],lane,settings);baseline=defaults(policy)
    # Serialize reservation changes against this lane's training/collection.
    with (lane_root/'worker.lock').open('a') as lane_lock:
     try:fcntl.flock(lane_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
     except BlockingIOError:status[lane]=dict(state='waiting',message='Waiting for the current model worker to finish.');continue
     if lane=='hybrid':
      # A prediction frozen before review belongs to its old model/settings.
      # Use current-model benchmark scores on recording-disjoint reviewed rows
      # instead of starving calibration whenever a new model is published.
      rows=benchmark_rows(root,version,policy.get('settings_revision',0))
     else:rows=list(read(lane_root/'corpus/manifest.json',{}).values())
     rows=reserve(lane_root,fresh(rows,dataset,lane))
     if lane=='machine':rows=machine_scores(cfg,model,folder,rows[:3000],policy)
     proof=tune(rows,baseline);proof.update(label_source='human' if lane=='hybrid' else 'machine',version=version,epoch=time.time(),eligible=len(rows),metric_scope='Human-reviewed ground truth' if lane=='hybrid' else 'Agreement with independent machine labels; not measured truth')
     fingerprint=hashlib.sha256(json.dumps([version,policy.get('settings_revision'),[(r.get('sample_id') or r.get('id'),r['label'],r['score']) for r in rows]],sort_keys=True).encode()).hexdigest();proof['data_id']=fingerprint
     prior=read(lane_root/'decision-tuning/status.json',{})
     if proof.get('accepted') and prior.get('data_id')!=fingerprint:proof['applied']=apply(cfg,lane,version,policy.get('settings_revision',0),proof['values'],proof)
     save(lane_root/'decision-tuning/status.json',proof);status[lane]=proof
   except Exception as exc:status[lane]=dict(state='retry',message='Automatic tuning will retry; current settings retained.',error=str(exc),epoch=time.time())
  save(root/'automatic-tuning.json',status)
  encoded=repr(json.dumps(status));remote(cfg,"from model_settings import save;save(data/'model-inspector/automatic-tuning.json',json.loads("+encoded+"));print('{}')")
  print(json.dumps(status),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args();cycle(read(a.config))
