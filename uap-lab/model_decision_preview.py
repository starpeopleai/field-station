"""Preview draft decisions on exact review pixels using versioned HQ predictions."""
import base64,hashlib,json,math,time
from pathlib import Path
from object_model_scores import connect,crop,attach
from model_settings import state,validate,effective
from color_decision import apply
from binary_decision import decide

def decision(raw,result,model,values,expected_sha):
 if result.get('state')!='ready' or result.get('version')!=model['version'] or result.get('input_contract')!='review-box-v1':return None
 if hashlib.sha256(raw).hexdigest()!=expected_sha:return None
 color=result.get('color_evidence') or {}
 score=color.get('raw_anomaly_score',result.get('anomaly_score'))
 if not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=1:return None
 policy=effective(model['policy'],model['lane'],dict(models={model['lane']+':'+model['version']:dict(values=values)}))
 prediction=apply(dict(scores=dict(anomalous=score,not_anomalous=1-score)),raw,policy)
 return dict(label=decide(prediction['scores'],policy['thresholds']['anomalous']),anomaly_score=prediction['scores']['anomalous'])

def fresh(row,now):
 epoch=row.get('detected_epoch')
 return row.get('kind')=='detection' and not row.get('human_reviewed') and isinstance(epoch,(int,float)) and math.isfinite(epoch) and 0<=now-epoch<=300

def preview(data,value):
 mode=value.get('mode','recall');now=time.time()
 if mode not in ('recall','live'):raise ValueError('Invalid preview mode')
 lane=value.get('lane');model=next((m for m in state(data)['models'] if m['lane']==lane and m.get('available')),None)
 if model is None:raise ValueError('Model is not available yet')
 if value.get('version')!=model['version']:raise ValueError('Model version changed. Reload this tab.')
 values={**model['settings'],**validate(value.get('values',{}),model['policy'])}
 ids=value.get('ids',[])
 if not isinstance(ids,list) or len(ids)>6 or any(not isinstance(i,str) or len(i)>160 for i in ids):raise ValueError('Invalid preview frames')
 live_rows={}
 if mode=='live':
  from live_camera_samples import samples
  sample=samples(data,refresh=value.get('select_new',False))
  if sample['preparing']:return dict(frames=[],version=model['version'],lane=lane,pending=1,mode=mode)
  chosen=sample['rows'];live_rows={row['id']:row for row in chosen};ids=list(live_rows)
  if chosen:attach(data,dict(items=chosen))
 elif not ids:
  from detection_library import listing
  chosen=[]
  for category in ('anomalous','not_anomalous'):
   candidates=listing(data,classification=category,review_status='human_reviewed',limit=12).get('items',[])
   count=0
   for row in candidates:
    try:crop(data,row)
    except (OSError,ValueError,KeyError):continue
    chosen.append(row);count+=1
    if count==3:break
  if chosen:attach(data,dict(items=chosen));ids=[row['id'] for row in chosen]
 with connect(data) as db:
  if ids:
   rows=db.execute('SELECT id,signature,row,results FROM scores WHERE id IN ('+','.join('?' for _ in ids)+')',ids).fetchall();order={key:i for i,key in enumerate(ids)};rows.sort(key=lambda r:order[r[0]])
  else:
   # Select from the review cache, never scan a training corpus in HTTP.
   rows=[]
  hashes={(key,sig):db.execute('SELECT crop FROM prediction_history WHERE id=? AND signature=?',(key,sig)).fetchone() for key,sig,_,_ in rows}
 selected=[];other=[];counts={}
 for key,sig,serialized,encoded in rows:
  row=json.loads(serialized)
  if mode=='live':
   row=live_rows.get(key)
   if row is None:continue
  try:raw=crop(data,row)
  except (OSError,ValueError,KeyError):continue
  group=row.get('label','not_anomalous');item=(key,sig,row,raw,json.loads(encoded or '{}'))
  if ids or counts.get(group,0)<3:selected.append(item);counts[group]=counts.get(group,0)+1
  else:other.append(item)
  if len(selected)==6:break
 if len(selected)<6:selected.extend(other[:6-len(selected)])
 frames=[];pending=[]
 for key,sig,row,raw,results in selected:
  checksum=hashes.get((key,sig));result=decision(raw,results.get(lane,{}),model,values,row.get('native_crop_sha256') if mode=='live' else checksum[0] if checksum else None)
  if result is None:pending.append(row)
  if mode=='live':
   from model_settings import read
   saved=read(Path(data)/'email-reviews/examples'/key[8:]/'review.json',{})
   if saved.get('human_confirmed') and not saved.get('deleted'):row=dict(row,human_reviewed=True,label=saved['label'])
  frames.append(dict(id=key,captured_epoch=row.get('detected_epoch'),image='data:image/png;base64,'+base64.b64encode(raw).decode(),state='ready' if result else 'pending',human_reviewed=bool(row.get('human_reviewed')),human_label=row.get('label') if row.get('human_reviewed') else None,**(result or {})))
 if pending:
  attach(data,dict(items=pending))
  pending_ids={r['id'] for r in pending}
  with connect(data) as db:
   for key,sig,row,raw,results in selected:
    if key in pending_ids and results:db.execute('UPDATE scores SET results=NULL,retry=0 WHERE id=? AND signature=?',(key,sig))
 reason=None
 if mode=='live' and not frames:reason='No fresh camera frames available.'
 return dict(frames=frames,version=model['version'],lane=lane,pending=len(pending),mode=mode,empty_reason=reason)
