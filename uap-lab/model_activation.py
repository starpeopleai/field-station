"""Durable, explicit operator requests to select a live model/profile."""
import fcntl,time,uuid
from pathlib import Path
from model_settings import read,save,effective,LANES,snapshot
APP=Path(__file__).resolve().parents[1]
CONFIG=APP/'uap-lab/recognition/config.json'

def status(data):
 cfg=read(CONFIG,{}) or {};policy=read(Path(cfg.get('policy','/nonexistent')),{}) or {};health=read(Path(data)/'recognition/status.json',{}) or {}
 lane=cfg.get('decision_lane','human');version=policy.get('version')
 ready=health.get('model')==version and health.get('decision_lane','human')==lane and health.get('runtime_ready') and not health.get('error') and time.time()-health.get('updated_epoch',0)<30
 request=read(Path(data)/'model-inspector/activation.json',{}) or {}
 catalog=read(Path(data)/'model-inspector/models.json',{}) or {};document=snapshot(data)
 models=[dict(lane=m['lane'],version=m.get('version'),available=m.get('available',False),revision=effective(m['policy'],m['lane'],document).get('settings_revision',0) if m.get('available') else None) for m in catalog.get('models',[])]
 return dict(models=models,lane=lane,version=version,ready=bool(ready),settings_revision=health.get('decision_settings_revision'),request={k:request.get(k) for k in ('id','lane','version','revision','phase','error')})

def next_request(data):
 job=read(Path(data)/'model-inspector/activation.json',{}) or {}
 if job.get('phase') not in ('queued','preparing','activating'):return job
 with (APP/'auto-training/deployment.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   # Leave the request durable. The worker polls again after maintenance.
   message='Waiting for station maintenance to release the model.'
   if job.get('error')!=message:update(data,job['id'],error=message)
   return {}
 return job

def request(data,value):
 root=Path(data)/'model-inspector';root.mkdir(parents=True,exist_ok=True)
 with (root/'activation.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  old=read(root/'activation.json',{}) or {}
  if old.get('phase') in ('queued','preparing','activating','monitoring'):
   if all(old.get(k)==value.get(k) for k in ('lane','version')) and value.get('revision',old.get('revision'))==old.get('revision'):return old
   raise ValueError('Another model switch is in progress.')
  lane=value.get('lane');version=value.get('version');catalog=read(root/'models.json',{})
  model=next((m for m in catalog.get('models',[]) if m.get('lane')==lane and m.get('version')==version and m.get('available')),None)
  if lane not in LANES or not model:raise ValueError('Model changed or is unavailable. Refresh before switching.')
  policy=effective(model['policy'],lane,snapshot(data))
  if 'revision' in value and value['revision']!=policy.get('settings_revision',0):raise ValueError('Decision settings changed. Refresh before switching.')
  job=dict(id=uuid.uuid4().hex,lane=lane,version=version,phase='queued',requested_epoch=time.time(),policy=policy)
  if 'revision' in value:job['revision']=value['revision']
  save(root/'activation.json',job);return job

def update(data,identity,**fields):
 root=Path(data)/'model-inspector'
 with (root/'activation.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);job=read(root/'activation.json',{})
  if job.get('id')!=identity:raise ValueError('Model switch was superseded')
  job.update(fields,updated_epoch=time.time());save(root/'activation.json',job);return job
