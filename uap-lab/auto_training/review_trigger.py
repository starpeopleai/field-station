"""Queue review-threshold training through the existing serialized controller.

Only committed human-review manifests count. This runs in the controller's
minute poll, never in a web save request, and caches unchanged manifests.
"""
import json,time,uuid
from pathlib import Path
THRESHOLDS=(100,250,500,1000,2500,5000,10000,25000,50000,100000)

def read(path):
 try:return json.loads(path.read_text())
 except (OSError,ValueError):return {}

def maybe_queue(root,state,busy,now=None):
 now=time.time() if now is None else now
 station=Path(root).resolve().parent
 config=read(station/'station-settings.json')
 if config.get('auto_training_enabled') is not True or busy:return
 threshold=config.get('auto_training_reviews',500)
 if type(threshold) is not int or threshold not in THRESHOLDS:return
 enabled=config.get('auto_training_enabled_epoch')
 # Old/malformed configuration must not train on the entire historical set.
 if not isinstance(enabled,(int,float)) or enabled<=0:return
 since=max(enabled,state.get('auto_review_since',enabled))
 manifest=station/'uap-lab/email-reviews/training-manifest.json'
 try:
  stamp=manifest.stat();identity=[stamp.st_mtime_ns,stamp.st_size,since]
  cached=state.get('auto_review_scan',{})
  if cached.get('identity')==identity:count=cached['count']
  else:
   rows=json.loads(manifest.read_text())['examples']
   if not isinstance(rows,list):return
   count=len({r.get('sample_id',r.get('event_id')) for r in rows if r.get('human_confirmed') is True and not r.get('deleted') and not r.get('retired') and r.get('label') in ('anomalous','not_anomalous') and isinstance(r.get('reviewed_epoch'),(int,float)) and since<r['reviewed_epoch']<=now and r.get('sample_id',r.get('event_id'))})
   state['auto_review_scan']=dict(identity=identity,count=count,checked_epoch=now)
 except (OSError,ValueError,KeyError,TypeError):return
 if count<threshold:return
 state['request']=dict(id=uuid.uuid4().hex,state='queued',requested_epoch=now,source='review_threshold',ranking_measure='composite',new_review_count=count,review_threshold=threshold)
