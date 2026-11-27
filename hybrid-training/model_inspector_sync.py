"""Build public model inspection data on HQ; keep tensor loading off the field web server."""
import uuid,argparse,base64,hashlib,json,os,shlex,subprocess,sys,time,zlib
from pathlib import Path

def read(path,default=None):
 try:return json.loads(Path(path).read_text())
 except FileNotFoundError:return default

def save(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(value,allow_nan=False));temp.replace(path)

def folder_for(root,version,state):
 folders=[Path(state.get('shadow_folder','/nonexistent')),Path(state.get('run_directory','/nonexistent')),root/'runs'/version]
 for folder in folders:
  if read(folder/'candidate-policy.json',{}).get('version')==version:return folder
 for p in (root/'runs').glob('*/candidate-policy.json'):
  if read(p,{}).get('version')==version:return p.parent
 raise ValueError('Published model artifact is unavailable on HQ')

def describe_weights(folder,cache):
 import torch
 path=folder/'candidate-weights.pt';stat=path.stat();key=hashlib.sha256((str(path)+':'+str(stat.st_size)+':'+str(stat.st_mtime_ns)).encode()).hexdigest();dest=cache/(key+'.json')
 previous=read(dest)
 if previous:return previous
 weights=torch.load(path,map_location='cpu',weights_only=True);tensors=[];heads=[];total=0;learned=0
 for name,tensor in weights.items():
  if not isinstance(tensor,torch.Tensor):continue
  array=tensor.detach().cpu();count=array.numel();total+=count;adapted=name.startswith(('head.','corrections.'))
  if adapted:learned+=count
  values=array.to(torch.float64)
  if not torch.isfinite(values).all():raise ValueError('Nonfinite model tensor')
  row=dict(name=name,shape=list(array.shape),count=count,dtype=str(array.dtype).removeprefix('torch.'),role='Trained classifier' if adapted else 'Frozen feature extractor / buffer',minimum=float(values.min()) if count else None,maximum=float(values.max()) if count else None,mean=float(values.mean()) if count else None,std=float(values.std(unbiased=False)) if count else None)
  tensors.append(row)
  if adapted and count<=16384:heads.append(dict(name=name,shape=list(array.shape),values=array.tolist()))
 digest=hashlib.sha256(path.read_bytes()).hexdigest();value=dict(total_values=total,trained_classifier_values=learned,tensors=tensors,classifiers=heads,file=dict(name=path.name,bytes=stat.st_size,sha256=digest))
 save(dest,value);return value

def rpc(cfg,code):
 command=shlex.join(['/Users/ufo-field/ufo-field/venv/bin/python','-c',code])
 return subprocess.check_output(['/usr/bin/python3',cfg['ssh_helper'],command],text=True,timeout=90)

def pull_settings(cfg):
 root=Path(cfg['root']);code="import sys,json;from pathlib import Path;sys.path.insert(0,'/Users/ufo-field/ufo-field/uap-lab');from model_settings import snapshot;print(json.dumps(snapshot(Path('/Volumes/UFO-Field/uap-lab'))))"
 document=json.loads(rpc(cfg,code));save(root/'model-settings.json',document);return document

def cycle(cfg):
 from experimental_profile import sync as sync_experimental
 sync_experimental(cfg)
 root=Path(cfg['root']);root.mkdir(parents=True,exist_ok=True);cache=root/'model-inspector/weights'
 # A model catalog can still refresh during a brief offline period; retain last settings.
 try:pull_settings(cfg)
 except Exception as exc:save(root/'model-inspector/sync-status.json',dict(state='settings_retry',error=str(exc),epoch=time.time()))
 models=[]
 lanes=[('human','Human-curated (stable)','human_root'),('experimental','Human-curated (experimental)','experimental_root'),('hybrid','Hybrid','hybrid_root'),('machine','Machine-only','machine_root')]
 if cfg.get('rotation_root'):lanes.append(('rotation','Human-curated (rotation)','rotation_root'))
 for lane,label,root_key in lanes:
  model=dict(lane=lane,label=label,available=False,live=lane=='human')
  try:
   lane_root=Path(cfg[root_key]);state=read(lane_root/'status.json',{});version=state.get('active_version') if lane=='human' else state.get('shadow_version')
   if not version:raise ValueError('No published model yet')
   folder=folder_for(lane_root,version,state);policy=read(folder/'candidate-policy.json');dataset=read(folder/'dataset.json',{})
   publication=(state.get('publication') if lane!='human' else read(lane_root/'model-publication/status.json',{})) or {}
   if lane=='experimental' and state.get('experiment_mode')=='decision_profile':
    publication=read(Path(cfg['human_root'])/'model-publication/status.json',{}) or {}
   model.update(experiment_mode=state.get('experiment_mode'),baseline_version=state.get('baseline_version'),available=True,version=version,policy=policy,architecture=policy.get('architecture','MobileNetV3 Small + trained linear classifier'),input_shape=[3,224,224],classes=policy['classes'],weights=describe_weights(folder,cache),training=dict(counts=dataset.get('counts',{}),human_counts=dataset.get('human_training_counts',{}),strategy=dataset.get('training_strategy','class_balanced'),source=dataset.get('training_lane','human_curated'),images=len(dataset.get('samples',[]))),trained_epoch=state.get('trained_epoch'),release_url=publication.get('url') if publication.get('version')==version else None)
  except Exception as exc:model['error']=str(exc)
  models.append(model)
 value=dict(models=models,updated_epoch=time.time());save(root/'model-inspector/models.json',value)
 payload=base64.b64encode(zlib.compress(json.dumps(value,allow_nan=False).encode())).decode()
 code="import sys,json,base64,zlib;from pathlib import Path;sys.path.insert(0,'/Users/ufo-field/ufo-field/uap-lab');from model_settings import save;root=Path('/Volumes/UFO-Field/uap-lab/model-inspector');value=json.loads(zlib.decompress(base64.b64decode("+repr(payload)+")));save(root/'models.json',value);\nif not (root/'settings.json').exists():save(root/'settings.json',dict(models={},history=[]))\nprint('Model inspection catalog synchronized')"
 rpc(cfg,code);save(root/'model-inspector/sync-status.json',dict(state='ready',epoch=time.time(),available=[m['lane'] for m in models if m['available']]))
 return value

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);args=parser.parse_args();value=cycle(read(args.config));print(json.dumps(dict(models=[dict(lane=m['lane'],available=m['available'],version=m.get('version')) for m in value['models']])))
