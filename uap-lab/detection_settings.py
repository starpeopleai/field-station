"""Current proposal-stage settings shared by all models."""
import copy,fcntl,math,time
from pathlib import Path
from model_settings import read,save,settings_key

def field(group,label,value,minimum,maximum,step=1,odd=False):
 return dict(group=group,label=label,default=value,min=minimum,max=maximum,step=step,integer=step==1,odd=odd)
SCHEMA={
 'motion_difference':field('Motion','Brightness change',8,0,255),
 'motion_detail':field('Motion','Local contrast',5,0,255),
 'background_alpha':field('Motion','Background adaptation',.04,.0001,1,.0001),
 'background_reset_gap':field('Motion','Background reset gap (seconds)',.1,.001,10,.001),
 'fine_kernel':field('Detail filters','Fine blur width',5,1,31,odd=True),
 'fine_sigma':field('Detail filters','Fine blur sigma',1,.1,20,.1),
 'soft_kernel':field('Detail filters','Soft blur width',15,1,61,odd=True),
 'soft_sigma':field('Detail filters','Soft blur sigma',3,.1,30,.1),
 'opening_kernel':field('Detail filters','Noise opening width (0 disables)',2,0,9),
 'dilation_kernel':field('Detail filters','Region expansion width (0 disables)',3,0,9),
 'minimum_area':field('Proposal limits','Minimum region area (pixels)',6,1,100000),
 'minimum_side':field('Proposal limits','Minimum region side (pixels)',3,1,1920),
 'global_difference':field('Exposure diagnostics','Global brightness change',15,0,255),
 'global_fraction':field('Exposure diagnostics','Changed-frame fraction',.2,0,1,.01),
 'track_gap':field('Tracking','Maximum tracking gap (seconds)',.15,.001,10,.001),
 'track_distance':field('Tracking','Minimum matching radius (pixels)',24,1,1024),
 'track_size_factor':field('Tracking','Object-size matching multiplier',3,.1,10,.1),
 'track_velocity_cap':field('Tracking','Maximum velocity allowance (pixels)',80,0,2048),
 'track_ambiguity':field('Tracking','Ambiguity margin',.15,0,1,.01),
 'direction_minimum_speed':field('Tracking','Minimum speed for direction (pixels/second)',1,0,1000,.1),
 'context_minimum':field('Review region','Minimum review-region side (pixels)',64,8,1024),
 'context_padding':field('Review region','Added review-region width/height (pixels)',24,0,512),
 'repeat_gap':field('Repeat grouping','Maximum repeat gap (seconds)',10,0,300,.1),
 'pending_gap':field('Repeat grouping','Unpublished group gap (seconds)',1,0,30,.1),
 'repeat_distance':field('Repeat grouping','Minimum grouping radius (pixels)',64,1,2048),
 'repeat_size_factor':field('Repeat grouping','Object-size grouping multiplier',2,.1,20,.1),
}
DEFAULTS={k:v['default'] for k,v in SCHEMA.items()}
_CACHE={}
def validate(values):
 if not isinstance(values,dict) or set(values)-set(SCHEMA):raise ValueError('Unsupported detection setting')
 for key,value in values.items():
  rule=SCHEMA[key]
  if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not rule['min']<=value<=rule['max']:raise ValueError('Invalid '+rule['label'])
  if rule['integer'] and int(value)!=value:raise ValueError(rule['label']+' must be a whole number')
  if rule['odd'] and int(value)%2!=1:raise ValueError(rule['label']+' must be odd')
 return {k:int(v) if SCHEMA[k]['integer'] else v for k,v in values.items()}
def snapshot(data):
 path=Path(data)/'detection-settings.json'
 try:st=path.stat();identity=(st.st_ino,st.st_mtime_ns,st.st_size)
 except FileNotFoundError:return dict(revision=0,values=dict(DEFAULTS))
 cached=_CACHE.get(str(path))
 if cached is None or cached[0]!=identity:
  doc=read(path,{});values={**DEFAULTS,**validate(doc.get('values',{}))}
  key=doc['revision'] if 'revision' in doc else settings_key({k:v for k,v in values.items() if v!=DEFAULTS[k]})
  _CACHE[str(path)]=(identity,dict(values=values,revision=key))
 return copy.deepcopy(_CACHE[str(path)][1])
def state(data):
 doc=snapshot(data);return dict(values=doc['values'],schema=SCHEMA)
def update(data,value):
 if not isinstance(value,dict) or set(value)-{'revision','expected','values','reset'}:raise ValueError('Invalid detection settings request')
 root=Path(data);root.mkdir(parents=True,exist_ok=True)
 with (root/'detection-settings.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);old=snapshot(root)
  if ('revision' in value and value['revision']!=old['revision']) or value.get('expected',old['values'])!=old['values']:raise ValueError('Detection settings changed. Refresh before saving.')
  values=dict(DEFAULTS) if value.get('reset') is True else {**old['values'],**validate(value.get('values'))}
  if values!=old['values']:
   save(root/'detection-settings.json',dict(values=values,epoch=time.time()))
 return dict(saved=True,**state(root))
