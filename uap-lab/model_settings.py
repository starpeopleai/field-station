"""Version-scoped decision controls. Learned model artifacts remain immutable."""
import argparse,copy,fcntl,json,math,os,re,time,uuid
from pathlib import Path

LANES={'human':'Human-curated (stable)','experimental':'Human-curated (experimental)','hybrid':'Hybrid','machine':'Machine-only','rotation':'Human-curated (rotation)'}
FIELDS={'anomaly_threshold','minimum_native_size','night_confirmation','minimum_context_score'}
_CACHE={}
AUTOMATIC={'hybrid','machine'}

def read(path,default=None):
 try:return json.loads(Path(path).read_text())
 except FileNotFoundError:return default

def save(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 try:
  with tmp.open('w') as out:json.dump(value,out,allow_nan=False);out.flush();os.fsync(out.fileno())
  tmp.replace(path)
 finally:tmp.unlink(missing_ok=True)

def snapshot(data):
 path=Path(data)/'model-inspector/settings.json'
 try:stat=path.stat();identity=(stat.st_ino,stat.st_mtime_ns,stat.st_size)
 except FileNotFoundError:return {'models':{}}
 cached=_CACHE.get(str(path))
 if cached is None or cached[0]!=identity:
  value=read(path,{'models':{}})
  if not isinstance(value,dict) or not isinstance(value.get('models',{}),dict):raise ValueError('Invalid model settings file')
  _CACHE[str(path)]=(identity,value)
 return copy.deepcopy(_CACHE[str(path)][1])

def defaults(policy):
 values=dict(anomaly_threshold=policy.get('thresholds',{}).get('anomalous',.8),minimum_native_size=policy.get('minimum_native_size',8))
 night=policy.get('night_context_confirmation',{})
 if policy.get('classification_input_scope')!='review_box' and night.get('version')==policy.get('version') and policy.get('input_color_space')=='RGB' and isinstance(night.get('minimum_context_score'),(int,float)) and 0<night['minimum_context_score']<=.001:
  values.update(night_confirmation=bool(night.get('enabled')),minimum_context_score=night['minimum_context_score'])
 from color_decision import DEFAULTS
 if policy.get('input_color_space')=='RGB':values.update(dict(DEFAULTS,**policy.get('color_decision',{})))
 return values

def validate(values,policy):
 allowed=defaults(policy)
 if not isinstance(values,dict) or set(values)-set(allowed):raise ValueError('Unsupported decision setting')
 for name,value in values.items():
  if name in ('night_confirmation','color_evidence'):
   if not isinstance(value,bool):raise ValueError('Night confirmation must be on or off')
  elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Decision settings must be finite numbers')
  elif name=='anomaly_threshold' and not 0<=value<=1:raise ValueError('Anomaly threshold must be between 0 and 1')
  elif name=='minimum_native_size' and (int(value)!=value or not 1<=value<=1920):raise ValueError('Minimum size must be a whole number from 1 to 1920 pixels')
  elif name=='minimum_context_score' and not 0<value<=.001:raise ValueError('Night context score must be greater than 0 and at most 0.001')
  elif name in ('color_score_boost','multicolor_score_boost','color_bonus_cap','color_brightness_floor','color_foreground_quantile') and not 0<=value<=1:raise ValueError('Color setting must be between 0 and 1')
  elif name=='color_clipping_limit' and not 0<value<=1:raise ValueError('Clipping limit must be greater than 0 and at most 1')
  elif name=='minimum_colored_pixels' and (int(value)!=value or not 1<=value<=262144):raise ValueError('Colored pixel count must be a whole number from 1 to 262144')
  elif name=='color_analysis_size' and (int(value)!=value or not 16<=value<=512):raise ValueError('Color analysis size must be a whole number from 16 to 512')
  elif name in ('minimum_color_saturation','minimum_color_fraction','minimum_color_diversity') and not 0<value<=1:raise ValueError('Color thresholds must be greater than 0 and at most 1')
 return dict(values)

def effective(policy,lane,document):
 policy=copy.deepcopy(policy);key=lane+':'+str(policy.get('version'));record=document.get('models',{}).get(key,{})
 changes=validate(record.get('values',{}),policy)
 if 'anomaly_threshold' in changes:policy.setdefault('thresholds',{})['anomalous']=changes['anomaly_threshold']
 if 'minimum_native_size' in changes:policy['minimum_native_size']=int(changes['minimum_native_size'])
 if 'night_confirmation' in changes:policy['night_context_confirmation']['enabled']=changes['night_confirmation']
 if 'minimum_context_score' in changes:policy['night_context_confirmation']['minimum_context_score']=changes['minimum_context_score']
 from color_decision import DEFAULTS
 color={k:v for k,v in changes.items() if k in DEFAULTS}
 if color:policy['color_decision']={**DEFAULTS,**policy.get('color_decision',{}),**color}
 policy['classification_input_scope']='review_box'
 if 'night_context_confirmation' in policy:policy['night_context_confirmation']['enabled']=False
 policy['settings_revision']=record.get('revision',0)
 return policy

def state(data):
 root=Path(data)/'model-inspector';catalog=read(root/'models.json',{'models':[]});document=snapshot(data);models=[]
 by_lane={m['lane']:m for m in catalog.get('models',[]) if m.get('lane') in LANES}
 for lane,label in LANES.items():
  model=copy.deepcopy(by_lane.get(lane,dict(lane=lane,label=label,available=False)))
  if model.get('available'):
   policy=model['policy'];configured=effective(policy,lane,document);record=document.get('models',{}).get(lane+':'+policy['version'],{})
   model.update(defaults=defaults(policy),settings=defaults(configured),settings_revision=record.get('revision',0),settings_changed_epoch=record.get('epoch'),overridden=bool(record.get('values')))
  if model.get('policy'):model['policy']['classification_input_scope']='review_box'
  model['settings_owner']='automatic' if lane in AUTOMATIC else 'human'
  model['automatic_tuning']=read(root/'automatic-tuning.json',{}).get(lane,{}) if lane in AUTOMATIC else None
  models.append(model)
 from model_activation import status as activation_status
 active=activation_status(data)
 for model in models:model['live']=bool(active['ready'] and model['lane']==active['lane'] and model.get('version')==active['version'])
 return dict(models=models,updated_epoch=catalog.get('updated_epoch'))

def update(data,value):
 if not isinstance(value,dict):raise ValueError('Invalid model settings request')
 lane=value.get('lane');version=value.get('version')
 if lane in AUTOMATIC:raise ValueError('This model’s decision settings are managed automatically.')
 if lane not in LANES or not re.fullmatch('[a-f0-9]{64}',str(version)):raise ValueError('Invalid model version')
 root=Path(data)/'model-inspector';root.mkdir(parents=True,exist_ok=True)
 with (root/'settings.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  catalog=read(root/'models.json',{})
  model=next((m for m in catalog.get('models',[]) if m.get('lane')==lane and m.get('version')==version and m.get('available')),None)
  if model is None:raise ValueError('Model version changed. Refresh this tab before saving.')
  document=snapshot(data);key=lane+':'+version;old=document.get('models',{}).get(key,{})
  if value.get('revision')!=old.get('revision',0):raise ValueError('Settings changed in another session. Refresh before saving.')
  changes={} if value.get('reset') is True else validate(value.get('values'),model['policy'])
  record=dict(values=changes,revision=old.get('revision',0)+1,epoch=time.time())
  document.setdefault('models',{})[key]=record
  document['history']=[*document.get('history',[]),dict(lane=lane,version=version,previous=old.get('values',{}),**record)][-100:]
  save(root/'settings.json',document)
 return dict(saved=True,lane=lane,version=version,revision=record['revision'])

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,required=True);parser.add_argument('action',choices=['export','catalog']);parser.add_argument('--json');args=parser.parse_args()
 if args.action=='export':print(json.dumps(snapshot(args.data)))
 else:
  value=json.loads(args.json)
  if not isinstance(value.get('models'),list) or any(m.get('lane') not in LANES for m in value['models']):raise ValueError('Invalid model catalog')
  save(args.data/'model-inspector/models.json',value)
  if not (args.data/'model-inspector/settings.json').exists():save(args.data/'model-inspector/settings.json',dict(models={},history=[]))
  print(json.dumps(dict(saved=True)))

def rebase_experimental(data,version,policy):
 """Move the independent experiment settings to the new shared Stable artifact."""
 if version!=policy.get('version') or not re.fullmatch('[a-f0-9]{64}',version):raise ValueError('Invalid stable model version')
 root=Path(data)/'model-inspector';root.mkdir(parents=True,exist_ok=True)
 with (root/'settings.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);document=snapshot(data);key='experimental:'+version
  if key in document.get('models',{}):return dict(changed=False,version=version)
  previous=[(k,v) for k,v in document.get('models',{}).items() if k.startswith('experimental:')]
  old_key,old=max(previous,key=lambda item:item[1].get('epoch',0)) if previous else (None,{})
  values={k:v for k,v in old.get('values',{}).items() if k in defaults(policy)};validate(values,policy)
  record=dict(values=values,revision=1,epoch=time.time(),copied_from=old_key)
  document.setdefault('models',{})[key]=record
  document['history']=[*document.get('history',[]),dict(lane='experimental',version=version,action='follow_stable_weights',**record)][-100:]
  save(root/'settings.json',document)
 return dict(changed=True,version=version,values=values)

def automatic_update(data,lane,version,revision,values,proof):
 """Local worker entry point. The web settings endpoint cannot invoke this."""
 if lane not in AUTOMATIC:raise ValueError('Manual model settings cannot be automatically changed')
 root=Path(data)/'model-inspector';root.mkdir(parents=True,exist_ok=True)
 with (root/'settings.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);document=snapshot(data);catalog=read(root/'models.json',{})
  model=next((m for m in catalog.get('models',[]) if m.get('lane')==lane and m.get('version')==version and m.get('available')),None)
  if not model:raise ValueError('Model changed during automatic tuning')
  key=lane+':'+version;old=document.get('models',{}).get(key,{})
  if old.get('revision',0)!=revision:raise ValueError('Settings changed during automatic tuning')
  initialization=proof.get('action')=='automatic_baseline'
  if initialization:
   if old.get('owner')=='automatic':return dict(changed=False)
   changes=defaults(model['policy'])
  else:
   if old.get('owner')!='automatic' or not proof.get('accepted') or not proof.get('independent_groups') or proof.get('label_source')!=('human' if lane=='hybrid' else 'machine'):raise ValueError('Automatic tuning evidence is incomplete')
   changes=validate(values,model['policy'])
   if changes==old.get('values'):return dict(changed=False)
  record=dict(values=changes,revision=revision+1,epoch=time.time(),owner='automatic',evidence=proof)
  document.setdefault('models',{})[key]=record
  document['history']=[*document.get('history',[]),dict(lane=lane,version=version,previous=old,**record)][-100:]
  save(root/'settings.json',document)
 return dict(changed=True,revision=record['revision'])


def migrate_review_box_contract(data):
 """Version the input correction without overwriting the operator's settings."""
 root=Path(data)/'model-inspector'
 with (root/'settings.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);document=snapshot(data)
  if document.get('input_contract')=='review-box-v1':return dict(changed=False)
  catalog=read(root/'models.json',{})
  for model in catalog.get('models',[]):
   if not model.get('available'):continue
   key=model['lane']+':'+model['version'];old=document.setdefault('models',{}).get(key,{})
   record=dict(old,values=old.get('values',{}),revision=old.get('revision',0)+1,epoch=time.time(),input_contract='review-box-v1')
   document['models'][key]=record;document['history']=[*document.get('history',[]),dict(lane=model['lane'],version=model['version'],action='review_box_input_correction',**record)][-100:]
  document['input_contract']='review-box-v1';save(root/'settings.json',document);return dict(changed=True)
